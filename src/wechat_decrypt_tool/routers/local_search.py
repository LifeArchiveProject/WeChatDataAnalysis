"""本机语义检索接口；所有账号参数在入口规范化。"""
import asyncio
import json
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from .ai import local_only, account_name
from ..local_search.service import get_local_search
from ..local_search.catalog import model_dir, remote_spec

router = APIRouter(prefix='/api/ai/local-search', dependencies=[Depends(local_only)])

class Settings(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool = False
    agent_global: bool = False
    model: Literal['bge-small-zh','bge-base-zh','e5-small','remote-openai'] | None = None
    # 仅远端模型使用；地址、模型名与密钥都由账号配置覆盖目录预设。
    remote_endpoint: str | None = Field(default=None, max_length=2048)
    remote_model: str | None = Field(default=None, max_length=512)
    remote_api_key: str | None = Field(default=None, max_length=2048)
    remote_allow_self_signed: bool = False
    usernames: list[str] = Field(default_factory=list, max_length=2000)
    days: Literal[0,30,90] = 90
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)
    device: Literal['auto','cpu','cuda'] = 'auto'
    device_id: int = Field(default=0, ge=0, le=32)
    auto_update: bool = True
    read_batch_size: Literal[0, 100, 500, 1000, 2000] = 0
    @model_validator(mode='after')
    def ranges(self):
        if self.start is not None and self.end is not None and self.start > self.end: raise ValueError('开始时间不能晚于结束时间')
        self.usernames = list(dict.fromkeys(u.strip() for u in self.usernames if u.strip()))
        return self

class ImportBody(BaseModel):
    path: str

class RemoteTestBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    endpoint: str = Field(max_length=2048)
    model: str = Field(default='', max_length=512)
    api_key: str = Field(default='', max_length=2048)
    allow_self_signed: bool = False

@router.post('/remote/test')
async def remote_test(body: RemoteTestBody):
    """「测试连接」：列出服务上的模型并探测向量维度，错误文案直接给用户照着改。"""
    spec = remote_spec('remote-openai', body.endpoint, body.model, body.api_key, body.allow_self_signed)
    probed = await asyncio.to_thread(get_local_search().remote_probe, spec)
    if probed.get('models') and probed.get('model_listed') is False:
        probed['hint'] = '服务上没有这个模型名，请从上面的清单里选一个'
    return {'status': 'success' if probed.get('reachable') else 'error', **probed}

@router.get('/status')
def status(account: str | None = None):
    return get_local_search().status(account_name(account) if account else None)

@router.put('/settings')
async def settings(body: Settings, account: str):
    try:
        values = body.model_dump()
        if body.agent_global:
            from ..ai.agent_tools import ChatTools
            chats = await ChatTools().conversations(account_name(account))
            values.update(usernames=[c['username'] for c in chats], days=0, start=0, end=None, auto_update=True)
        return await get_local_search().configure(account_name(account), values)
    except ValueError as e: raise HTTPException(400, str(e)) from None

@router.get('/conversations')
async def conversations(account: str):
    from ..ai.agent_tools import ChatTools
    return await ChatTools().conversations(account_name(account))

@router.post('/models/{id}/{action}')
async def model_action(id: str, action: Literal['download','pause','delete','import'], body: ImportBody | None = None):
    service = get_local_search()
    try:
        if action == 'download': return await service.downloads.start(id)
        if action == 'pause': await service.downloads.pause(id)
        if action == 'delete':
            async with service.model_lock:
                referenced = any(c.get('model')==id or c.get('active',{}).get('model')==id for c in service.store.list('config'))
                if service.engine.key and service.engine.key[0] == str(model_dir(service.downloads.root,id)) and not referenced:
                    await asyncio.to_thread(service.engine.close)
                await service.downloads.delete(id, referenced)
        if action == 'import':
            if not body: raise ValueError('请选择模型目录')
            await service.downloads.import_model(id, body.path)
        return {'ok':True}
    except ValueError as e: raise HTTPException(400,str(e)) from None

@router.post('/index/{action}')
async def index_action(action: Literal['build','rebuild','pause','resume','clear'], account: str, job_id: str | None = None):
    service, account = get_local_search(), account_name(account)
    try:
        if action in {'build','rebuild'}: return await service.build(account, action=='rebuild')
        if action == 'pause': await service.pause_account(account)
        if action == 'resume': return await service.resume(account, job_id)
        if action == 'clear': await service.clear(account)
        return {'ok':True}
    except ValueError as e: raise HTTPException(400,str(e)) from None

@router.post('/device/recheck')
async def recheck(account: str):
    service = get_local_search()
    cfg = service.config(account_name(account))
    def reset():
        with service.engine.lock:
            service.engine.close()
            service.engine.gpu_failed = False
    await asyncio.to_thread(reset)
    try:
        await asyncio.to_thread(service.engine.encode, model_dir(service.downloads.root,cfg['model']), remote_spec(cfg['model'],cfg.get('remote_endpoint'),cfg.get('remote_model'),cfg.get('remote_api_key'),cfg.get('remote_allow_self_signed'),cfg.get('remote_dimension')), ['设备检测'],cfg['device'],cfg['device_id'])
    except Exception: raise HTTPException(400,'设备检测未完成，请先准备模型和运行组件') from None
    return service.engine.status

@router.get('/device/list')
async def list_devices():
    from ..local_search.gpu import gpu_devices
    return await asyncio.to_thread(gpu_devices)

@router.post('/gpu/{action}')
async def gpu_action(action: Literal['download','pause','import'], body: ImportBody | None = None):
    gpu = get_local_search().gpu
    try:
        if action == 'pause': await gpu.pause()
        else:
            if action == 'import' and not body: raise ValueError('请选择离线组件目录')
            await gpu.start(body.path if action == 'import' else None)
        return gpu.status()
    except ValueError as e: raise HTTPException(400,str(e)) from None

@router.get('/events')
async def events(request: Request, account: str | None = None, after: int = 0):
    account = account_name(account) if account else None
    try: after=max(after,int(request.headers.get('last-event-id','0')))
    except ValueError: pass
    async def stream():
        nonlocal after
        while not await request.is_disconnected():
            rows = get_local_search().store.events(after)
            for event in rows:
                after = event['id']
                if event['account'] and event['account'] != account: continue
                yield f"id: {after}\ndata: {json.dumps(event,ensure_ascii=False)}\n\n"
            if not rows: yield ': heartbeat\n\n'
            await asyncio.sleep(1)
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'Cache-Control':'no-cache'})
