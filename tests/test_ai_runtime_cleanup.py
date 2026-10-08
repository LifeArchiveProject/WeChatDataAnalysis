"""运行自检必须主动释放持久连接，正常和异常路径均允许 Windows 清理临时目录。"""
import asyncio
import tempfile
from pathlib import Path

import pytest

from wechat_decrypt_tool.ai import runtime_check, storage, agent_service


def track_stores(monkeypatch):
    stores = []

    class TrackedStore(storage.AIStore):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # 保持强引用，避免依赖垃圾回收碰巧释放 SQLite 文件句柄。
            stores.append(self)

    monkeypatch.setattr(storage, 'AIStore', TrackedStore)
    return stores


def test_full_runtime_check_closes_owned_stores_before_temporary_directory_cleanup(monkeypatch):
    stores = track_stores(monkeypatch)
    report = runtime_check.check_runtime()
    assert report['ok'] and report['application_graph'] == 'deepagents-v3-one-call-no-query'
    assert {store.root.name for store in stores} == {'application', 'business'}
    assert all(store._db is None and not store.root.exists() for store in stores)


@pytest.mark.parametrize('phase', ['setup', 'submit', 'validation'])
def test_checkpoint_failure_stops_workers_closes_store_and_preserves_original_error(monkeypatch, phase):
    stores = track_stores(monkeypatch)
    services = []
    original_agent = agent_service.AgentService

    class TrackedAgent(original_agent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            services.append(self)

        async def submit(self, *args, **kwargs):
            if phase == 'submit':
                raise RuntimeError('模拟提交失败')
            return await super().submit(*args, **kwargs)

        def public_run(self, *args, **kwargs):
            if phase == 'validation':
                raise RuntimeError('模拟校验失败')
            return super().public_run(*args, **kwargs)

    monkeypatch.setattr(agent_service, 'AgentService', TrackedAgent)
    if phase == 'setup':
        original_put = storage.AIStore.put

        def failed_setup(self, kind, *args, **kwargs):
            if kind == 'defaults':
                raise RuntimeError('模拟配置失败')
            return original_put(self, kind, *args, **kwargs)

        monkeypatch.setattr(storage.AIStore, 'put', failed_setup)
    with tempfile.TemporaryDirectory(prefix='test-ai-runtime-cleanup-') as directory:
        with pytest.raises(RuntimeError, match='模拟'):
            asyncio.run(runtime_check._checkpoint(Path(directory)))
        assert stores and all(store._db is None for store in stores)
        assert all(service.stopping and all(worker.done() for worker in service.workers.values())
                   for service in services)
    assert not Path(directory).exists()
