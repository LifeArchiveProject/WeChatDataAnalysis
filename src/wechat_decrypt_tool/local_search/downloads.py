"""Hugging Face 匿名下载任务，暂停保留临时数据，恢复共享一次重试预算。"""
from ..ai.diagnostics import observed, event as diagnostic_event, context as diagnostic_context, new_id
import logging
import asyncio
import json
import multiprocessing as mp
import os
from pathlib import Path
import re
import shutil
import time

from .catalog import CATALOG, model_dir, model_spec, verify_model, file_hash
from ..ai.diagnostics import exception_fields

async def copy_import_file(source, destination):
    """暂停时等待当前文件复制退出，避免清理与后台写入竞争。"""
    temporary=destination.with_name(destination.name+'.importing')
    task=asyncio.create_task(asyncio.to_thread(shutil.copyfile,source,temporary))
    try: await asyncio.shield(task)
    except asyncio.CancelledError:
        await asyncio.gather(task,return_exceptions=True)
        raise
    temporary.replace(destination)


def download_worker(pipe, root, spec):
    try:
        _download_worker(pipe, root, spec)
    except Exception as error:
        # 依赖导入发生在下载循环之前，也要经 Pipe 保留实际失败类型。
        try:
            pipe.send({'error':'load', 'diagnostic_fields':exception_fields(error)})
        finally:
            pipe.close()


def _download_worker(pipe, root, spec):
    # 避免 SDK 输出临时签名地址或读取其他工具保存的登录凭据。
    os.environ.update(HF_HUB_DISABLE_IMPLICIT_TOKEN='1', HF_HUB_DISABLE_XET='1', HF_HUB_DISABLE_TELEMETRY='1', HF_HUB_DOWNLOAD_TIMEOUT='30')
    import logging
    logging.disable(logging.CRITICAL)
    from huggingface_hub import hf_hub_download
    import huggingface_hub.file_download as fd
    import huggingface_hub.utils._http as http
    from tqdm.auto import tqdm
    original_backoff, original_get = http._http_backoff_base, fd.http_get
    def no_backoff(*args, **kwargs):
        kwargs['max_retries'] = 0
        return original_backoff(*args, **kwargs)
    def no_get_retry(*args, **kwargs):
        kwargs['_nb_retries'] = 0
        return original_get(*args, **kwargs)
    http._http_backoff_base, fd.http_get = no_backoff, no_get_retry
    completed = 0
    class Progress(tqdm):
        last_send = 0
        def __init__(self,*args,**kwargs):
            self.sink=open(os.devnull,'w')
            kwargs['file']=self.sink
            super().__init__(*args,**kwargs)
        def close(self):
            super().close()
            if hasattr(self,'sink'): self.sink.close()
        def update(self, n=1):
            result = super().update(n)
            now = time.monotonic()
            if now - self.last_send > .25:
                pipe.send({'stage': 'downloading', 'bytes': completed + int(self.n)})
                self.last_send = now
            return result
    try:
        for item in spec['files']:
            pipe.send({'diagnostic_event': 'download.file.started', 'file': item['path'], 'total': item['size']})
            path = Path(root) / item['path']
            if path.is_file() and path.stat().st_size == item['size'] and file_hash(path) == item['sha256']:
                completed += item['size']
                pipe.send({'stage': 'downloading', 'bytes': completed})
                pipe.send({'diagnostic_event': 'download.file.finished', 'file': item['path'], 'bytes': item['size'], 'cached': True})
                continue
            if path.exists():
                path.unlink()
            hf_hub_download(spec['repo'], item['path'], revision=spec['revision'], token=False,
                endpoint='https://huggingface.co', local_dir=root, tqdm_class=Progress)
            completed += item['size']
            pipe.send({'diagnostic_event': 'download.file.finished', 'file': item['path'], 'bytes': item['size'], 'cached': False})
        pipe.send({'stage': 'verifying', 'bytes': completed})
        verify_model(root, spec, report=lambda name, fields: pipe.send({'diagnostic_event': name, **fields}))
        pipe.send({'stage': 'verified', 'bytes': completed})
    except Exception as error:
        response = getattr(error, 'response', None)
        status = getattr(response, 'status_code', None)
        headers = getattr(response, 'headers', {})
        retry = headers.get('retry-after', '')
        reset = re.search(r't=(\d+)', headers.get('ratelimit', ''))
        wait = int(retry) if str(retry).isdigit() else int(reset[1]) if reset else 0
        if retry and not str(retry).isdigit():
            from email.utils import parsedate_to_datetime
            try: wait=max(0,int(parsedate_to_datetime(retry).timestamp()-time.time()))
            except (ValueError,TypeError,OverflowError): pass
        category = 'network'
        if status == 429: category = 'rate_limit'
        elif status in (401, 403):
            # CDN 签名失效时重新解析固定仓库地址，不误报为登录要求。
            host = getattr(getattr(response, 'url', None), 'host', '')
            category = 'network' if host and host != 'huggingface.co' else 'access'
        elif status == 404: category = 'missing'
        elif isinstance(error, ValueError): category = 'checksum'
        elif isinstance(error, OSError) and getattr(error, 'errno', None) == 28: category = 'disk'
        pipe.send({'error': category, 'http_status': status, 'wait': wait, 'diagnostic_fields': exception_fields(error)})
    finally:
        pipe.close()


