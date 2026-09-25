import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from wechat_decrypt_tool.ai.storage import AIStore
from wechat_decrypt_tool.ai.service import AIService
from wechat_decrypt_tool.routers import ai


def test_all_presets_can_be_created_read_and_edited(tmp_path):
    service = AIService(AIStore(tmp_path))
    app = FastAPI(); app.include_router(ai.router)

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://localhost") as client:
            presets = (await client.get("/api/ai/settings")).json()["presets"]
            assert len(presets) == 16
            assert {p["provider"] for p in presets} == {"deepseek", "xiaomi", "claude", "kimi", "custom", "openai", "gemini", "qwen", "zhipu", "doubao", "siliconflow", "openrouter", "requesty", "groq", "ollama", "lmstudio"}
            assert presets[-1]["provider"] == "custom"
            for preset in presets:
                assert "model" not in preset
                key = "" if preset["provider"] in {"ollama", "lmstudio"} else "private-key"
                response = await client.post("/api/ai/profiles", json={**preset, "api_key": key, "model": "upstream-model"})
                assert response.status_code == 200, response.text
                profile = response.json()
                assert profile["has_key"] == bool(key)
                edited = await client.put(f'/api/ai/profiles/{profile["id"]}', json={**preset, "name": "已编辑", "api_key": None, "model": "another-model"})
                assert edited.status_code == 200, edited.text
                assert service.store.get("profile", profile["id"])["api_key"] == key
            settings = await client.get("/api/ai/settings")
            assert "private-key" not in settings.text
            profiles = settings.json()["profiles"]
            assert len(profiles) == 16
            assert all(p["name"] == "已编辑" and p["model"] == "another-model" for p in profiles)
            assert {p["provider"] for p in profiles} == {p["provider"] for p in presets}
            assert (await client.post("/api/ai/profiles", json={**presets[0], "provider": "unknown", "model": "test"})).status_code == 422

    with patch.object(ai, "get_ai_service", return_value=service):
        asyncio.run(run())


def test_manual_capabilities_survive_save_reload_and_runtime_resolution(tmp_path):
    service = AIService(AIStore(tmp_path))
    service.models.metadata.data = {'openai':{'name':'OpenAI','models':{'fixture':{
        'limit':{'context':128000,'output':16384},'modalities':{'input':['text','image']},'tool_call':True}}}}
    app = FastAPI(); app.include_router(ai.router)
    body = {'provider':'openai','name':'测试','model':'fixture','base_url':'https://api.openai.com/v1',
            'model_overrides':{'context_window':64000,'vision':False,'tool_call':False}}
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app,client=('127.0.0.1',1)),base_url='http://localhost') as client:
            created = await client.post('/api/ai/profiles',json=body)
            assert created.status_code == 200, created.text
            saved = created.json()
            assert saved['context_window'] == 64000 and saved['vision'] is False
            loaded = (await client.get('/api/ai/settings')).json()['profiles'][0]
            assert loaded['model_overrides']['tool_call'] is False
            assert service.models.resolve(saved['id'])['model_metadata']['tool_call'] is False
            restored = await client.put('/api/ai/profiles/'+saved['id'],json={**body,'model_overrides':{}})
            assert restored.json()['context_window'] == 128000 and restored.json()['vision'] is True
    with patch.object(ai,'get_ai_service',return_value=service):
        asyncio.run(run())


def test_local_only_profiles_masking_and_defaults(tmp_path):
    service = AIService(AIStore(tmp_path))
    app = FastAPI(); app.include_router(ai.router)
    body = {"provider": "custom", "name": "本地", "base_url": "http://localhost:11434/v1", "protocol": "openai", "api_key": "private-key", "model": "test", "vision": False}
    async def run():
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            response = await client.post("/api/ai/profiles", json=body)
            assert response.status_code == 200, response.text
            id = response.json()["id"]
            assert "private-key" not in response.text
            assert response.json()["has_key"] is True
            settings = await client.get("/api/ai/settings")
            assert "private-key" not in settings.text
            update = await client.put(f"/api/ai/profiles/{id}", json={**body, "api_key": None})
            assert update.status_code == 200
            assert service.store.get("profile", id)["api_key"] == "private-key"
            changed = await client.put(f"/api/ai/profiles/{id}", json={**body, "base_url": "https://different.example/v1", "api_key": None})
            assert changed.status_code == 422
            assert service.store.get("profile", id)["base_url"] == body["base_url"]
            invalid = await client.put("/api/ai/defaults", json={"vision": id})
            assert invalid.status_code == 422
            valid = await client.put("/api/ai/defaults", json={"text": id})
            assert valid.status_code == 200
            remote_origin = await client.get("/api/ai/settings", headers={"Origin": "https://evil.example"})
            assert remote_origin.status_code == 403
        remote = httpx.ASGITransport(app=app, client=("192.168.1.10", 1234))
        async with httpx.AsyncClient(transport=remote, base_url="http://localhost") as client:
            assert (await client.get("/api/ai/settings")).status_code == 403
    with patch.object(ai, "get_ai_service", return_value=service):
        asyncio.run(run())


