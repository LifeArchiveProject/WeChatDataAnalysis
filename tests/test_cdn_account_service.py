from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List

import httpx
import pytest

from wechat_decrypt_tool import cdn_image_service as svc


WXID = "wxid_cdn_test"
TOKEN_A = "v2.super-secret-token-AAAA"
TOKEN_B = "v2.super-secret-token-BBBB"
JPEG_FIXTURE = b"\xff\xd8\xff\xe0" + bytes(range(60)) + b"\xff\xd9"
AES_KEY_HEX = "ab" * 16


def _token_body(token: str = TOKEN_A, *, now: int = 1_000_000, expires_in: int = 259200) -> Dict[str, Any]:
    return {
        "token": token,
        "tokenDuration": "medium",
        "issuedAt": now,
        "expiresAt": now + expires_in,
        "expiresIn": expires_in,
        "account": {
            "nickname": "昵称",
            "avatarUrl": None,
            "plan": "Free",
            "permanentPlan": "Free",
            "proExpiresAt": None,
        },
        "quota": {
            "period": "day",
            "periodKey": "day:2026-09-05",
            "limitBytes": 52428800,
            "usedBytes": 0,
            "remainingBytes": 52428800,
            "resetsAt": now + 86400,
        },
    }


class FakeWorker:
    """可编程的 Worker：按路径排队响应，并记录每次请求。"""

    def __init__(self) -> None:
        self.requests: List[httpx.Request] = []
        self.handlers: Dict[str, List[Callable[[httpx.Request], httpx.Response]]] = {}
        self.default: Dict[str, Callable[[httpx.Request], httpx.Response]] = {}

    def queue(self, path: str, handler: Callable[[httpx.Request], httpx.Response] | httpx.Response) -> None:
        if isinstance(handler, httpx.Response):
            resp = handler
            handler = lambda _req, _resp=resp: _resp  # noqa: E731
        self.handlers.setdefault(path, []).append(handler)

    def always(self, path: str, handler: Callable[[httpx.Request], httpx.Response] | httpx.Response) -> None:
        if isinstance(handler, httpx.Response):
            resp = handler
            handler = lambda _req, _resp=resp: _resp  # noqa: E731
        self.default[path] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        queued = self.handlers.get(path) or []
        if queued:
            return queued.pop(0)(request)
        if path in self.default:
            return self.default[path](request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    def calls(self, path: str) -> List[httpx.Request]:
        return [r for r in self.requests if r.url.path == path]


@pytest.fixture
def worker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeWorker:
    fake = FakeWorker()
    wxid_dir = tmp_path / "wechat" / WXID
    wxid_dir.mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    monkeypatch.setattr(svc, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(svc, "_resolve_wxid_dir_for_image_key", lambda *a, **k: wxid_dir)
    monkeypatch.setattr(
        svc,
        "get_wechat_internal_global_config",
        lambda _dir, file_name1: b"CFG:" + file_name1.encode(),
    )
    monkeypatch.setattr(svc, "_TOKEN_MIN_INTERVAL_SECONDS", 0.0)
    monkeypatch.setattr(svc, "_last_token_request_at", 0.0)
    monkeypatch.setattr(svc, "_token_locks", {})
    monkeypatch.setattr(svc, "_state_cache", {})

    async def _yielding_handler(request: httpx.Request) -> httpx.Response:
        # 让每次「网络请求」都真的让出事件循环，并发测试才有交错。
        await asyncio.sleep(0)
        return fake(request)

    monkeypatch.setattr(
        svc,
        "_make_async_client",
        lambda **kw: httpx.AsyncClient(transport=httpx.MockTransport(_yielding_handler), **kw),
    )
    return fake


def _state_file(tmp_path: Path) -> Path:
    return tmp_path / "data" / "cdn_account_state.json"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# token
# ---------------------------------------------------------------------------


def test_token_issue_persists_state_and_never_logs_token(worker: FakeWorker, tmp_path: Path, caplog) -> None:
    worker.queue("/token", httpx.Response(200, json=_token_body()))
    caplog.set_level(logging.DEBUG, logger=svc.__name__)

    token = _run(svc.ensure_token("acct"))

    assert token == TOKEN_A
    req = worker.calls("/token")[0]
    assert req.method == "POST"
    assert b'name="weixinIDFolder"' in req.content
    assert WXID.encode() in req.content
    assert b'name="tokenDuration"' in req.content
    assert b"medium" in req.content
    assert b"CFG:global_config.crc" in req.content

    saved = json.loads(_state_file(tmp_path).read_text(encoding="utf-8"))
    entry = saved[WXID]
    assert entry["token"] == TOKEN_A
    assert entry["expiresAt"] == 1_000_000 + 259200
    assert entry["account"]["plan"] == "Free"
    assert entry["quota"]["limitBytes"] == 52428800
    assert entry["quotaSource"] == "token"

    assert TOKEN_A not in caplog.text
    assert any("CDN token" in rec.getMessage() for rec in caplog.records)

    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["connected"] is False  # expiresAt 是 fixture 里的旧时间戳
    assert snapshot["account"]["nickname"] == "昵称"
    assert "token" not in snapshot


def test_token_refresh_is_driven_by_expires_at(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(svc, "_now", lambda: clock["now"])
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A, now=1_000_000, expires_in=3600)))
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_B, now=1_003_400, expires_in=3600)))

    assert _run(svc.ensure_token("acct")) == TOKEN_A
    clock["now"] = 1_000_000 + 3600 - 400  # 还有 400 秒 > 300 秒余量
    assert _run(svc.ensure_token("acct")) == TOKEN_A
    assert len(worker.calls("/token")) == 1

    clock["now"] = 1_000_000 + 3600 - 200  # 进入 300 秒刷新窗口
    assert _run(svc.ensure_token("acct")) == TOKEN_B
    assert len(worker.calls("/token")) == 2


