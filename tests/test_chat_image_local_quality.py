"""覆盖旧缩略图缓存的显示、离线导出与并发预解密，使用真实编码和 XOR 解密。"""

import importlib
import io
import json
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

import test_chat_media_image_cache_upgrade as cache_fixtures


ACCOUNT = "wxid_test"
USERNAME = "wxid_friend"
MD5 = "a" * 32


def image_bytes(width, height, format="PNG"):
    output = io.BytesIO()
    Image.new("RGB", (width, height), (24, 90, 170)).save(output, format=format)
    return output.getvalue()


def dimensions(data):
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        return image.size


@pytest.fixture
def local_images(tmp_path, monkeypatch):
    monkeypatch.setenv("WECHAT_TOOL_DATA_DIR", str(tmp_path))
    helper = cache_fixtures.TestChatMediaImageCacheUpgrade()
    account = tmp_path / "output" / "databases" / ACCOUNT
    account.mkdir(parents=True)
    source = tmp_path / "wxid_source"
    source.mkdir()
    helper._seed_contact_db(account / "contact.db", account=ACCOUNT, username=USERNAME)
    helper._seed_session_db(account / "session.db", username=USERNAME)
    helper._seed_source_info(account, wxid_dir=source)
    client = helper._build_client()
    from wechat_decrypt_tool import media_helpers
    from wechat_decrypt_tool.routers import chat_media, media

    importlib.reload(media)
    client.app.include_router(media.router)
    media_helpers._save_media_keys(account, 0xA5)
    try:
        yield helper, account, source, client, media_helpers, chat_media
    finally:
        client.close()
        logging.shutdown()


def seed_variant(fixture, suffix, payload, md5=MD5):
    helper, _, source, *_ = fixture
    return helper._seed_live_variant(source, username=USERNAME, md5=md5, suffix=suffix, payload=payload)


def seed_cache(fixture, payload, md5=MD5):
    helper, account, *_ = fixture
    return helper._seed_cached_resource(account, md5=md5, payload=payload)


def get_image(fixture, **kwargs):
    return fixture[3].get("/api/chat/media/image", params={"account": ACCOUNT, "username": USERNAME, "md5": MD5, **kwargs})


def test_default_request_chooses_pixels_over_filename_and_bytes(local_images):
    seed_cache(local_images, image_bytes(120, 120))
    seed_variant(local_images, "_b", image_bytes(160, 160, "JPEG"))
    original = image_bytes(800, 600, "WebP")
    seed_variant(local_images, "_h", original)
    _, account, _, _, helpers, router = local_images
    downloader = AsyncMock(side_effect=AssertionError("本地缓存修复不能调用 CDN"))
    with patch.object(router.cdn_image_service, "download_original_image", downloader), patch.object(
        helpers, "_fallback_search_media_by_md5", side_effect=AssertionError("不能全账号扫描")
    ):
        response = get_image(local_images)
    assert response.status_code == 200
    assert response.content == original
    assert dimensions(response.content) == (800, 600)
    assert helpers._try_find_decrypted_resource(account, MD5).read_bytes() == original
    downloader.assert_not_awaited()


def test_default_uncached_request_compares_all_decoded_variants(local_images):
    seed_variant(local_images, "_b", image_bytes(120, 120))
    seed_variant(local_images, "_h", image_bytes(800, 600))
    response = get_image(local_images)
    assert response.status_code == 200
    assert dimensions(response.content) == (800, 600)


@pytest.mark.parametrize("cached", [False, True])
def test_hardlink_thumbnail_does_not_hide_original_in_chat_attach(local_images, cached):
    if cached:
        seed_cache(local_images, image_bytes(120, 120))
    seed_variant(local_images, "_h", image_bytes(800, 600))
    thumbnail = local_images[2] / "cache" / "Thumb" / f"{MD5}_t.dat"
    thumbnail.parent.mkdir(parents=True)
    thumbnail.write_bytes(image_bytes(120, 120))
    with patch.object(local_images[4], "_resolve_media_path_from_hardlink", return_value=thumbnail), patch.object(
        local_images[5], "_resolve_media_path_from_hardlink", return_value=thumbnail
    ):
        response = get_image(local_images)
    assert response.status_code == 200
    assert dimensions(response.content) == (800, 600)


def test_only_cache_still_works_without_source_directory(local_images):
    original = image_bytes(900, 700)
    seed_cache(local_images, original)
    (_, account, source, _, helpers, _) = local_images
    (account / "_source.json").write_text(json.dumps({"source": "imported", "prefer_decrypted": True}), encoding="utf-8")
    with patch.object(helpers, "_resolve_account_wxid_dir", return_value=None), patch.object(
        helpers, "_resolve_account_db_storage_dir", return_value=None
    ):
        response = get_image(local_images)
    assert response.status_code == 200
    assert response.content == original


def test_larger_cache_is_not_downgraded_by_live_variant(local_images):
    original = image_bytes(900, 700)
    seed_cache(local_images, original)
    seed_variant(local_images, "_b", image_bytes(120, 120))
    seed_variant(local_images, "_h", b"broken encrypted image")
    assert get_image(local_images).content == original
    assert get_image(local_images, prefer_live=True).content == original