def test_profile_removal_pauses_inheriting_rules_and_account_guard(tmp_path):
    service = AIService(AIStore(tmp_path))
    service.store.put("profile", {"vision": False}, id="profile")
    service.store.put("defaults", {"text": "profile", "vision": ""}, id="global")
    service.store.put("rule", {"account": "one", "enabled": True, "profile_id": "", "vision_profile_id": "", "media": True}, id="rule")
    service.store.put("task", {"account": "one", "status": "completed"}, id="task")
    app = FastAPI(); app.include_router(ai.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://localhost") as client:
            assert (await client.get("/api/ai/tasks/task", params={"account": "two"})).status_code == 404
            assert (await client.delete("/api/ai/profiles/profile")).status_code == 200
            assert service.store.get("rule", "rule")["enabled"] is False
    with patch.object(ai, "get_ai_service", return_value=service), patch.object(ai, "account_name", side_effect=lambda x: x):
        asyncio.run(run())


def test_usage_audit_pagination_and_unknown_tokens(tmp_path):
    service = AIService(AIStore(tmp_path))
    service.store.put("usage", {"status": "success", "usage_known": True, "usage": {"input_tokens": 10, "output_tokens": 2}})
    service.store.put("usage", {"status": "failed", "usage_known": False, "usage": {}, "http_status": 401})
    app = FastAPI(); app.include_router(ai.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://localhost") as client:
            result = (await client.get("/api/ai/usage")).json()
            assert result == {"calls": 2, "input_tokens": 10, "output_tokens": 2, "failed_calls": 1, "unknown_usage_calls": 1}
            first = (await client.get("/api/ai/usage/records?limit=1")).json()
            second = (await client.get("/api/ai/usage/records?limit=1&offset=1")).json()
            assert len(first) == len(second) == 1 and first[0]["id"] != second[0]["id"]
    with patch.object(ai, "get_ai_service", return_value=service):
        asyncio.run(run())


def test_model_fetch_needs_no_name_or_model_and_blocks_saved_key_to_new_url(tmp_path):
    from unittest.mock import AsyncMock
    service = AIService(AIStore(tmp_path))
    service.models.catalog = AsyncMock(return_value=[{"id": "upstream-only", "vision": None}])
    service.store.put("profile", {"base_url": "https://example.com/v1", "protocol": "openai", "api_key": "private"}, id="p")
    app = FastAPI(); app.include_router(ai.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://localhost") as client:
            result = await client.post("/api/ai/models", json={"base_url": "https://example.com/v1", "profile_id": "p"})
            assert result.status_code == 200 and result.json()["models"] == ["upstream-only"]
            assert "private" not in result.text
            result = await client.post("/api/ai/models", json={"base_url": "https://different.example/v1", "profile_id": "p"})
            assert result.status_code == 422
            assert service.models.catalog.await_count == 1
    with patch.object(ai, "get_ai_service", return_value=service):
        asyncio.run(run())


def test_connection_result_uses_product_message_instead_of_model_reply(tmp_path):
    from unittest.mock import AsyncMock
    service = AIService(AIStore(tmp_path))
    service.models.invoke = AsyncMock(return_value="连接成功。图片的颜色是**深绿色**。")
    app = FastAPI(); app.include_router(ai.router)
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 1)), base_url="http://localhost") as client:
            for vision in (False, True):
                service.store.put("profile", {"vision": vision}, id="p")
                response = await client.post("/api/ai/profiles/p/test")
                assert response.status_code == 200
                data = response.json()
                assert data["message"].startswith("连接成功，模型已正常响应。")
                assert "深绿色" not in response.text and "**" not in response.text
                assert ("本次也测试了图片输入。" in data["message"]) == vision
                assert bool(service.models.invoke.call_args.kwargs["images"]) == vision
            service.models.invoke.return_value = ""
            assert (await client.post("/api/ai/profiles/p/test")).status_code == 400
    with patch.object(ai, "get_ai_service", return_value=service):
        asyncio.run(run())