def test_legacy_quota_file_is_removed(worker: FakeWorker, tmp_path: Path) -> None:
    legacy = tmp_path / "data" / "cdn_image_quota.json"
    legacy.write_text("{}", encoding="utf-8")
    svc._legacy_cleanup_dirs.clear()
    svc.get_plan_snapshot("acct")
    assert not legacy.exists()


def test_config_unreadable_maps_to_cdn_error(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_dir, file_name1):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(svc, "get_wechat_internal_global_config", _boom)
    with pytest.raises(svc.CdnError) as excinfo:
        _run(svc.ensure_token("acct"))
    assert excinfo.value.code == "config_unreadable"
    assert worker.calls("/token") == []


# ---------------------------------------------------------------------------
# quota / 401 / 403
# ---------------------------------------------------------------------------


def test_quota_401_refreshes_token_once(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/quota", httpx.Response(401, json={"error": "bad", "code": "invalid_token"}))
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_B)))
    body = _token_body()
    body["account"]["plan"] = "Plus"
    worker.queue("/quota", httpx.Response(200, json={"account": body["account"], "quota": body["quota"]}))

    result = _run(svc.fetch_quota("acct", force=True))

    assert result["account"]["plan"] == "Plus"
    quota_calls = worker.calls("/quota")
    assert [r.headers["Authorization"] for r in quota_calls] == [f"Bearer {TOKEN_A}", f"Bearer {TOKEN_B}"]
    assert len(worker.calls("/token")) == 2
    assert svc.get_plan_snapshot("acct")["quotaSource"] == "quota"