ERRORS = {'network': '网络连接中断，已保留下载进度', 'rate_limit': '下载服务限流，等待后继续',
          'access': '文件访问被拒绝，请检查网络或下载源状态', 'missing': '指定模型版本或文件不存在',
          'checksum': '模型完整性校验失败，请重试或导入完整模型', 'disk': '磁盘空间不足，请清理空间后继续',
          'load': '文件已下载，但本地加载测试失败'}


class ModelDownloads:
    def __init__(self, root, store, engine):
        self.root, self.store, self.engine = Path(root), store, engine
        self.root.mkdir(parents=True, exist_ok=True)
        self.tasks, self.stopping = {}, False
        self.cancelled = set()
        self.queue_lock = asyncio.Lock()

    def update(self, job, **values):
        changed = any(values.get(k, job.get(k)) != job.get(k) for k in ('status', 'stage'))
        job.update(values)
        job['updated'] = time.time()
        self.store.put('download', job, id=job['id'])
        self.store.event('', 'local_search_download', job, unique_key=f'download:{job["id"]}', replace=True)
        if changed:
            diagnostic_event('download.state', level=logging.ERROR if job.get('status')=='error' else logging.INFO,
                             model=job['id'], status=job.get('status'), phase=job.get('stage'), bytes=job.get('bytes'), attempt=job.get('attempt'))

    def models(self):
        values = []
        for spec in CATALOG:
            if spec.get('backend') == 'remote':
                values.append({**spec, 'downloaded': True, 'size': 0,
                               'job': None})
                continue
            root = model_dir(self.root, spec['id'])
            record = self.store.get('model', spec['id']) or {}
            available = record.get('revision') == spec['revision'] and all((root / f['path']).is_file() and (root / f['path']).stat().st_size == f['size'] for f in spec['files'])
            values.append({**spec, 'downloaded': available, 'size': sum(f['size'] for f in spec['files']),
                           'job': self.store.get('download', spec['id'])})
        return values

    def available(self, id):
        return next((m['downloaded'] for m in self.models() if m['id'] == id), False)

    @observed('download.start', id_field='task_id')
    async def start(self, id):
        spec = model_spec(id)
        if id in self.tasks and not self.tasks[id].done():
            return self.store.get('download', id)
        self.cancelled.discard(id)
        previous = self.store.get('download', id) or {}
        if previous.get('source') and previous.get('status')!='done': return await self.import_model(id,previous['source'])
        job = {'id': id, 'status': 'queued', 'stage': 'queued', 'bytes': previous.get('bytes', 0),
               'trace_id': previous.get('trace_id') or diagnostic_context.get().get('trace_id') or new_id(),
               'total': sum(f['size'] for f in spec['files']), 'attempt': 0, 'started': time.time(), 'speed': 0, 'error': ''}
        self.update(job)
        self.tasks[id] = asyncio.create_task(self.run(job, spec))
        return job

    @observed('download.run', execution=True)
    async def run(self, job, spec):
        process = None
        async with self.queue_lock:
            try:
                for attempt in range(1, 6):
                    self.update(job, status='running', stage='connecting', attempt=attempt, error='')
                    parent, child = mp.get_context('spawn').Pipe()
                    process = mp.get_context('spawn').Process(target=download_worker, args=(child, str(model_dir(self.root, spec['id'])), spec), daemon=True)
                    process.start()
                    child.close()
                    failure = None
                    last_bytes, last_time = job['bytes'], time.monotonic()
                    last_diagnostic = last_time
                    diagnostic_event('download.process.started', pid=getattr(process,'pid',None), model=spec['id'], attempt=attempt, bytes=job['bytes'])
                    while True:
                        if parent.poll():
                            try:
                                event = parent.recv()
                            except EOFError:
                                failure = {'error': 'network'}
                                break
                            if 'error' in event:
                                diagnostic_event('download.attempt.failed', level=logging.WARNING, reason_code=event['error'],
                                                 **{**event.get('diagnostic_fields',{}), 'http_status': event.get('http_status')})
                                failure = event
                                break
                            if event.get('diagnostic_event') in {'download.file.started', 'download.file.finished','model.file.verify.started','model.file.verify.finished'}:
                                diagnostic_event(event['diagnostic_event'], level=logging.ERROR if event.get('validation_status')=='failed' else logging.INFO,
                                                 file=event.get('file'), bytes=event.get('bytes'), total=event.get('total'), cached=event.get('cached'), validation_status=event.get('validation_status'))
                                continue
                            now = time.monotonic()
                            count = event.get('bytes', job['bytes'])
                            speed = max(0, (count - last_bytes) / max(.01, now - last_time))
                            self.update(job, stage=event['stage'], bytes=count, speed=round(speed))
                            if now-last_diagnostic >= 5 or event['stage'] in {'verifying','verified'}:
                                diagnostic_event('download.progress', phase=event['stage'], bytes=count, total=job['total'], duration_ms=(now-last_diagnostic)*1000)
                                last_diagnostic = now
                            last_bytes, last_time = count, now
                            if event['stage'] == 'verified':
                                break
                        elif not process.is_alive():
                            failure = {'error': 'network'}
                            break
                        await asyncio.sleep(.2)
                    process.join(timeout=1)
                    if process.is_alive(): process.terminate()
                    parent.close()
                    diagnostic_event('download.process.exited', pid=getattr(process,'pid',None), exit_code=getattr(process,'exitcode',None))
                    if not failure:
                        self.update(job, stage='loading', speed=0)
                        await asyncio.to_thread(self.engine.encode, model_dir(self.root, spec['id']), spec, ['本地检索'], 'cpu', 0, False, lambda: spec['id'] in self.cancelled)
                        self.store.put('model', {'revision': spec['revision']}, id=spec['id'])
                        self.update(job, status='done', stage='done', bytes=job['total'])
                        return
                    category = failure['error']
                    if category not in {'network', 'rate_limit'} or attempt == 5:
                        self.update(job, status='error', error=ERRORS[category], category=category, speed=0)
                        return
                    wait = failure.get('wait') or min(30, 2 ** attempt)
                    diagnostic_event('download.retry', level=logging.WARNING, attempt=attempt+1, wait_seconds=wait, reason_code=category)
                    self.update(job, stage='retry_wait', next_retry=time.time() + wait, error=ERRORS[category], speed=0)
                    await asyncio.sleep(wait)
            except asyncio.CancelledError:
                self.update(job, status='paused', stage='paused', speed=0)
                raise
            except Exception as error:
                diagnostic_event('download.failed', level=logging.ERROR, error=error)
                self.update(job, status='error', error=ERRORS['load'], category='load', speed=0)
            finally:
                if process and process.is_alive():
                    process.terminate()
                    process.join(timeout=3)

    @observed('download.pause')
    async def pause(self, id):
        self.cancelled.add(id)
        task = self.tasks.get(id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            job = self.store.get('download',id)
            if job and job['status'] in {'queued','running'}: self.update(job,status='paused',stage='paused',speed=0)

    @observed('download.delete')
    async def delete(self, id, referenced=False):
        if referenced:
            raise ValueError('该模型正在被账号使用，请先切换模型或清理其索引')
        await self.pause(id)
        target, root = model_dir(self.root, id).resolve(), self.root.resolve()
        if not target.is_relative_to(root):
            raise ValueError('无效模型目录')
        if target.exists():
            await asyncio.to_thread(shutil.rmtree, target)
        self.store.delete('model', id)
        self.store.delete('download', id)

    @observed('download.import_model', id_field='task_id')
    async def import_model(self, id, source):
        spec, source = model_spec(id), Path(source).resolve()
        await self.pause(id)
        if self.available(id): return
        if not source.is_dir(): raise ValueError('请选择完整的模型目录')
        self.cancelled.discard(id)
        job={'id':id,'status':'queued','stage':'queued','bytes':0,'total':sum(f['size'] for f in spec['files']),
             'source':str(source),'started':time.time(),'speed':0,'error':''}
        self.update(job)
        @observed('download.import.execute', execution=True)
        async def perform():
            async with self.queue_lock:
                try:
                    self.update(job,status='running',stage='verifying')
                    await asyncio.to_thread(verify_model, source, spec)
                    destination=model_dir(self.root,id)
                    for item in spec['files']:
                        diagnostic_event('download.import.file.started', file=item['path'], total=item['size'])
                        path=destination/item['path'];path.parent.mkdir(parents=True,exist_ok=True)
                        if path.resolve()!=(source/item['path']).resolve():
                            await copy_import_file(source/item['path'],path)
                        self.update(job,stage='importing',bytes=job['bytes']+item['size'])
                        diagnostic_event('download.import.file.finished', file=item['path'], bytes=item['size'])
                    self.update(job,stage='loading')
                    await asyncio.to_thread(self.engine.encode,destination,spec,['本地检索'],'cpu',0,False,lambda:id in self.cancelled)
                    self.store.put('model',{'revision':spec['revision']},id=id)
                    self.update(job,status='done',stage='done')
                except asyncio.CancelledError:
                    self.update(job,status='paused',stage='paused');raise
                except Exception as error:
                    diagnostic_event('download.import.failed', level=logging.ERROR, error=error)
                    self.update(job,status='error',stage='error',error='离线文件校验或加载失败，请确认目录包含完整的指定版本')
        self.tasks[id]=asyncio.create_task(perform())
        return job

    @observed('download.stop')
    async def stop(self):
        for id in list(self.tasks): await self.pause(id)
