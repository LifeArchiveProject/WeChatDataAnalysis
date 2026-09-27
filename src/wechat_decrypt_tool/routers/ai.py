from __future__ import annotations

import asyncio
import ipaddress
import json
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from ..ai.providers import PRESETS, ProviderFailure, public_profile, validate_url
from ..ai.schemas import Defaults, ModelListInput, ProviderInput, RuleInput, TaskInput
from ..ai.service import get_ai_service
from ..ai.model_selection import SelectedModel, selected_model
from ..ai.diagnostics import event as diagnostic_event
import logging
from ..chat_helpers import _resolve_account_dir


def local_only(request: Request):
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            raise ValueError()
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError()
        host = request.url.hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError()
    except (ValueError, AttributeError):
        raise HTTPException(403, "AI 服务仅允许本机应用访问") from None


router = APIRouter(prefix="/api/ai", dependencies=[Depends(local_only)])


@router.post('/diagnostics/events')
async def diagnostic_events(request: Request):
    from ..ai.diagnostics_http import ingest
    return await ingest(request)


def account_name(account):
    return _resolve_account_dir(account).name


def get_record(kind, id, account=None):
    record = get_ai_service().store.get(kind, id)
    if record is None or (account is not None and record.get("account") != account_name(account)):
        raise HTTPException(404, "记录不存在")
    return record


@router.get("/settings")
async def settings():
    service = get_ai_service()
    service.models.metadata.refresh_in_background()
    return {"presets": PRESETS, "profiles": [public_profile(service.models.metadata.enrich(p)) for p in service.store.list("profile")],
            "defaults": service.store.get("defaults", "global") or {"text": "", "vision": ""},
            "selected_model": selected_model(service.store)}


@router.put('/selected-model')
def save_selected_model(body: SelectedModel):
    service = get_ai_service()
    with service.store.lock:
        get_record('profile', body.profile_id)
        try:
            service.models.resolve_turn(body.profile_id, body.model_id, body.reasoning_effort, body.thinking_mode, body.thinking_budget)
        except ProviderFailure as exc:
            raise HTTPException(422, str(exc)) from None
        choice = body.model_dump(exclude={key for key in ('thinking_mode', 'thinking_budget') if getattr(body, key) is None})
        service.store.put('selected_model', choice, id='global')
    return choice


@router.get('/model-metadata')
async def model_metadata(provider: str, model: str, base_url: str = '', protocol: str = 'openai'):
    catalog = get_ai_service().models.metadata
    await catalog.refresh()
    return {'metadata': catalog.automatic({'provider': provider, 'model': model, 'base_url': base_url, 'protocol': protocol})}


@router.get('/profiles/{id}/model-capabilities')
async def selected_model_capabilities(id: str, model_id: str = Query(min_length=1, max_length=200)):
    service = get_ai_service()
    profile = get_record('profile', id)
    await service.models.metadata.refresh()
    # 只获取已配置服务的能力，不调用聊天模型；换模型时不带原模型手动覆盖。
    if model_id != profile['model']:
        profile = {**profile, 'model': model_id, 'model_overrides': {}, 'context_window': None, 'vision': False}
    return {'metadata': service.models.metadata.enrich(profile)['model_metadata']}


def write_profile(body, id=None):
    service = get_ai_service()
    profile = body.model_dump()
    # 旧客户端没有来源标记时，明确传入的配置仍视为用户设置。
    if 'model_overrides' not in body.model_fields_set:
        profile['model_overrides'] = {key: profile[key] for key in ('vision', 'context_window')
                                      if key in body.model_fields_set and profile[key] is not None}
    profile = service.models.metadata.enrich(profile)
    try:
        validate_url(profile["base_url"])
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    old = get_record("profile", id) if id else {}
    if 'compaction_policy' not in body.model_fields_set and old.get('compaction_policy'):
        # 旧设置界面保存模型时保留通过 API 配置的上下文策略。
        profile['compaction_policy'] = old['compaction_policy']
    if profile["api_key"] is None:
        if old.get("api_key") and (profile["base_url"].rstrip("/") != old["base_url"].rstrip("/") or profile["protocol"] != old["protocol"]):
            raise HTTPException(422, "修改服务地址或协议后，请重新输入密钥再保存")
        profile["api_key"] = old.get("api_key", "")
    profile["revision"] = old.get("revision", 0) + 1
    saved = service.store.put('profile', profile, id=id)
    diagnostic_event('profile.saved', profile_id=saved['id'], revision=saved['revision'], model=saved['model'], protocol=saved['protocol'],
                     changed_fields=[k for k in profile if profile[k] != old.get(k)])
    return public_profile(saved)


@router.post("/profiles")
async def create_profile(body: ProviderInput):
    await get_ai_service().models.metadata.refresh()
    return write_profile(body)