def test_quota_uses_cache_when_fresh(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    _run(svc.ensure_token("acct"))
    result = _run(svc.fetch_quota("acct"))
    assert result["quota"]["limitBytes"] == 52428800
    assert worker.calls("/quota") == []


def test_403_marks_frozen_and_blocks_further_token_calls(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/quota", httpx.Response(403, json={"error": "frozen", "code": "account_frozen"}))

    with pytest.raises(svc.CdnAccountFrozenError):
        _run(svc.fetch_quota("acct", force=True))

    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["frozen"] is True
    assert snapshot["lastError"]["code"] == "account_frozen"

    with pytest.raises(svc.CdnAccountFrozenError):
        _run(svc.ensure_token("acct", force=False))
    with pytest.raises(svc.CdnAccountFrozenError):
        _run(svc.download_media("acct", "fileid-1", media_type="orig"))
    assert len(worker.calls("/token")) == 1


# ---------------------------------------------------------------------------
# download
# ---------------------------------------------------------------------------


def _download_ok(content: bytes, headers: Dict[str, str]) -> httpx.Response:
    base = {"Content-Type": "application/octet-stream", "Content-Length": str(len(content))}
    base.update(headers)
    return httpx.Response(200, content=content, headers=base)


def test_download_parses_quota_headers(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/download",
        _download_ok(
            JPEG_FIXTURE,
            {
                "X-WXCDN-Cache": "HIT",
                "X-Quota-Limit": "52428800",
                "X-Quota-Used": "1024",
                "X-Quota-Remaining": "52427776",
                "X-Quota-Reset": "1000500",
            },
        ),
    )

    data = _run(svc.download_media("acct", "file-1", media_type="orig"))
    assert data == JPEG_FIXTURE

    req = worker.calls("/download")[0]
    assert req.headers["Authorization"] == f"Bearer {TOKEN_A}"
    assert dict(req.url.params) == {"fileid": "file-1", "type": "orig"}

    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["quota"]["usedBytes"] == 1024
    assert snapshot["quota"]["remainingBytes"] == 52427776
    assert snapshot["quota"]["resetsAt"] == 1000500
    assert snapshot["quota"]["period"] == "day"  # 沿用 token 响应里的周期信息
    assert snapshot["quotaSource"] == "download"
    assert snapshot["lastError"] is None
    assert snapshot["recent"][-1] == {
        "at": 1_000_000,
        "type": "orig",
        "bytes": len(JPEG_FIXTURE),
        "cache": "HIT",
        "remainingAfter": 52427776,
    }


def test_download_unlimited_headers_become_none(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/download",
        _download_ok(
            JPEG_FIXTURE,
            {
                "X-WXCDN-Cache": "MISS",
                "X-Quota-Limit": "unlimited",
                "X-Quota-Used": "4096",
                "X-Quota-Remaining": "unlimited",
            },
        ),
    )
    _run(svc.download_media("acct", "file-2", media_type="normal"))
    quota = svc.get_plan_snapshot("acct")["quota"]
    assert quota["limitBytes"] is None
    assert quota["remainingBytes"] is None
    assert quota["usedBytes"] == 4096


def test_download_alias_keeps_signature(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", _download_ok(JPEG_FIXTURE, {}))
    data = _run(svc.download_original_image("acct", "file-3", aes_key_hex="", image_type="thumb"))
    assert data == JPEG_FIXTURE
    assert dict(worker.calls("/download")[0].url.params)["type"] == "thumb"


def test_download_401_refreshes_once(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", httpx.Response(401, json={"error": "x", "code": "invalid_token"}))
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_B)))
    worker.queue("/download", _download_ok(JPEG_FIXTURE, {}))

    data = _run(svc.download_media("acct", "file-4"))
    assert data == JPEG_FIXTURE
    auths = [r.headers["Authorization"] for r in worker.calls("/download")]
    assert auths == [f"Bearer {TOKEN_A}", f"Bearer {TOKEN_B}"]


def test_download_401_twice_raises_invalid_token(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.always("/download", httpx.Response(401, json={"error": "x", "code": "invalid_token"}))
    with pytest.raises(svc.CdnInvalidTokenError):
        _run(svc.download_media("acct", "file-5"))
    assert len(worker.calls("/download")) == 2


def test_download_quota_exceeded_carries_body_quota(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    quota = {
        "period": "day",
        "periodKey": "day:2026-09-05",
        "limitBytes": 52428800,
        "usedBytes": 52428800,
        "remainingBytes": 0,
        "resetsAt": 1_086_400,
    }
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/download",
        httpx.Response(429, json={"error": "额度不足", "code": "quota_exceeded", "quota": quota}),
    )
    with pytest.raises(svc.CdnQuotaExceededError) as excinfo:
        _run(svc.download_media("acct", "file-6"))
    assert excinfo.value.quota == quota
    assert excinfo.value.status == 429
    assert str(excinfo.value) == "额度不足"
    last = svc.get_plan_snapshot("acct")["lastError"]
    assert last["code"] == "quota_exceeded"
    assert last["quota"] == quota


def test_download_rate_limited_parses_retry_after(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/download",
        httpx.Response(
            429,
            json={"error": "slow down", "code": "rate_limited"},
            headers={"Retry-After": "7"},
        ),
    )
    with pytest.raises(svc.CdnRateLimitedError) as excinfo:
        _run(svc.download_media("acct", "file-7"))
    assert excinfo.value.retry_after == 7
    assert excinfo.value.headers() == {"Retry-After": "7"}


def test_download_media_type_validation(worker: FakeWorker) -> None:
    with pytest.raises(ValueError):
        _run(svc.download_media("acct", "file-8", media_type="bogus"))
    with pytest.raises(ValueError):
        _run(svc.download_media("acct", "", media_type="orig"))
    assert worker.requests == []


def _aes_ecb_encrypt(plain: bytes, key_hex: str) -> bytes:
    from Crypto.Cipher import AES
    from Crypto.Util import Padding

    return AES.new(bytes.fromhex(key_hex), AES.MODE_ECB).encrypt(Padding.pad(plain, AES.block_size))


def test_download_decrypts_locally_without_sending_key(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    encrypted = _aes_ecb_encrypt(JPEG_FIXTURE, AES_KEY_HEX)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", _download_ok(encrypted, {"X-WXCDN-Cache": "MISS"}))

    data = _run(svc.download_media("acct", "file-9", media_type="orig", aes_key_hex=AES_KEY_HEX))

    assert data == JPEG_FIXTURE
    calls = worker.calls("/download")
    assert len(calls) == 1
    assert "key" not in dict(calls[0].url.params)
    assert AES_KEY_HEX not in str(calls[0].url)


def test_download_falls_back_to_server_decrypt_when_local_result_is_garbage(
    worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    caplog.set_level(logging.DEBUG, logger=svc.__name__)
    wrong_key = "cd" * 16
    encrypted = _aes_ecb_encrypt(JPEG_FIXTURE, wrong_key)  # 用错的 key 本地解出来是垃圾
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", _download_ok(encrypted, {}))
    worker.queue("/download", _download_ok(JPEG_FIXTURE, {"X-WXCDN-Cache": "HIT"}))

    data = _run(svc.download_media("acct", "file-10", media_type="orig", aes_key_hex=AES_KEY_HEX))

    assert data == JPEG_FIXTURE
    calls = worker.calls("/download")
    assert len(calls) == 2
    assert "key" not in dict(calls[0].url.params)
    assert dict(calls[1].url.params) == {"fileid": "file-10", "type": "orig", "key": AES_KEY_HEX}
    assert any("回退服务端解密" in rec.getMessage() for rec in caplog.records)


def test_download_non_image_trusts_unpadded_local_decrypt(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    payload = b"%PDF-1.7 not an image but a document" * 3
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", _download_ok(_aes_ecb_encrypt(payload, AES_KEY_HEX), {}))
    data = _run(svc.download_media("acct", "file-11", media_type="file", aes_key_hex=AES_KEY_HEX))
    assert data == payload
    assert len(worker.calls("/download")) == 1


# ---------------------------------------------------------------------------
# redeem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        (" wx-7k9m p4rx-2v8d-q6yt-h3nc ", "7K9MP4RX2V8DQ6YTH3NC"),
        ("WX-7K9M-P4RX-2V8D-Q6YT-H3NC", "7K9MP4RX2V8DQ6YTH3NC"),
        ("wx-7K9M－P4RX－2V8D－Q6YT－H3NC", "7K9MP4RX2V8DQ6YTH3NC"),  # 全角连字符
        ("wx-7K9M-P4RX-2V8D-Q6YT-H3NC-extra", "7K9MP4RX2V8DQ6YTH3NC"),  # 截断到 20
        ("wx-OIL0-P4RX-2V8D-Q6YT-H3NC", "0110P4RX2V8DQ6YTH3NC"),  # O/I/L 纠正
        ("wx-7K9M-P4RX-2V8D-Q6YT-H3N!", "7K9MP4RX2V8DQ6YTH3N"),  # 非法字符剔除
        ("", ""),
    ),
)
def test_normalize_redeem_code(raw: str, expected: str) -> None:
    assert svc.normalize_redeem_code(raw) == expected


def test_redeem_rejects_short_code_without_calling_worker(worker: FakeWorker) -> None:
    with pytest.raises(svc.CdnRedeemError) as excinfo:
        _run(svc.redeem_code("acct", "wx-7K9M"))
    assert excinfo.value.code == "invalid_redeem_code"
    assert excinfo.value.status == 400
    assert worker.requests == []


def test_redeem_success_updates_account_and_quota(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    caplog.set_level(logging.DEBUG, logger=svc.__name__)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    body = {
        "redemption": {"plan": "Pro", "durationMonths": 1, "redeemedAt": 1_000_000},
        "account": {"nickname": "昵称", "avatarUrl": None, "plan": "Pro", "permanentPlan": "Free", "proExpiresAt": 1_100_000},
        "quota": {"period": "month", "periodKey": "month:2026-09", "limitBytes": 214748364800, "usedBytes": 0, "remainingBytes": 214748364800, "resetsAt": 1_200_000},
    }
    worker.queue("/redeem", httpx.Response(200, json=body))

    result = _run(svc.redeem_code("acct", " wx-7k9m p4rx-2v8d-q6yt-h3nc "))

    assert result == body
    req = worker.calls("/redeem")[0]
    assert json.loads(req.content) == {"code": "wx-7K9MP4RX2V8DQ6YTH3NC"}
    assert req.headers["Authorization"] == f"Bearer {TOKEN_A}"
    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["account"]["plan"] == "Pro"
    assert snapshot["quotaSource"] == "redeem"
    assert "7K9MP4RX2V8DQ6YTH3NC" not in caplog.text
    assert "7K9M...H3NC" in caplog.text


def test_redeem_locked_persists_and_short_circuits(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/redeem",
        httpx.Response(
            429,
            json={
                "error": "兑换功能因连续失败已临时锁定",
                "code": "redeem_locked",
                "lockedUntil": 1_086_400,
                "retryAfterSeconds": 86400,
            },
            headers={"Retry-After": "86400"},
        ),
    )

    with pytest.raises(svc.CdnRedeemError) as excinfo:
        _run(svc.redeem_code("acct", "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"))
    assert excinfo.value.code == "redeem_locked"
    assert excinfo.value.status == 429
    assert excinfo.value.locked_until == 1_086_400
    assert excinfo.value.retry_after == 86400

    saved = json.loads(_state_file(tmp_path).read_text(encoding="utf-8"))
    assert saved[WXID]["redeemLockedUntil"] == 1_086_400
    assert svc.get_plan_snapshot("acct")["redeemLockedUntil"] == 1_086_400

    with pytest.raises(svc.CdnRedeemError) as excinfo2:
        _run(svc.redeem_code("acct", "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"))
    assert excinfo2.value.code == "redeem_locked"
    assert excinfo2.value.retry_after == 86_400
    assert len(worker.calls("/redeem")) == 1  # 锁定期间不再打 Worker


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
def test_redeem_error_codes_map_to_redeem_error(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, status: int, code: str) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/redeem", httpx.Response(status, json={"error": "nope", "code": code}))
    with pytest.raises(svc.CdnRedeemError) as excinfo:
        _run(svc.redeem_code("acct", "wx-7K9M-P4RX-2V8D-Q6YT-H3NC"))
    assert excinfo.value.status == status
    assert excinfo.value.code == code


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def test_clear_cached_token_and_snapshot(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    _run(svc.ensure_token("acct"))
    assert svc.get_plan_snapshot("acct")["connected"] is True

    svc.clear_cached_token("acct")
    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["connected"] is False
    assert snapshot["account"]["plan"] == "Free"  # 只清 token，保留套餐信息


def test_snapshot_never_raises_for_unresolvable_account(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(svc, "get_data_dir", lambda: tmp_path)

    def _boom(*_a, **_k):
        raise FileNotFoundError("nope")

    monkeypatch.setattr(svc, "_resolve_wxid_dir_for_image_key", _boom)
    snapshot = svc.get_plan_snapshot("ghost")
    assert snapshot["connected"] is False
    assert snapshot["account"] is None
    assert snapshot["enabled"] is False
    assert snapshot["tokenDuration"] == "medium"


def test_token_duration_setting_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(svc, "get_data_dir", lambda: tmp_path)
    assert svc.get_token_duration() == "medium"
    svc.set_cdn_download_enabled(True)
    assert svc.set_token_duration("long") == "long"
    assert svc.get_token_duration() == "long"
    assert svc.is_cdn_download_enabled() is True
    raw = json.loads((tmp_path / "cdn_image_settings.json").read_text(encoding="utf-8"))
    assert raw == {"enabled": True, "tokenDuration": "long"}
    with pytest.raises(ValueError):
        svc.set_token_duration("forever")


def test_network_error_becomes_cdn_error(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    def _unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    worker.always("/token", _unreachable)
    with pytest.raises(svc.CdnError) as excinfo:
        _run(svc.ensure_token("acct"))
    assert excinfo.value.code == "network_error"


# ---------------------------------------------------------------------------
# 并发 / 闸门 / 退避
# ---------------------------------------------------------------------------


def test_concurrent_ensure_token_coalesces_into_one_token_call(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_A)))

    async def _go():
        return await asyncio.gather(*(svc.ensure_token("acct") for _ in range(8)))

    tokens = _run(_go())
    assert tokens == [TOKEN_A] * 8
    assert len(worker.calls("/token")) == 1


def test_concurrent_401s_refresh_token_only_once(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    """10 个并发下载同时拿到 401：只应换发一次 token（共 2 次 /token），不能各刷各的。"""
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_B)))

    def _download(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == f"Bearer {TOKEN_A}":
            return httpx.Response(401, json={"error": "expired", "code": "invalid_token"})
        return _download_ok(JPEG_FIXTURE, {"X-WXCDN-Cache": "HIT"})

    worker.always("/download", _download)

    async def _go():
        return await asyncio.gather(*(svc.download_media("acct", f"file-{i}") for i in range(10)))

    results = _run(_go())
    assert results == [JPEG_FIXTURE] * 10
    assert len(worker.calls("/token")) == 2
    downloads = worker.calls("/download")
    assert sum(1 for r in downloads if r.headers["Authorization"] == f"Bearer {TOKEN_A}") == 10
    assert sum(1 for r in downloads if r.headers["Authorization"] == f"Bearer {TOKEN_B}") == 10


def test_401_with_already_rotated_token_does_not_hit_token_endpoint(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_B)))
    _run(svc.ensure_token("acct"))
    # 调用方手里的旧 token 已经不是本地那枚了：直接复用本地的，不再签发。
    assert _run(svc.ensure_token("acct", stale_token=TOKEN_A)) == TOKEN_B
    assert len(worker.calls("/token")) == 1
    # 本地那枚正是被拒绝的：这才重新签发。
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    assert _run(svc.ensure_token("acct", stale_token=TOKEN_B)) == TOKEN_A
    assert len(worker.calls("/token")) == 2


def test_token_gate_waits_min_interval_between_calls(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1_000_000.0}
    sleeps: List[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr(svc, "_now", lambda: clock["now"])
    monkeypatch.setattr(svc, "_sleep", _fake_sleep)
    monkeypatch.setattr(svc, "_TOKEN_MIN_INTERVAL_SECONDS", 4.0)
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_A)))

    _run(svc.ensure_token("acct"))
    assert sleeps == []
    clock["now"] += 1.5
    _run(svc.ensure_token("acct", force=True))
    assert sleeps == [pytest.approx(2.5)]
    assert len(worker.calls("/token")) == 2


