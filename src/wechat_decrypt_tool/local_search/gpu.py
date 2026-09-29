"""版本化 NVIDIA 组件安装；不修改系统 CUDA 和 Python 环境。"""
from ..ai.diagnostics import observed, event as diagnostic_event, failures
import logging
import asyncio
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import zipfile

from .catalog import file_hash

MANIFEST_PATH = Path(__file__).parents[1] / 'resources/local_search_gpu.json'

def gpu_devices():
    # 当前加速组件仅面向 Windows；macOS 使用独立的 CPU 推理路径。
    if sys.platform != 'win32': return []
    try:
        r = subprocess.run(['nvidia-smi','--query-gpu=index,name,uuid,driver_version,memory.total','--format=csv,noheader,nounits'],
            capture_output=True,text=True,timeout=4,creationflags=0x08000000 if sys.platform=='win32' else 0)
        return [dict(zip(('id','name','uuid','driver','memory_mb'),[x.strip() for x in line.split(',')])) for line in r.stdout.splitlines() if line.count(',')==4]
    except (OSError,subprocess.TimeoutExpired) as error:
        failures.report('gpu.detect', error)
        return []


class GPUComponent:
    def __init__(self, root, store, engine):
        self.root, self.store, self.engine = Path(root),store,engine
        self.manifest=json.loads(MANIFEST_PATH.read_text())
        tag=f'cp{sys.version_info.major}{sys.version_info.minor}'
        self.files=[f for f in self.manifest['files'] if tag in f['name'] or 'py3-none' in f['name']]
        self.supported=sys.platform=='win32' and platform.machine().lower() in {'amd64','x86_64'} and any(tag in f['name'] for f in self.files)
        self.destination=self.root/self.manifest['id']/tag
        self.task=None
        self.cancelled=threading.Event()
        if self.installed(): self.engine.gpu_root=self.destination
        diagnostic_event('gpu.component.detected', component=self.manifest['id'], supported=self.supported, platform=sys.platform, arch=platform.machine())

    def installed(self):
        try:
            saved=json.loads((self.destination/'installed.json').read_text())
            return saved.get('id')==self.manifest['id'] and saved.get('files')==self.manifest['files'] and (self.destination/'onnxruntime/capi/onnxruntime_providers_cuda.dll').is_file()
        except (OSError,ValueError): return False

    def status(self):
        return {'installed':self.installed(),'supported':self.supported,'platform':sys.platform,
                'reason': 'macOS 使用 CPU 本地推理，无需 NVIDIA 加速组件' if sys.platform=='darwin' else '' if self.supported else '当前系统不支持此 NVIDIA 组件，仍可使用 CPU',
                'version':self.manifest['id'],
                'size':sum(f['size'] for f in self.files),'job':self.store.get('gpu_component','global')}

    def update(self, **values):
        job={**(self.store.get('gpu_component','global') or {}),**values,'updated':time.time()}
        self.store.put('gpu_component',job,id='global')
        self.store.event('','local_search_gpu',job, unique_key='local_search_gpu', replace=True)

    @observed('gpu.start')
    async def start(self, source=None):
        if not self.supported: raise ValueError('当前系统或 Python 架构不支持此 NVIDIA 组件，将继续使用 CPU')
        if self.task and not self.task.done(): return self.status()
        if self.installed(): return self.status()
        self.cancelled.clear()
        self.update(status='queued',bytes=0,total=sum(f['size'] for f in self.files),error='',started=time.time(),resume_on_start=False)
        self.task=asyncio.create_task(self.run(Path(source).resolve() if source else None))
        return self.status()

    @observed('gpu.run', execution=True)
    async def run(self, source):
        import httpx
        cache=self.root/'downloads'
        cache.mkdir(parents=True,exist_ok=True)
        completed=0
        installation=None
        try:
            async with httpx.AsyncClient(follow_redirects=True,timeout=30) as client:
                for f in self.files:
                    diagnostic_event('gpu.file.started', file=f['name'], total=f['size'])
                    path=cache/f['name']
                    if source:
                        original=source/f['name']
                        if not original.is_file(): raise ValueError('离线组件文件不完整')
                        if original.resolve()!=path.resolve():
                            from .downloads import copy_import_file
                            await copy_import_file(original,path)
                    elif not path.is_file() or path.stat().st_size!=f['size']:
                        for attempt in range(1,6):
                            size=path.stat().st_size if path.exists() else 0
                            diagnostic_event('gpu.file.resume', file=f['name'], bytes=size, attempt=attempt)
                            self.update(status='running',stage='downloading',attempt=attempt,bytes=completed+size)
                            try:
                                async with client.stream('GET',f['url'],headers={'Range':f'bytes={size}-'} if size else {}) as r:
                                    r.raise_for_status()
                                    if size and r.status_code!=206: size=0
                                    with path.open('ab' if size else 'wb') as output:
                                        sent=time.monotonic()
                                        log_sent=sent
                                        async for data in r.aiter_bytes(256*1024):
                                            output.write(data); size+=len(data)
                                            if time.monotonic()-sent>.3:
                                                self.update(bytes=completed+size)
                                                sent=time.monotonic()
                                            if time.monotonic()-log_sent>=5:
                                                diagnostic_event('gpu.file.progress', file=f['name'], bytes=size, total=f['size'])
                                                log_sent=time.monotonic()
                                break
                            except httpx.HTTPError as error:
                                diagnostic_event('gpu.file.failed', level=logging.WARNING, error=error, attempt=attempt, http_status=getattr(getattr(error,'response',None),'status_code',None))
                                if attempt==5: raise
                                wait=min(30,2**attempt)
                                diagnostic_event('gpu.file.retry', level=logging.WARNING, attempt=attempt+1, wait_seconds=wait)
                                self.update(stage='retry_wait',next_retry=time.time()+wait)
                                await asyncio.sleep(wait)
                    self.update(stage='verifying')
                    if path.stat().st_size!=f['size'] or await asyncio.to_thread(file_hash,path)!=f['sha256']:
                        path.unlink(missing_ok=True)
                        raise ValueError('NVIDIA 组件校验失败，已移除损坏文件，请重试')
                    completed+=f['size']
                    diagnostic_event('gpu.file.verified', file=f['name'], bytes=f['size'], validation_status='success')
            self.update(status='running',stage='installing',bytes=completed)
            installation=asyncio.create_task(asyncio.to_thread(self.install,cache))
            await asyncio.shield(installation)
            self.engine.gpu_root=self.destination
            self.engine.gpu_failed=False
            self.update(status='done',stage='done')
        except asyncio.CancelledError:
            self.cancelled.set()
            if installation: await asyncio.gather(installation,return_exceptions=True)
            self.update(status='paused',stage='paused')
            raise
        except Exception as e:
            diagnostic_event('gpu.failed', level=logging.ERROR, error=e)
            self.update(status='error',error=str(e) if isinstance(e,ValueError) else 'NVIDIA 组件下载或安装失败，CPU 仍可使用')

    @observed('gpu.install')
    def install(self, cache):
        stage=self.destination.with_name(self.destination.name+'.staging')
        stage.mkdir(parents=True,exist_ok=True)
        for f in self.files:
            if self.cancelled.is_set(): raise ValueError('组件安装已暂停')
            diagnostic_event('gpu.package.install.started', file=f['name'])
            with zipfile.ZipFile(cache/f['name']) as archive:
                for member in archive.infolist():
                    target=(stage/member.filename).resolve()
                    if not target.is_relative_to(stage.resolve()) or (member.external_attr>>16)&0o170000==0o120000:
                        raise ValueError('组件包含不安全的文件路径')
                    if self.cancelled.is_set(): raise ValueError('组件安装已暂停')
                    archive.extract(member,stage)
            diagnostic_event('gpu.package.install.finished', file=f['name'])
        (stage/'installed.json').write_text(json.dumps(self.manifest),encoding='utf-8')
        with self.engine.lock:
            if self.cancelled.is_set(): raise ValueError('组件安装已暂停')
            self.engine.close()
            if self.destination.exists():
                if not self.destination.resolve().is_relative_to(self.root.resolve()): raise ValueError('无效组件目录')
                shutil.rmtree(self.destination)
            stage.rename(self.destination)

    @observed('gpu.pause')
    async def pause(self):
        self.cancelled.set()
        if self.task and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task,return_exceptions=True)