@router.put("/profiles/{id}")
async def update_profile(id: str, body: ProviderInput):
    await get_ai_service().models.metadata.refresh()
    return write_profile(body, id)


@router.delete("/profiles/{id}")
def delete_profile(id: str):
    service = get_ai_service()
    get_record("profile", id)
    # 删除前完成旧默认迁移，确保删除后不会选中另一个服务。
    selected_model(service.store)
    defaults = service.store.get("defaults", "global") or {}
    inherited = [key for key in ("text", "vision") if defaults.get(key) == id]
    for rule in service.store.list("rule"):
        if id in {rule["profile_id"], rule["vision_profile_id"]} or ("text" in inherited and not rule["profile_id"]) or ("vision" in inherited and rule["media"] and not rule["vision_profile_id"]):
            service.store.put("rule", rule | {"enabled": False, "error": "所引用的 AI 配置已删除，请重新选择"}, id=rule["id"])
    service.store.delete("profile", id)
    # 再核对当前选择，避免删除期间的新选择被较早的快照覆盖。
    selected_model(service.store)
    diagnostic_event('profile.deleted', profile_id=id, count=len(inherited))
    service.store.put("defaults", {key: "" if defaults.get(key) == id else defaults.get(key, "") for key in ("text", "vision")}, id="global")
    return {"status": "success"}


@router.put("/defaults")
def save_defaults(body: Defaults):
    for key, value in body.model_dump().items():
        if value:
            profile = get_ai_service().models.metadata.enrich(get_record("profile", value))
            if key == "vision" and not profile["vision"]:
                raise HTTPException(422, "默认视觉模型必须启用图片能力")
    saved = get_ai_service().store.put('defaults', body.model_dump(), id='global')
    diagnostic_event('profile.defaults.saved', changed_fields=list(body.model_dump()))
    return saved


@router.get("/profiles/{id}/models")
async def models(id: str):
    try:
        details = await get_ai_service().models.catalog(get_record("profile", id))
        return {"models": [x["id"] for x in details], "model_details": details}
    except ProviderFailure as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/models")
async def draft_models(body: ModelListInput):
    profile = body.model_dump()
    try:
        validate_url(profile["base_url"])
        if profile["api_key"] is None and body.profile_id:
            saved = get_record("profile", body.profile_id)
            if profile["base_url"].rstrip("/") != saved["base_url"].rstrip("/") or profile["protocol"] != saved["protocol"]:
                raise HTTPException(422, "修改服务地址或协议后，请重新输入密钥再获取模型")
            profile["api_key"] = saved.get("api_key", "")
        details = await get_ai_service().models.catalog(profile)
        return {"models": [x["id"] for x in details], "model_details": details}
    except (ValueError, ProviderFailure) as exc:
        raise HTTPException(400, str(exc)) from None


@router.post("/profiles/{id}/test")
async def test_profile(id: str):
    diagnostic_event('profile.connection.started', profile_id=id)
    try:
        profile = get_ai_service().models.metadata.enrich(get_record("profile", id))
        images = None
        if profile.get("vision"):
            import io
            from PIL import Image
            from ..ai.media import image_url
            buffer = io.BytesIO()
            Image.new("RGB", (32, 32), "green").save(buffer, "PNG")
            images = [image_url(buffer.getvalue())]
        result = await get_ai_service().models.invoke(profile, "连接测试，请回答：连接成功" + ("，并说明图片的颜色" if images else ""), images=images)
        if not str(result or "").strip():
            raise ProviderFailure("模型未返回测试结果，请重试或更换模型。")
        # 模型回答只用于探测连接，不把测试素材和自由生成的内容展示给用户。
        message = "连接成功，模型已正常响应。"
        if images:
            message += "本次也测试了图片输入。"
        diagnostic_event('profile.connection.finished', profile_id=id, status='success', vision=bool(images))
        return {"status": "success", "message": message, "test_type": "image" if images else "text"}
    except ProviderFailure as exc:
        raise HTTPException(400, str(exc)) from None


@router.get("/usage")
def usage():
    records = get_ai_service().store.list("usage")
    return {"calls": len(records), "input_tokens": sum(x["usage"].get("input_tokens", 0) for x in records),
            "output_tokens": sum(x["usage"].get("output_tokens", 0) for x in records),
            "failed_calls": sum(x.get("status") == "failed" for x in records),
            "unknown_usage_calls": sum(not x.get("usage_known", bool(x.get("usage"))) for x in records)}