def test_token_rate_limit_backoff_skips_worker_inside_retry_after(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(svc, "_now", lambda: clock["now"])
    worker.always(
        "/token",
        httpx.Response(429, json={"error": "too fast", "code": "rate_limited"}, headers={"Retry-After": "9"}),
    )

    with pytest.raises(svc.CdnRateLimitedError) as first:
        _run(svc.ensure_token("acct"))
    assert first.value.retry_after == 9
    assert len(worker.calls("/token")) == 1

    saved = json.loads(_state_file(tmp_path).read_text(encoding="utf-8"))[WXID]
    assert saved["tokenRetryUntil"] == 1_000_009
    assert saved["lastError"]["code"] == "rate_limited"

    clock["now"] = 1_000_004.0
    with pytest.raises(svc.CdnRateLimitedError) as second:
        _run(svc.ensure_token("acct"))
    assert second.value.retry_after == 5
    assert len(worker.calls("/token")) == 1  # 窗口内不打 Worker
    assert svc.get_plan_snapshot("acct")["tokenRetryUntil"] == 1_000_009

    clock["now"] = 1_000_010.0
    with pytest.raises(svc.CdnRateLimitedError):
        _run(svc.ensure_token("acct"))
    assert len(worker.calls("/token")) == 2  # 窗口过了才重试

    # 用户主动「连接」可以越过退避窗口。
    with pytest.raises(svc.CdnRateLimitedError):
        _run(svc.ensure_token("acct", force=True))
    assert len(worker.calls("/token")) == 3


def test_token_network_error_backoff_and_recovery(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(svc, "_now", lambda: clock["now"])

    def _unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    worker.queue("/token", _unreachable)
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_A)))

    with pytest.raises(svc.CdnError) as first:
        _run(svc.ensure_token("acct"))
    assert first.value.code == "network_error"
    assert first.value.retry_after == svc._TOKEN_NETWORK_ERROR_BACKOFF_SECONDS

    clock["now"] += 5
    with pytest.raises(svc.CdnError) as second:
        _run(svc.ensure_token("acct"))
    assert second.value.code == "network_error"
    assert second.value.retry_after == svc._TOKEN_NETWORK_ERROR_BACKOFF_SECONDS - 5
    assert len(worker.calls("/token")) == 1

    clock["now"] += svc._TOKEN_NETWORK_ERROR_BACKOFF_SECONDS
    assert _run(svc.ensure_token("acct")) == TOKEN_A
    assert len(worker.calls("/token")) == 2
    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["tokenRetryUntil"] is None
    assert snapshot["lastError"] is None


