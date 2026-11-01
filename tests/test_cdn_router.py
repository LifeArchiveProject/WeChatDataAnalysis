from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from wechat_decrypt_tool import cdn_image_service as svc
from wechat_decrypt_tool.routers.cdn import router as cdn_router
from wechat_decrypt_tool.routers.system import router as system_router


WXID = "wxid_router_test"
TOKEN = "v2.router-secret-token"


def _token_body(now: int = 1_000_000) -> Dict[str, Any]:
    return {
        "token": TOKEN,
        "tokenDuration": "medium",
        "issuedAt": now,
        "expiresAt": now + 259200,
        "expiresIn": 259200,
        "account": {"nickname": "昵称", "avatarUrl": None, "plan": "Free", "permanentPlan": "Free", "proExpiresAt": None},
        "quota": {"period": "day", "periodKey": "day:2026-09-05", "limitBytes": 52428800, "usedBytes": 0, "remainingBytes": 52428800, "resetsAt": now + 86400},
    }


class Worker:
    def __init__(self) -> None:
        self.routes: Dict[str, Any] = {}
        self.requests: list[httpx.Request] = []

    def set(self, path: str, handler: Any) -> None:
        self.routes[path] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self.routes.get(request.url.path)
        if handler is None:
            raise AssertionError(f"unexpected request {request.url}")
        if isinstance(handler, httpx.Response):
            return handler
        return handler(request)


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    worker = Worker()
    wxid_dir = tmp_path / "wechat" / WXID
    wxid_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(svc, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(svc, "_resolve_wxid_dir_for_image_key", lambda *a, **k: wxid_dir)
    monkeypatch.setattr(svc, "get_wechat_internal_global_config", lambda _d, file_name1: b"cfg")
    monkeypatch.setattr(svc, "_TOKEN_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(svc, "_last_token_request_at", 0.0)
    monkeypatch.setattr(svc, "_token_locks", {})
    monkeypatch.setattr(svc, "_state_cache", {})
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    monkeypatch.setattr(
        svc,
        "_make_async_client",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(worker), **kw),
    )

    app = FastAPI()
    app.include_router(cdn_router)
    app.include_router(system_router)
    with TestClient(app) as client:
        yield client, worker, data_dir


def test_plan_returns_200_with_error_when_worker_unreachable(env) -> None:
    client, worker, _ = env

    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    worker.set("/token", _down)

    resp = client.get("/api/cdn/plan", params={"account": "acct"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["error"]["code"] == "network_error"
    assert "message" in body["error"]
    assert "token" not in body


def test_plan_auto_connects_and_returns_snapshot(env) -> None:
    client, worker, data_dir = env
    worker.set("/token", httpx.Response(200, json=_token_body()))

    resp = client.get("/api/cdn/plan", params={"account": "acct"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["account"]["plan"] == "Free"
    assert body["quota"]["limitBytes"] == 52428800
    assert body["quotaSource"] == "token"
    assert "error" not in body
    assert TOKEN not in resp.text
    assert json.loads((data_dir / "cdn_account_state.json").read_text(encoding="utf-8"))[WXID]["token"] == TOKEN


def test_plan_refresh_calls_quota_and_surfaces_rate_limit(env) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(200, json=_token_body()))
    worker.set(
        "/quota",
        httpx.Response(429, json={"error": "slow", "code": "rate_limited"}, headers={"Retry-After": "5"}),
    )

    first = client.get("/api/cdn/plan", params={"account": "acct"})
    assert first.status_code == 200 and "error" not in first.json()

    resp = client.get("/api/cdn/plan", params={"account": "acct", "refresh": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["error"] == {"code": "rate_limited", "message": "slow", "retryAfterSeconds": 5}


def test_plan_unresolvable_account_is_200(env, monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = env

    def _boom(*_a, **_k):
        raise FileNotFoundError("no wxid")

    monkeypatch.setattr(svc, "_resolve_wxid_dir_for_image_key", _boom)
    resp = client.get("/api/cdn/plan", params={"account": "ghost"})
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
    assert resp.json()["error"]["code"] == "account_unresolved"


def test_connect_maps_worker_403(env) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(403, json={"error": "账号已冻结", "code": "account_frozen"}))

    resp = client.post("/api/cdn/connect", json={"account": "acct"})

    assert resp.status_code == 403
    assert resp.json()["detail"] == {"code": "account_frozen", "message": "账号已冻结"}
    assert client.get("/api/cdn/plan", params={"account": "acct"}).json()["frozen"] is True


def test_connect_maps_worker_429_with_retry_after(env) -> None:
    client, worker, _ = env
    worker.set(
        "/token",
        httpx.Response(429, json={"error": "too fast", "code": "rate_limited"}, headers={"Retry-After": "9"}),
    )
    resp = client.post("/api/cdn/connect", json={"account": "acct"})
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "9"
    assert resp.json()["detail"] == {"code": "rate_limited", "message": "too fast", "retryAfterSeconds": 9}


def test_connect_success_returns_snapshot(env) -> None:
    client, worker, _ = env
    body = _token_body()
    worker.set("/token", httpx.Response(200, json=body))
    worker.set("/quota", httpx.Response(200, json={"account": body["account"], "quota": body["quota"]}))
    resp = client.post("/api/cdn/connect", json={"account": "acct"})
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["quotaSource"] == "quota"
    assert TOKEN not in resp.text


@pytest.mark.parametrize(
    ("status", "code"),
    (
        (400, "invalid_redeem_code"),
        (409, "redeem_code_used"),
        (409, "plan_not_upgraded"),
        (410, "redeem_code_expired"),
        (410, "redeem_code_revoked"),
    ),
)
def test_redeem_status_mapping(env, status: int, code: str) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(200, json=_token_body()))
    worker.set("/redeem", httpx.Response(status, json={"error": "nope", "code": code}))

    resp = client.post("/api/cdn/redeem", json={"account": "acct", "code": "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"})

    assert resp.status_code == status
    assert resp.json()["detail"] == {"code": code, "message": "nope"}


def test_redeem_locked_includes_locked_until_and_retry_after(env) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(200, json=_token_body()))
    worker.set(
        "/redeem",
        httpx.Response(
            429,
            json={"error": "locked", "code": "redeem_locked", "lockedUntil": 1_086_400, "retryAfterSeconds": 86400, "remainingAttempts": 0},
            headers={"Retry-After": "86400"},
        ),
    )
    resp = client.post("/api/cdn/redeem", json={"account": "acct", "code": "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"})
    assert resp.status_code == 429
    assert resp.headers["Retry-After"] == "86400"
    assert resp.json()["detail"] == {
        "code": "redeem_locked",
        "message": "locked",
        "retryAfterSeconds": 86400,
        "lockedUntil": 1_086_400,
    }
    assert "remainingAttempts" not in resp.text


def test_redeem_invalid_format_is_400_without_worker_call(env) -> None:
    client, worker, _ = env
    resp = client.post("/api/cdn/redeem", json={"account": "acct", "code": "wx-abc"})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "invalid_redeem_code"
    assert worker.requests == []


def test_redeem_success_payload(env) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(200, json=_token_body()))
    body = {
        "redemption": {"plan": "Plus", "durationMonths": None, "redeemedAt": 1_000_000},
        "account": {"nickname": "昵称", "avatarUrl": None, "plan": "Plus", "permanentPlan": "Plus", "proExpiresAt": None},
        "quota": {"period": "month", "periodKey": "month:2026-09", "limitBytes": 10737418240, "usedBytes": 0, "remainingBytes": 10737418240, "resetsAt": 1_200_000},
    }
    worker.set("/redeem", httpx.Response(200, json=body))
    resp = client.post("/api/cdn/redeem", json={"account": "acct", "code": "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["redemption"] == body["redemption"]
    assert payload["account"]["plan"] == "Plus"
    assert payload["quota"]["limitBytes"] == 10737418240
    assert payload["snapshot"]["account"]["plan"] == "Plus"
    assert payload["snapshot"]["quotaSource"] == "redeem"
    assert TOKEN not in resp.text


def test_token_duration_endpoint(env) -> None:
    client, _, _ = env
    ok = client.post("/api/cdn/token_duration", json={"value": "long"})
    assert ok.status_code == 200
    assert ok.json()["tokenDuration"] == "long"
    assert svc.get_token_duration() == "long"
    bad = client.post("/api/cdn/token_duration", json={"value": "forever"})
    assert bad.status_code == 400


def test_system_cdn_image_status_and_toggle(env) -> None:
    client, worker, _ = env
    status = client.get("/api/system/cdn_image/status")
    assert status.status_code == 200
    assert status.json() == {"enabled": False, "tokenDuration": "medium", "plan": None}

    toggled = client.post("/api/system/cdn_image/toggle", json={"enabled": True, "tokenDuration": "short"})
    assert toggled.status_code == 200
    assert toggled.json() == {"status": "success", "enabled": True, "tokenDuration": "short"}

    with_plan = client.get("/api/system/cdn_image/status", params={"account": "acct"})
    assert with_plan.status_code == 200
    body = with_plan.json()
    assert body["enabled"] is True
    assert body["plan"]["connected"] is False
    assert body["plan"]["tokenDuration"] == "short"
    assert "dailyLimit" not in body
    assert worker.requests == []


def test_plan_honours_token_retry_after_between_polls(env) -> None:
    client, worker, _ = env
    worker.set(
        "/token",
        httpx.Response(429, json={"error": "too fast", "code": "rate_limited"}, headers={"Retry-After": "9"}),
    )

    first = client.get("/api/cdn/plan", params={"account": "acct"})
    assert first.status_code == 200
    assert first.json()["error"] == {"code": "rate_limited", "message": "too fast", "retryAfterSeconds": 9}
    assert len(worker.requests) == 1

    second = client.get("/api/cdn/plan", params={"account": "acct"})
    assert second.status_code == 200
    body = second.json()
    assert body["connected"] is False
    assert body["error"]["code"] == "rate_limited"
    assert body["error"]["retryAfterSeconds"] == 9
    assert body["tokenRetryUntil"] == 1_000_009
    assert len(worker.requests) == 1  # 窗口内轮询不再打 /token


def test_plan_backs_off_after_network_error(env) -> None:
    client, worker, _ = env

    def _down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    worker.set("/token", _down)
    for _ in range(3):
        resp = client.get("/api/cdn/plan", params={"account": "acct"})
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == "network_error"
        assert resp.json()["error"]["retryAfterSeconds"] > 0
    assert len(worker.requests) == 1


def test_connect_403_without_frozen_code_is_not_sticky(env) -> None:
    client, worker, _ = env
    worker.set("/token", httpx.Response(403, text="<html>blocked</html>", headers={"Content-Type": "text/html"}))

    resp = client.post("/api/cdn/connect", json={"account": "acct"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "http_403"
    assert client.get("/api/cdn/plan", params={"account": "acct"}).json()["frozen"] is False

    body = _token_body()
    worker.set("/token", httpx.Response(200, json=body))
    worker.set("/quota", httpx.Response(200, json={"account": body["account"], "quota": body["quota"]}))
    ok = client.post("/api/cdn/connect", json={"account": "acct"})
    assert ok.status_code == 200
    assert ok.json()["connected"] is True


def test_system_toggle_rejects_bad_duration_without_mutating_enabled(env) -> None:
    client, _, _ = env
    bad = client.post("/api/system/cdn_image/toggle", json={"enabled": True, "tokenDuration": "forever"})
    assert bad.status_code == 400
    status = client.get("/api/system/cdn_image/status")
    assert status.json() == {"enabled": False, "tokenDuration": "medium", "plan": None}
