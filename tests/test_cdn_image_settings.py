from __future__ import annotations

import json

from wechat_decrypt_tool import cdn_image_service


def test_cdn_original_image_download_defaults_to_disabled(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cdn_image_service, "get_data_dir", lambda: tmp_path)

    assert cdn_image_service.is_cdn_download_enabled() is False

    (tmp_path / "cdn_image_settings.json").write_text("not-json", encoding="utf-8")
    assert cdn_image_service.is_cdn_download_enabled() is False


def test_cdn_original_image_download_preserves_explicit_user_choice(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cdn_image_service, "get_data_dir", lambda: tmp_path)

    cdn_image_service.set_cdn_download_enabled(True)
    assert cdn_image_service.is_cdn_download_enabled() is True
    assert json.loads((tmp_path / "cdn_image_settings.json").read_text(encoding="utf-8")) == {
        "enabled": True
    }

    cdn_image_service.set_cdn_download_enabled(False)
    assert cdn_image_service.is_cdn_download_enabled() is False
