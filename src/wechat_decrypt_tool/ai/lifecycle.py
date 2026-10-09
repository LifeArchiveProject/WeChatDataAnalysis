"""AI 服务统一启停诊断，独立于其他后台服务的生命周期。"""
import logging
import threading
from typing import Any
from importlib.metadata import PackageNotFoundError, version

from .diagnostics import observed, event

STORE_MAINTENANCE_INTERVAL_SECONDS = 6 * 60 * 60
_maintenance_lock = threading.Lock()
_maintenance_stop: threading.Event | None = None
_maintenance_threads: list[threading.Thread] = []


def _maintain_store(store, name):
    """在后台回收过期事件并压缩数据库，避免大型遗留库拖慢启动。"""
    try:
        deduplicated, removed, freed = store.maintain()
        event('storage.maintenance.finished', component=name, events_deduplicated=deduplicated,
              events_removed=removed, bytes_freed=freed)
    except Exception as error:
        event('storage.maintenance.failed', level=logging.WARNING, component=name, error=error)


def _maintenance_loop(store: Any, name: str, stop: threading.Event,
                      interval: float = STORE_MAINTENANCE_INTERVAL_SECONDS) -> None:
    """定期维护存储；等待使用 stop，以便应用关闭时立即退出等待。"""
    while not stop.is_set():
        _maintain_store(store, name)
        stop.wait(max(0.1, interval))


def _start_store_maintenance(stores: tuple[tuple[str, Any], ...]) -> None:
    """启动一组唯一的维护线程，避免重复触发多个生命周期钩子。"""
    global _maintenance_stop, _maintenance_threads
    with _maintenance_lock:
        if _maintenance_stop is not None and any(thread.is_alive() for thread in _maintenance_threads):
            return
        _maintenance_stop = threading.Event()
        _maintenance_threads = []
        for name, store in stores:
            thread = threading.Thread(
                target=_maintenance_loop,
                args=(store, name, _maintenance_stop),
                name=f'ai-store-maintenance-{name}',
                daemon=True,
            )
            _maintenance_threads.append(thread)
            thread.start()


def _stop_store_maintenance() -> None:
    """通知维护线程停止，并等待短暂时间让正在执行的维护收尾。"""
    global _maintenance_stop, _maintenance_threads
    with _maintenance_lock:
        stop = _maintenance_stop
        threads = list(_maintenance_threads)
        _maintenance_stop = None
        _maintenance_threads = []
    if stop is None:
        return
    stop.set()
    for thread in threads:
        thread.join(timeout=2)


@observed('lifecycle.start')
async def start_services():
    for package in ('deepagents', 'langchain-openai', 'langchain-anthropic', 'langgraph', 'onnxruntime', 'sqlite-vec', 'tokenizers'):
        try:
            event('runtime.component', component=package, runtime=version(package))
        except PackageNotFoundError as error:
            event('runtime.component.missing', level=logging.WARNING, component=package, error=error)
    from .service import get_ai_service
    from .agent_service import get_agent_service
    from ..local_search.service import get_local_search
    get_ai_service().store.recover_interrupted_usage()
    get_ai_service().start()
    await get_agent_service().start()
    await get_local_search().start()
    _start_store_maintenance((('summary', get_ai_service().store), ('search', get_local_search().store)))


@observed('lifecycle.stop')
async def stop_services():
    from .service import get_ai_service
    from .agent_service import get_agent_service
    from ..local_search.service import get_local_search
    _stop_store_maintenance()
    for name, factory in (('search',get_local_search),('summary',get_ai_service),('agent',get_agent_service)):
        try:
            await factory().stop()
        except Exception as error:
            event('lifecycle.service.stop_failed', level=logging.ERROR, component=name, error=error)
    # Agent 与摘要共享业务库，全部工作线程退出后才关闭持久连接。
    for store in (get_ai_service().store, get_local_search().store):
        store.close()