def test_etag_changes_when_original_arrives_after_thumbnail(local_images):
    seed_cache(local_images, image_bytes(120, 120))
    first = get_image(local_images)
    assert first.headers["cache-control"] == "private, max-age=0, must-revalidate"
    seed_variant(local_images, "_h", image_bytes(800, 600))
    client = local_images[3]
    params = {"account": ACCOUNT, "username": USERNAME, "md5": MD5}
    second = client.get("/api/chat/media/image", params=params, headers={"If-None-Match": first.headers["etag"]})
    assert second.status_code == 200
    assert dimensions(second.content) == (800, 600)
    assert second.headers["etag"] != first.headers["etag"]
    third = client.get("/api/chat/media/image", params=params, headers={"If-None-Match": second.headers["etag"]})
    assert third.status_code == 304


@pytest.mark.parametrize("stream", [False, True])
def test_predecrypt_repairs_valid_thumbnail_then_skips_unchanged_sources(local_images, stream):
    seed_cache(local_images, image_bytes(120, 120))
    for suffix, size in [("_t", (120, 120)), ("_b", (160, 160)), ("_h", (800, 600))]:
        encrypted = bytes(byte ^ 0xA5 for byte in image_bytes(*size))
        seed_variant(local_images, suffix, encrypted)
    _, account, _, client, helpers, _ = local_images

    def run():
        if stream:
            response = client.get("/api/media/decrypt_all_stream", params={"account": ACCOUNT, "concurrency": 10})
            response.raise_for_status()
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            return events[-1]
        response = client.post("/api/media/decrypt_all", json={"account": ACCOUNT})
        response.raise_for_status()
        return response.json()

    result = run()
    assert result["fail_count"] == 0
    assert result["success_count"] == 3
    cached = helpers._try_find_decrypted_resource(account, MD5)
    assert dimensions(cached.read_bytes()) == (800, 600)
    mtime = cached.stat().st_mtime_ns
    result = run()
    assert result["skip_count"] == 3
    assert result["success_count"] == 0
    assert cached.stat().st_mtime_ns == mtime
    # 同一路径内容变化后必须重新比较，不能只按 MD5 永久跳过。
    seed_variant(local_images, "_h", bytes(byte ^ 0xA5 for byte in image_bytes(1000, 800)))
    result = run()
    assert result["success_count"] == 1
    assert dimensions(cached.read_bytes()) == (1000, 800)


def test_concurrent_cache_writers_never_replace_original_with_thumbnail(local_images):
    _, account, _, _, helpers, _ = local_images
    sizes = [(120, 120), (800, 600), (160, 160), (1000, 800)] * 8
    with ThreadPoolExecutor(max_workers=10) as executor:
        list(executor.map(lambda size: helpers._save_best_image_resource(account, MD5, image_bytes(*size)), sizes))
    assert dimensions(helpers._try_find_decrypted_resource(account, MD5).read_bytes()) == (1000, 800)
    assert not list((account / "resource").rglob("*.tmp"))


def test_repeated_display_does_not_redecrypt_unchanged_original(local_images):
    seed_cache(local_images, image_bytes(120, 120))
    path = seed_variant(local_images, "_h", bytes(byte ^ 0xA5 for byte in image_bytes(800, 600)))
    assert dimensions(get_image(local_images).content) == (800, 600)
    helpers = local_images[4]
    with patch.object(helpers, "_read_and_maybe_decrypt_media", wraps=helpers._read_and_maybe_decrypt_media) as decoder:
        assert dimensions(get_image(local_images).content) == (800, 600)
    assert not any(call.args[0] == path for call in decoder.call_args_list)
    seed_variant(local_images, "_h", bytes(byte ^ 0xA5 for byte in image_bytes(1000, 800)))
    assert dimensions(get_image(local_images).content) == (1000, 800)


def test_readers_remain_valid_while_predecrypt_changes_cache_format(local_images):
    seed_cache(local_images, image_bytes(120, 120))
    _, account, _, _, helpers, _ = local_images

    def write(size):
        format = ["PNG", "JPEG", "WebP"][size % 3]
        return helpers._save_best_image_resource(account, MD5, image_bytes(size, size, format))

    def read(_):
        response = get_image(local_images)
        assert response.status_code == 200
        assert dimensions(response.content)[0] >= 120

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(write, size) for size in range(121, 151)]
        futures.extend(executor.submit(read, index) for index in range(30))
        for future in futures:
            future.result()
    assert dimensions(helpers._try_find_decrypted_resource(account, MD5).read_bytes()) == (150, 150)


def test_export_upgrades_cache_without_any_prior_image_request(local_images):
    _, account, _, _, helpers, _ = local_images
    seed_cache(local_images, image_bytes(120, 120))
    seed_variant(local_images, "_b", image_bytes(160, 160))
    original = image_bytes(800, 600)
    seed_variant(local_images, "_h", bytes(byte ^ 0xA5 for byte in original))
    from wechat_decrypt_tool import chat_export_service as service

    importlib.reload(service)
    # HTML、JSON 和增量导出共用这个写入入口；原生签名组件由真实启动验收覆盖。
    archive_path = account / "offline-export.zip"
    media_index = helpers.MediaPathIndex.build(account_dir=account, usernames=[USERNAME], media_kinds=["image"])
    with zipfile.ZipFile(archive_path, "w") as archive:
        result, copied = service._materialize_media(
            zf=archive, account_dir=account, conv_username=USERNAME, kind="image", md5=MD5, file_id="",
            media_written={}, suggested_name="", media_index=media_index,
        )
        assert copied
        assert result.startswith("media/images/")
    with zipfile.ZipFile(archive_path) as archive:
        names = [name for name in archive.namelist() if name.startswith("media/images/")]
        assert len(names) == 1
        assert archive.read(names[0]) == original
        assert dimensions(archive.read(names[0])) == (800, 600)
    assert dimensions(helpers._try_find_decrypted_resource(account, MD5).read_bytes()) == (800, 600)
