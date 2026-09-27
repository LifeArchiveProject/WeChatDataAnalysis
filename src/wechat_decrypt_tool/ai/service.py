from __future__ import annotations
from .diagnostics import observed, event as diagnostic_event, context as diagnostic_context, new_id, failures
import logging

import asyncio
import copy
import json
import hashlib
import time
from datetime import datetime, timedelta
from typing import TypedDict

from .media import MediaService
from .messages import advance_cursor, filter_after, read_messages
from .providers import ModelService, ProviderFailure, public_profile
from .schemas import Matches, RuleInput, Summary, TaskInput
from .storage import AIStore


class TaskCancelled(Exception):
    pass


class GraphState(TypedDict, total=False):
    task_id: str
    index: int
    conversations: list[dict]
    results: list[dict]
    overview: dict


def split_messages(messages, limit=18000):
    """保持来源标识；长附件逐段送入模型，并为提醒保留前文上下文。"""
    chunks, current, size = [], [], 0
    for message in messages:
        text = message["text"] or f"[{message['kind']}]"
        for offset in range(0, len(text), limit // 2):
            part = {k: message[k] for k in ("source", "time", "sender")}
            part["text"] = text[offset:offset + limit // 2]
            length = len(json.dumps(part, ensure_ascii=False))
            if current and size + length > limit:
                chunks.append(current)
                current, size = [], 0
            current.append(part)
            size += length
    if current:
        chunks.append(current)
    return chunks


def validate_sources(result, allowed, alert=False):
    groups = [result.get("matches", [])] if alert else [result.get(k, []) for k in ("topics", "conclusions", "todos")]
    for group in groups:
        for point in group:
            if any(source not in allowed for source in point.get("sources", [])):
                raise ProviderFailure("模型返回了无效消息来源，请重试")
    return result


def next_due(rule, now=None):
    now = time.time() if now is None else now
    if rule["trigger"] == "daily":
        hour, minute = map(int, rule["daily_time"].split(":"))
        target = datetime.fromtimestamp(now).replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target.timestamp() <= now:
            target += timedelta(days=1)
        return target.timestamp()
    return now + (10 if rule["trigger"] == "count" else rule["interval_seconds"])


class AIService:
    def __init__(self, store=None, models=None, reader=None):
        self.store = store or AIStore()
        self.models = models or ModelService(self.store)
        self.media = MediaService(self.store, self.models)
        self.reader = reader or read_messages
        self.loop_task = None
        self.worker = None
        self.active_id = None
        self.stopping = False
        self.deleted_accounts = set()
        self.rule_locks = {}

    def check(self, id):
        task = self.store.get("task", id)
        if self.stopping or not task or task.get("cancel_requested") or task["account"] in self.deleted_accounts:
            raise TaskCancelled()
        return task

    def update_task(self, id, **fields):
        task = self.store.get("task", id)
        if task is None:
            return
        if fields.get("stage") and fields["stage"] != task.get("stage"):
            fields["stage_started_at"] = time.time()
            activity = list(task.get("activity", []))
            # 记录真实阶段，不保存模型思考过程或提示词。
            activity.append({"stage": fields["stage"], "time": fields["stage_started_at"]})
            fields["activity"] = activity[-60:]
        if fields.get("status") in {"completed", "failed", "partial", "cancelled"}:
            fields["finished_at"] = time.time()
        fields["updated_at"] = time.time()
        self.store.put("task", task | fields, id=id)
        if fields.get('status') and fields['status'] != task.get('status'):
            diagnostic_event('summary.task.state', level=logging.ERROR if fields['status']=='failed' else logging.INFO,
                             task_id=id, status=fields['status'], failed_count=sum(bool(r.get('error')) for r in fields.get('results', task.get('results', []))))
        self.store.event(task["account"], "task", {"task_id": id, **{k: v for k, v in fields.items() if k in {"status", "stage", "progress"}}})

    def snapshot_models(self, options):
        text = self.models.resolve(options.get("profile_id", ""))
        vision = {}
        if options.get("media", True):
            try:
                vision = self.models.resolve(options.get("vision_profile_id", ""), vision=True)
            except ProviderFailure:
                if options.get("vision_profile_id"):
                    raise
                if text.get("vision"):
                    vision = text
        return {"text": public_profile(text), "vision": public_profile(vision) if vision else {}}

    @observed('summary.create_task', id_field='task_id')
    def create_task(self, options, rule=None, prepared=None):
        options = TaskInput.model_validate(options).model_dump()
        # 截止到上一完整秒，同一秒的后续消息留给下一轮。
        end = min(options["range"].get("end") or int(time.time()) - 1, int(time.time()) - 1)
        range = options["range"]
        start = range.get("start")
        if range["mode"] == "hours":
            start = max(0, end - int(range["hours"] * 3600))
        models = self.snapshot_models(options)
        task = self.store.put("task", {**options, "range": {**range, "start": start, "end": end},
            "trace_id": diagnostic_context.get().get('trace_id') or new_id(),
            "status": "queued", "stage": "等待执行", "created": time.time(), "models": models,
            "rule_id": rule["id"] if rule else "", "rule_revision": rule.get("revision") if rule else None,
            "kind": rule["kind"] if rule else "summary", "condition": rule.get("condition", "") if rule else "",
            "cursors": copy.deepcopy(rule.get("cursors", {})) if rule else {}, "results": [], "overview": {},
            "cancel_requested": False, "progress": 0, "error": "", "attempts": 0, "retry_at": 0})
        if prepared is not None:
            self.store.put("prepared", {"conversations": prepared}, id=task["id"], account=task["account"])
        diagnostic_event('summary.task.created', task_id=task['id'], start=start, end=end, mode=range['mode'], count=len(options['conversations']))
        return task

    def task_profile(self, task, vision=False):
        snapshot = task["models"]["vision" if vision else "text"]
        if not snapshot:
            return {}
        live = self.models.resolve(snapshot["id"], vision=vision)
        # 执行参数固定为提交时版本；密钥在执行时单独解析，不保存到检查点。
        return {**snapshot, "api_key": live.get("api_key", "")}

    @observed('summary.read_conversations', id_field='task_id')
    async def read_conversations(self, options, rule=None, checkpoint=None):
        end = options["range"].get("end") or int(time.time()) - 1
        conversations = []
        for username in options["conversations"]:
            if checkpoint:
                checkpoint()
            cursor = (rule or {}).get("cursors", {}).get(username)
            start = options["range"].get("start")
            incremental = bool(rule and (rule["kind"] == "alert" or rule["trigger"] == "count" or options["range"]["mode"] == "since"))
            if incremental and cursor:
                start = cursor["time"]
            count = options["range"]["count"] if options["range"]["mode"] == "count" and not incremental else None
            try:
                read_started = time.monotonic()
                diagnostic_event('summary.conversation.read.started', username=username, start=start, end=end, incremental=incremental, count=count)
                conv = await asyncio.to_thread(self.reader, options["account"], username, start, end, count,
                    bool(rule and rule["kind"] == "alert"), checkpoint)
                if incremental and cursor:
                    conv["messages"] = filter_after(conv["messages"], cursor)
                conv["context"] = []
                if rule and rule["kind"] == "alert" and conv["messages"]:
                    # 只补充近期对话，低频会话不能为了凑足条数回溯多年前的无关资料。
                    context_end = conv["messages"][0]["time"]
                    context_start = max(0, context_end - 24 * 3600, options["range"].get("start") or 0)
                    context = await asyncio.to_thread(self.reader, options["account"], username, context_start,
                        context_end, 20, True, checkpoint)
                    new_sources = {m["source"] for m in conv["messages"]}
                    conv["context"] = [m for m in context["messages"] if m["source"] not in new_sources]
                conversations.append(conv)
                diagnostic_event('summary.conversation.read.finished', username=username, returned=len(conv['messages']), duration_ms=(time.monotonic()-read_started)*1000)
            except TaskCancelled:
                raise
            except Exception as exc:
                diagnostic_event('summary.conversation.read.failed', level=logging.ERROR, error=exc, username=username)
                conversations.append({"username": username, "name": username, "messages": [], "error": "消息读取失败：" + (str(exc) if isinstance(exc, ValueError) else "请检查消息数据源")})
        return conversations

    @observed('summary.graph_read', id_field='task_id')
    async def graph_read(self, state):
        task = self.check(state["task_id"])
        self.update_task(task["id"], stage="读取消息", progress=2)
        prepared = self.store.get("prepared", task["id"])
        if prepared:
            diagnostic_event('summary.read.cache', cached=True, count=len(prepared['conversations']))
            conversations = prepared["conversations"]
        else:
            rule = self.store.get("rule", task["rule_id"]) if task["rule_id"] else None
            if rule:
                rule = {**rule, "cursors": task["cursors"]}
            conversations = await self.read_conversations(task, rule, lambda: self.check(task["id"]))
        self.check(task["id"])
        self.update_task(task["id"], conversation_names=[c["name"] for c in conversations], message_count=sum(len(c["messages"]) for c in conversations))
        return {"conversations": conversations, "index": 0, "results": []}

    @observed('summary.summarize_parts', id_field='task_id')
    async def summarize_parts(self, task, messages, prefix, alert=False, progress=None):
        chunks = split_messages(messages)
        output = []
        for i, chunk in enumerate(chunks):
            self.check(task["id"])
            if progress:
                progress(i, len(chunks))
            digest = hashlib.sha256(json.dumps(chunk, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            key = f"{task['id']}:{prefix}:{i}:{digest}"
            cached = self.store.get("partial", key)
            if cached:
                diagnostic_event('summary.segment.cache', task_id=task['id'], index=i, cached=True)
                output.append(cached["result"])
                continue
            context = chunks[i - 1][-5:] if alert and i else []
            diagnostic_event('summary.segment.started', index=i, count=len(chunk), segments=len(chunks))
            prompt = ("判断是否满足关注条件：" + task["condition"] + "。仅对新增消息给出命中，不满足返回空 matches。" if alert else "总结资料，区分话题、已确定结论和待办事项，不臆造负责人或时间。")
            prompt += "\n前文上下文：" + json.dumps(context, ensure_ascii=False) + "\n资料：" + json.dumps(chunk, ensure_ascii=False)
            result = await self.models.invoke(self.task_profile(task), prompt, Matches if alert else Summary, account=task["account"])
            self.check(task["id"])
            validate_sources(result, {m["source"] for m in chunk + context}, alert)
            self.store.put("partial", {"result": result}, id=key, account=task["account"])
            output.append(result)
            diagnostic_event('summary.segment.finished', index=i, validation_status='success')
        if alert:
            return {"matches": [m for x in output for m in x["matches"]]}
        if not output:
            return Summary(overview="该范围没有可总结的消息").model_dump()
        return await self.merge_summaries(task, output, {m["source"] for m in messages}, prefix)

    @observed('summary.merge_summaries', id_field='task_id')
    async def merge_summaries(self, task, output, allowed_sources, prefix):
        # 层次合并，避免大量分段摘要再次超出模型上下文。
        level = 0
        while len(output) > 1:
            self.update_task(task["id"], stage="合并分段摘要")
            merged = []
            for i in range(0, len(output), 4):
                self.check(task["id"])
                group = output[i:i + 4]
                digest = hashlib.sha256(json.dumps(group, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                key = f"{task['id']}:{prefix}:merge:{level}:{i}:{digest}"
                cached = self.store.get("partial", key)
                diagnostic_event('summary.merge.started', index=i, merge_level=level, count=len(group), cached=bool(cached))
                if cached:
                    value = cached["result"]
                else:
                    value = await self.models.invoke(self.task_profile(task), "合并以下摘要，保留消息来源并去除重复，不增加未经证实的信息：\n" + json.dumps(group, ensure_ascii=False), Summary, account=task["account"])
                    self.check(task["id"])
                    validate_sources(value, allowed_sources)
                    self.store.put("partial", {"result": value}, id=key, account=task["account"])
                merged.append(value)
                diagnostic_event('summary.merge.finished', index=i, merge_level=level, cached=bool(cached), validation_status='success')
            output = merged
            level += 1
        return output[0]

    @observed('summary.graph_analyze', id_field='task_id')
    async def graph_analyze(self, state):
        task = self.check(state["task_id"])
        index = state["index"]
        conv = state["conversations"][index]
        result = {"username": conv["username"], "name": conv["name"], "count": len(conv["messages"]),
                  "first_time": min((m["time"] for m in conv["messages"]), default=None),
                  "last_time": max((m["time"] for m in conv["messages"]), default=None),
                  "warning": conv.get("warning", ""), "sources": [], "coverage": [], "error": conv.get("error", "")}
        if not result["error"]:
            try:
                base = 5 + 85 * index / len(state["conversations"])
                share = 85 / len(state["conversations"])
                messages = conv.get("context", []) + conv["messages"]
                media_total = sum(m["kind"] in {"image", "file"} for m in messages) if task["media"] else 0
                media_index = 0
                self.update_task(task["id"], stage=f"已读取 {len(conv['messages'])} 条消息，准备分析", progress=round(base))
                enriched = []
                for message_index, message in enumerate(messages):
                    self.check(task["id"])
                    if task["media"] and message["kind"] in {"image", "file"}:
                        media_index += 1
                        self.update_task(task["id"], stage=f"处理图片与附件 {media_index}/{media_total} · {conv['name']}",
                                         progress=round(base + share * .5 * message_index / max(1, len(messages))))
                    value = await self.media.enrich(task["account"], message, task, self.task_profile(task, True), lambda: self.check(task["id"]))
                    enriched.append(value)
                    result["sources"].append({k: message[k] for k in ("source", "anchor", "username", "time", "sender")})
                    if value.get("coverage"):
                        result["coverage"].append({"source": value["source"], "status": value["coverage"]})
                def report_summary(done, total):
                    self.update_task(task["id"], stage=f"{'判断关注条件' if task['kind'] == 'alert' else '生成摘要'} {done + 1}/{total} · {conv['name']}",
                                     progress=round(base + share * (.5 + .5 * done / max(1, total))))
                result["summary"] = await self.summarize_parts(task, enriched, conv["username"], task["kind"] == "alert", report_summary)
                if any(not x["status"].startswith("已分析") and x["status"] != "未启用媒体分析" for x in result["coverage"]):
                    result["error"] = "部分附件未分析，请补齐附件或调整模型后重试；检查点尚未推进"
                if task["kind"] == "alert":
                    new_ids = {m["source"] for m in conv["messages"]}
                    result["summary"]["matches"] = [{**m, "sources": [s for s in m["sources"] if s in new_ids]} for m in result["summary"]["matches"] if any(s in new_ids for s in m["sources"])]
                result["cursor"] = advance_cursor(conv["messages"], task["cursors"].get(conv["username"]))
            except TaskCancelled:
                raise
            except ProviderFailure as exc:
                diagnostic_event('summary.conversation.analyze.failed', level=logging.ERROR, error=exc, username=conv['username'])
                if exc.authentication:
                    self.pause_rule(task, str(exc))
                result["error"] = str(exc)
            except Exception as exc:
                diagnostic_event('summary.conversation.analyze.failed', level=logging.ERROR, error=exc, username=conv['username'])
                result["error"] = "资料解析失败，请检查附件格式后重试"
        results = state["results"] + [result]
        self.check(task["id"])
        self.update_task(task["id"], results=results, progress=round(5 + 85 * (index + 1) / len(state["conversations"])))
        return {"results": results, "index": index + 1}

    @observed('summary.graph_overview', id_field='task_id')
    async def graph_overview(self, state):
        task = self.check(state["task_id"])
        if task["kind"] == "alert":
            return {"overview": {}}
        self.update_task(task["id"], stage="整理总结结果", progress=92)
        successful = [x for x in state["results"] if x.get("summary")]
        if len(successful) == 1:
            return {"overview": successful[0]["summary"]}
        if not successful:
            return {"overview": {"overview": "没有成功分析的会话"}}
        # 保留每个会话的概述，不能只从话题条目拼装，以免漏掉空话题列表的有效概述。
        summaries = [{**r["summary"], "overview": r["name"] + "：" + r["summary"]["overview"]} for r in successful]
        allowed = {s["source"] for r in successful for s in r["sources"]}
        return {"overview": await self.merge_summaries(task, summaries, allowed, "overview")}

    @observed('summary.pause_rule', id_field='task_id')
    def pause_rule(self, task, error):
        rule = self.store.get("rule", task["rule_id"])
        if rule:
            self.store.put("rule", rule | {"enabled": False, "error": error}, id=rule["id"])

    @observed('summary.execute', id_field='task_id', execution=True)
    async def execute(self, id):
        from .providers import audit_task_id
        from langgraph.graph import StateGraph, START, END
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        task = self.check(id)
        self.active_id = id
        self.update_task(id, status="running", error="", attempts=task.get("attempts", 0) + 1, retry_at=0, started_at=task.get("started_at") or time.time(), finished_at=None)
        graph = StateGraph(GraphState)
        graph.add_node("read", self.graph_read)
        graph.add_node("analyze", self.graph_analyze)
        graph.add_node("overview", self.graph_overview)
        graph.add_edge(START, "read")
        graph.add_conditional_edges("read", lambda s: "analyze" if s["conversations"] else "overview")
        graph.add_conditional_edges("analyze", lambda s: "analyze" if s["index"] < len(s["conversations"]) else "overview")
        graph.add_edge("overview", END)
        config = {"configurable": {"thread_id": id}, "recursion_limit": 1000, "callbacks": []}
        try:
            audit_token = audit_task_id.set(id)
            from langsmith import tracing_context
            async with AsyncSqliteSaver.from_conn_string(str(self.store.root / "checkpoints.sqlite3")) as saver:
                compiled = graph.compile(checkpointer=saver)
                existing = await compiled.aget_state(config)
                diagnostic_event('summary.execution.resume', task_id=id, cached=bool(existing.values), index=existing.values.get('index',0))
                with tracing_context(enabled=False):
                    state = await compiled.ainvoke(None if existing.values else {"task_id": id}, config)
            self.check(id)
            self.finalize(task, state)
        except TaskCancelled:
            if not self.stopping:
                self.update_task(id, status="cancelled", stage="已取消")
        except Exception as exc:
            diagnostic_id = new_id()
            diagnostic_event('summary.execution.failed', level=logging.ERROR, error=exc, task_id=id, diagnostic_id=diagnostic_id)
            error = str(exc) if isinstance(exc, ProviderFailure) else "任务执行失败，可重试恢复已完成阶段"
            self.update_task(id, status="failed", error=error, stage="执行失败", diagnostic_id=diagnostic_id)
            self.schedule_retry(id)
        finally:
            audit_task_id.reset(audit_token)
            if self.active_id == id:
                self.active_id = None
            if task["account"] in self.deleted_accounts:
                await self.reset_graph(id)

    @observed('summary.cancel_task', id_field='task_id')
    async def cancel_task(self, id):
        self.update_task(id, cancel_requested=True, retry_at=0, status="cancelled", stage="已取消")
        if self.active_id == id and self.worker and not self.worker.done():
            self.worker.cancel()
            await asyncio.gather(self.worker, return_exceptions=True)

    @observed('summary.schedule_retry', id_field='task_id')
    def schedule_retry(self, id):
        task = self.store.get("task", id)
        if not task or not task["rule_id"]:
            return
        rule = self.store.get("rule", task["rule_id"])
        if not rule or not rule["enabled"] or rule["revision"] != task["rule_revision"]:
            return
        if task.get("attempts", 0) >= 3:
            self.pause_rule(task, "任务连续失败 3 次，已暂停；请检查失败原因后重新启用")
            return
        retry_at = time.time() + 60 * (2 ** max(0, task.get("attempts", 1) - 1))
        diagnostic_event('summary.retry.scheduled', task_id=id, rule_id=rule['id'], wait_seconds=retry_at-time.time(), attempt=task.get('attempts', 0)+1)
        self.update_task(id, retry_at=retry_at, stage="执行失败，等待自动重试")
        self.store.put("rule", rule | {"next_due": max(rule["next_due"], retry_at + 5)}, id=rule["id"])

    @observed('summary.finalize', id_field='task_id')
    def finalize(self, task, state):
        results = state.get("results", [])
        failed = [x for x in results if x.get("error")]
        status = "partial" if failed and any(x.get("summary") for x in results) else "failed" if failed else "completed"
        # 结果与通知先持久化，检查点后推进；通知具有稳定唯一键，恢复重放不会重复创建。
        self.update_task(task["id"], results=results, overview=state.get("overview", {}))
        if task["kind"] == "alert":
            for result in results:
                matches = result.get("summary", {}).get("matches", [])
                new_matches = []
                sources = {x["source"]: x for x in result["sources"]}
                for match in matches:
                    for source in match["sources"]:
                        key = f"{task['rule_id']}:{source}"
                        existing = self.store.get("alert", key)
                        if existing:
                            if existing.get("task_id") == task["id"] and not existing.get("hidden"):
                                new_matches.append(existing)
                            continue
                        alert = self.store.put("alert", {"task_id": task["id"], "rule_id": task["rule_id"], "reason": match["reason"], "name": result["name"], **sources[source]}, id=key, account=task["account"])
                        new_matches.append(alert)
                if new_matches:
                    diagnostic_event('summary.alert.matches', task_id=task['id'], rule_id=task['rule_id'], matches=len(new_matches), count=len(matches))
                    first = new_matches[0]
                    self.notify(task, result["name"], "；".join(dict.fromkeys(m["reason"] for m in new_matches)), first, f"alert:{task['id']}:{result['username']}")
        elif any(x.get("summary") and x["count"] for x in results):
            self.notify(task, "AI 总结已完成", f"已处理 {len(results) - len(failed)} 个会话" + (f"，{len(failed)} 个失败" if failed else ""), {}, f"summary:{task['id']}")
        rule = self.store.get("rule", task["rule_id"]) if task["rule_id"] else None
        if rule and rule.get("revision") == task["rule_revision"]:
            cursors = dict(rule["cursors"])
            for result in results:
                if not result["error"] and result.get("cursor"):
                    cursors[result["username"]] = result["cursor"]
            self.store.put("rule", rule | {"cursors": cursors, "last_task": task["id"], "error": "部分会话处理失败，请查看任务" if failed else ""}, id=rule["id"])
            diagnostic_event('summary.rule.checkpoint.committed', rule_id=rule['id'], count=len(results)-len(failed), failed_count=len(failed), committed=True)
        self.update_task(task["id"], status=status, stage="处理完成" if not failed else "部分资料处理失败", progress=100,
                         error="；".join(x["name"] + "：" + x["error"] for x in failed))
        if failed:
            self.schedule_retry(task["id"])

    @observed('summary.notify', id_field='task_id')
    def notify(self, task, title, body, source, key):
        if task["notify"]:
            hidden = task["hide_content"]
            self.store.event(task["account"], "notification", {"title": "有新的 AI 提醒" if hidden else title,
                "body": "打开应用查看" if hidden else body[:240], "target": {"account": task["account"], "task_id": task["id"], "username": source.get("username", ""), "anchor": source.get("anchor", "")}}, key)

    @observed('summary.save_rule', id_field='rule_id')
    async def save_rule(self, options, id=None):
        rule = RuleInput.model_validate(options).model_dump()
        old = self.store.get("rule", id) if id else None
        changed_scope = not old or old["account"] != rule["account"] or old["conversations"] != rule["conversations"]
        reset_baseline = changed_scope or (rule["enabled"] and not old.get("enabled", False))
        rule["revision"] = (old or {}).get("revision", 0) + 1
        rule["cursors"] = (old or {}).get("cursors", {})
        rule["error"] = ""
        if rule["enabled"]:
            self.snapshot_models(rule)
        if reset_baseline:
            end = int(time.time())
            rule["cursors"] = {}
            for username in rule["conversations"]:
                conv = await asyncio.to_thread(self.reader, rule["account"], username, end, end, None, rule["kind"] == "alert" and rule["enabled"])
                rule["cursors"][username] = advance_cursor(conv["messages"], {"time": end, "ids": []})
        rule["next_due"] = next_due(rule)
        return self.store.put("rule", rule, id=id)

    @observed('summary.run_rule', id_field='rule_id')
    async def run_rule(self, rule, force=False):
        lock = self.rule_locks.setdefault(rule["id"], asyncio.Lock())
        async with lock:
            return await self._run_rule(rule, force)

    async def _run_rule(self, rule, force=False):
        if any(t.get("rule_id") == rule["id"] for t in self.store.tasks_in_status(["queued", "running"])):
            diagnostic_event('summary.rule.skipped', rule_id=rule['id'], reason_code='active_task')
            return None
        options = TaskInput.model_validate(rule).model_dump()
        end = int(time.time()) - 1
        options["range"]["end"] = min(options["range"].get("end") or end, end)
        if options["range"]["mode"] == "hours":
            options["range"]["start"] = max(0, end - int(options["range"]["hours"] * 3600))
        prepared = await self.read_conversations(options, rule)
        latest = self.store.get("rule", rule["id"])
        if latest and latest.get("revision") != rule.get("revision"):
            diagnostic_event('summary.rule.skipped', rule_id=rule['id'], reason_code='revision_changed')
            return None
        if any(x.get("error") for x in prepared):
            raise ValueError("；".join(x["error"] for x in prepared if x.get("error")))
        new_count = sum(len(filter_after(c["messages"], rule["cursors"].get(c["username"], {"time": 0, "ids": []}))) for c in prepared)
        if not new_count or (not force and rule["trigger"] == "count" and new_count < rule["threshold"]):
            diagnostic_event('summary.rule.skipped', rule_id=rule['id'], reason_code='no_new_messages' if not new_count else 'below_threshold', count=new_count)
            return None
        return self.create_task(options, rule, prepared)

    async def scheduler(self):
        while not self.stopping:
            try:
                if self.worker is None or self.worker.done():
                    for task in self.store.tasks_in_status(["failed", "partial"]):
                        if task["status"] in {"failed", "partial"} and task.get("retry_at") and task["retry_at"] <= time.time():
                            rule = self.store.get("rule", task["rule_id"])
                            if rule and rule["enabled"] and rule["revision"] == task["rule_revision"]:
                                await self.reset_graph(task["id"])
                                self.update_task(task["id"], status="queued", retry_at=0)
                    pending = self.store.tasks_in_status(["queued", "running"])
                    if pending:
                        self.worker = asyncio.create_task(self.execute(pending[-1]["id"]))
                for rule in self.store.list("rule"):
                    if not rule["enabled"] or rule["next_due"] > time.time():
                        continue
                    try:
                        await self.run_rule(rule)
                        failures.recovered('summary.rule.'+rule['id'])
                        latest = self.store.get("rule", rule["id"])
                        if latest and latest["revision"] == rule["revision"]:
                            self.store.put("rule", latest | {"next_due": next_due(rule)}, id=rule["id"])
                    except Exception as exc:
                        failures.report('summary.rule.'+rule['id'], exc)
                        latest = self.store.get("rule", rule["id"])
                        if latest and latest["revision"] == rule["revision"]:
                            self.store.put("rule", latest | {"next_due": time.time() + max(60, rule["interval_seconds"]), "error": str(exc) if isinstance(exc, (ValueError, ProviderFailure)) else "自动任务暂时失败，将重试"}, id=rule["id"])
                failures.recovered('summary.scheduler')
            except Exception as exc:
                failures.report('summary.scheduler', exc)
            await asyncio.sleep(2)

    @observed('summary.start', id_field='task_id')
    def start(self):
        if self.loop_task is None:
            self.stopping = False
            self.loop_task = asyncio.create_task(self.scheduler())

    @observed('summary.stop', id_field='task_id')
    async def stop(self):
        self.stopping = True
        for task in (self.loop_task, self.worker):
            if task:
                task.cancel()
        await asyncio.gather(*(t for t in (self.loop_task, self.worker) if t), return_exceptions=True)
        self.loop_task = self.worker = None

    @observed('summary.reset_graph', id_field='task_id')
    async def reset_graph(self, id):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        async with AsyncSqliteSaver.from_conn_string(str(self.store.root / "checkpoints.sqlite3")) as saver:
            await saver.setup()
            await saver.adelete_thread(id)

    @observed('summary.purge_account', id_field='task_id')
    def purge_account(self, account):
        import sqlite3
        was_deleted = account in self.deleted_accounts
        self.deleted_accounts.add(account)
        from . import agent_service
        try:
            if agent_service._agent is not None:
                agent_service._agent.cancel_account(account)
        except Exception:
            if not was_deleted:
                self.deleted_accounts.discard(account)
            raise
        from ..local_search import service as local_search_service
        if local_search_service._service is not None:
            local_search_service._service.purge(account)
        ids = [t["id"] for t in self.store.list("task", account)]
        agent_ids = [r['id'] for r in self.store.list('agent_run', account)]
        self.store.purge_account(account)
        path = self.store.root / "checkpoints.sqlite3"
        if path.exists():
            with sqlite3.connect(path, timeout=30) as db:
                tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ("checkpoints", "writes"):
                    if table in tables:
                        db.executemany(f"DELETE FROM {table} WHERE thread_id=?", [(id,) for id in ids])
        agent_path = self.store.root / 'agent_checkpoints.sqlite3'
        if agent_path.exists():
            with sqlite3.connect(agent_path, timeout=30) as db:
                tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('checkpoints', 'writes'):
                    if table in tables:
                        db.executemany(f'DELETE FROM {table} WHERE thread_id=?', [(id,) for id in agent_ids])
        deep_path = self.store.root / 'deepagents_checkpoints.sqlite3'
        if deep_path.exists():
            # 历史清理可能已删掉 agent_run，只留下以账号开头的孤儿检查点。
            prefix = f'{account}:'
            with sqlite3.connect(deep_path, timeout=30) as db:
                tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                for table in ('checkpoints', 'writes'):
                    if table in tables:
                        db.execute(f'DELETE FROM {table} WHERE substr(thread_id,1,?)=?', (len(prefix), prefix))


_service = None


def get_ai_service():
    global _service
    if _service is None:
        _service = AIService()
    return _service