@router.get("/usage/records")
def usage_records(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return get_ai_service().store.list("usage", limit=limit, offset=offset)


@router.get("/conversations")
def conversations(account: str):
    from ..chat_export_service import get_chat_export_targets_preview
    try:
        return get_chat_export_targets_preview(account=account_name(account), include_hidden=True, include_official=False)["targets"]
    except Exception as error:
        diagnostic_event('conversations.failed', level=logging.ERROR, error=error)
        raise HTTPException(400, "获取完整会话列表失败，请检查账号数据源") from None


@router.post("/tasks")
def create_task(body: TaskInput):
    service = get_ai_service()
    with service.account_lifecycle_lock:
        data = body.model_dump()
        data["account"] = account_name(body.account)
        service.deleted_accounts.discard(data["account"])
        service.store.revoked_accounts.discard(data["account"])
        try:
            return service.create_task(data)
        except ProviderFailure as exc:
            raise HTTPException(422, str(exc)) from None


@router.get("/tasks")
def tasks(account: str, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    return get_ai_service().store.list("task", account_name(account), limit=limit, offset=offset, compact=True)


@router.get("/tasks/{id}")
def task(id: str, account: str):
    return get_record("task", id, account)


@router.post("/tasks/{id}/cancel")
async def cancel_task(id: str, account: str):
    record = get_record("task", id, account)
    if record["status"] not in {"queued", "running"}:
        return record
    await get_ai_service().cancel_task(id)
    return get_record("task", id, account)


@router.post("/tasks/{id}/retry")
async def retry_task(id: str, account: str):
    service = get_ai_service()
    record = get_record("task", id, account)
    if record["status"] not in {"failed", "partial", "cancelled"}:
        raise HTTPException(409, "当前任务不能重试")
    try:
        models = service.snapshot_models(record)
    except ProviderFailure as exc:
        raise HTTPException(422, str(exc)) from None
    await service.reset_graph(id)
    # 成功分段仍可复用；失败会话重新读取固定范围，以便附件补齐后继续。
    service.store.delete("prepared", id)
    if models != record["models"]:
        with service.store.connection() as db:
            db.execute("DELETE FROM records WHERE kind='partial' AND id LIKE ?", (id + ":%",))
    service.update_task(id, status="queued", cancel_requested=False, error="", attempts=0, retry_at=0, stage="等待重试",
                        models=models, previous_models=record.get("previous_models", []) + [record["models"]])
    diagnostic_event('summary.retry.requested', task_id=id, changed=models!=record['models'])
    return get_record("task", id, account)


@router.delete("/tasks/{id}")
async def delete_task(id: str, account: str):
    service = get_ai_service()
    record = get_record("task", id, account)
    if record["status"] in {"running", "queued"}:
        raise HTTPException(409, "请先取消任务")
    await service.reset_graph(id)
    service.store.delete("task", id)
    service.store.delete("prepared", id)
    with service.store.connection() as db:
        db.execute("DELETE FROM records WHERE kind='partial' AND id LIKE ?", (id + ":%",))
        db.execute("DELETE FROM events WHERE json_extract(body,'$.target.task_id')=? OR json_extract(body,'$.task_id')=?", (id, id))
    return {"status": "success"}


@router.get("/rules")
def rules(account: str):
    return get_ai_service().store.list("rule", account_name(account))


async def write_rule(body, id=None):
    data = body.model_dump()
    data["account"] = account_name(body.account)
    if id:
        get_record("rule", id, body.account)
    try:
        return await get_ai_service().save_rule(data, id)
    except (ValueError, ProviderFailure) as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/rules")
async def create_rule(body: RuleInput):
    return await write_rule(body)


@router.put("/rules/{id}")
async def update_rule(id: str, body: RuleInput):
    return await write_rule(body, id)


@router.delete("/rules/{id}")
def delete_rule(id: str, account: str):
    get_record("rule", id, account)
    get_ai_service().store.delete("rule", id)
    return {"status": "success"}


@router.post("/rules/{id}/run")
async def run_rule(id: str, account: str):
    try:
        return {"task": await get_ai_service().run_rule(get_record("rule", id, account), force=True)}
    except (ProviderFailure, ValueError) as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/alerts")
def alerts(account: str):
    return get_ai_service().store.list("alert", account_name(account))


@router.delete("/alerts")
def clear_alerts(account: str):
    service = get_ai_service()
    for alert in service.store.list("alert", account_name(account)):
        # 保留已命中的去重标记，避免清空历史后旧消息重新提醒。
        service.store.put("alert", {"hidden": True}, id=alert["id"], account=account_name(account))
    return {"status": "success"}


@router.get("/events")
async def events(request: Request, after: int = 0, account: str | None = None, notifications: bool = False):
    account = account_name(account) if account else None
    service = get_ai_service()
    try:
        after = max(after, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise HTTPException(422, "无效事件位置") from None
    initial_cursor = after if notifications or after else service.store.latest_event_id()
    async def stream():
        cursor = max(0, initial_cursor)
        while not await request.is_disconnected():
            for event in service.store.events(cursor, account, notifications):
                cursor = event["id"]
                yield f"id: {cursor}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield ": heartbeat\n\n"
            await asyncio.sleep(2)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/events/{id}/ack")
def acknowledge(id: int):
    get_ai_service().store.acknowledge(id)
    return {"status": "success"}