# ---------------------------------------------------------------------------
# 403 / 状态持久化 / Retry-After 日期
# ---------------------------------------------------------------------------


def test_403_without_account_frozen_code_does_not_freeze(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/quota",
        httpx.Response(403, text="<html><body>Access denied</body></html>", headers={"Content-Type": "text/html"}),
    )
    body = _token_body()
    worker.queue("/quota", httpx.Response(200, json={"account": body["account"], "quota": body["quota"]}))

    with pytest.raises(svc.CdnError) as excinfo:
        _run(svc.fetch_quota("acct", force=True))
    assert not isinstance(excinfo.value, svc.CdnAccountFrozenError)
    assert excinfo.value.code == "http_403"
    assert excinfo.value.status == 403

    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["frozen"] is False
    assert snapshot["lastError"]["code"] == "http_403"

    # 下一次调用照常打 Worker，并且成功。
    result = _run(svc.fetch_quota("acct", force=True))
    assert result["quota"]["limitBytes"] == 52428800
    assert len(worker.calls("/quota")) == 2
    assert len(worker.calls("/token")) == 1


def test_state_write_failure_keeps_live_token_in_memory(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setattr(svc, "_state_path", lambda: blocker / "cdn_account_state.json")  # 写盘必然失败
    caplog.set_level(logging.WARNING, logger=svc.__name__)
    worker.always("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.always("/download", _download_ok(JPEG_FIXTURE, {"X-Quota-Remaining": "100"}))

    for i in range(3):
        assert _run(svc.download_media("acct", f"file-{i}")) == JPEG_FIXTURE

    assert len(worker.calls("/token")) == 1
    assert any("写入账号状态失败" in rec.getMessage() for rec in caplog.records)
    assert TOKEN_A not in caplog.text
    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["connected"] is True
    assert snapshot["quota"]["remainingBytes"] == 100
    assert len(snapshot["recent"]) == 3


def test_quota_exceeded_updates_snapshot_quota(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    exhausted = {
        "period": "day",
        "periodKey": "day:2026-09-05",
        "limitBytes": 52428800,
        "usedBytes": 52428800,
        "remainingBytes": 0,
        "resetsAt": 1_086_400,
    }
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue("/download", httpx.Response(429, json={"error": "额度不足", "code": "quota_exceeded", "quota": exhausted}))
    assert svc.get_plan_snapshot("acct")["quota"] is None

    with pytest.raises(svc.CdnQuotaExceededError):
        _run(svc.download_media("acct", "file-x"))

    snapshot = svc.get_plan_snapshot("acct")
    assert snapshot["quota"] == exhausted
    assert snapshot["quota"]["remainingBytes"] == 0
    assert snapshot["quotaSource"] == "download"
    assert snapshot["quotaFetchedAt"] == 1_000_000


def test_retry_after_http_date_is_parsed(worker: FakeWorker, monkeypatch: pytest.MonkeyPatch) -> None:
    import email.utils

    monkeypatch.setattr(svc, "_now", lambda: 1_000_000.0)
    worker.queue("/token", httpx.Response(200, json=_token_body(TOKEN_A)))
    worker.queue(
        "/download",
        httpx.Response(
            429,
            json={"error": "slow down", "code": "rate_limited"},
            headers={"Retry-After": email.utils.formatdate(1_000_000 + 120, usegmt=True)},
        ),
    )
    with pytest.raises(svc.CdnRateLimitedError) as excinfo:
        _run(svc.download_media("acct", "file-date"))
    assert excinfo.value.retry_after == 120
    assert excinfo.value.headers() == {"Retry-After": "120"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ("WX3K9MP4RX2V8DQ6YTH3", "WX3K9MP4RX2V8DQ6YTH3"),  # 省略前缀、码本身以 WX 开头：不能吃掉
        ("wx-WX3K9MP4RX2V8DQ6YTH3", "WX3K9MP4RX2V8DQ6YTH3"),  # 显式前缀 + 以 WX 开头的码
        ("wx7K9MP4RX2V8DQ6YTH3NC", "7K9MP4RX2V8DQ6YTH3NC"),  # 前缀不带分隔符但剩余仍够 20 位
        ("WX 3K9M-P4RX-2V8D-Q6YT-H3NC", "3K9MP4RX2V8DQ6YTH3NC"),  # 空格也算分隔符
    ),
)
def test_normalize_redeem_code_keeps_leading_wx_that_belongs_to_code(raw: str, expected: str) -> None:
    assert svc.normalize_redeem_code(raw) == expected
