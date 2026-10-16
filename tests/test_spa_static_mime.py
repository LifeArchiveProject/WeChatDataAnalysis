from __future__ import annotations

import mimetypes

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.testclient import TestClient

from wechat_decrypt_tool.api import _SPAStaticFiles


@pytest.mark.parametrize(
    ("suffix", "expected"),
    (
        (".js", "text/javascript; charset=utf-8"),
        (".mjs", "text/javascript; charset=utf-8"),
        (".css", "text/css; charset=utf-8"),
    ),
)
def test_static_asset_content_type_ignores_system_mime_override(
    tmp_path, suffix: str, expected: str
) -> None:
    asset = tmp_path / f"entry{suffix}"
    asset.write_text("export default true;", encoding="utf-8")

    original = mimetypes.guess_type(asset.name)[0]
    assert original is not None
    try:
        # Simulate a Windows registry entry that overrides Python's MIME table.
        mimetypes.add_type("text/plain", suffix)
        assert mimetypes.guess_type(asset.name)[0] == "text/plain"

        app = Starlette(
            routes=[Mount("/", app=_SPAStaticFiles(directory=str(tmp_path), html=True))]
        )
        with TestClient(app) as client:
            response = client.get(f"/entry{suffix}")

        assert response.status_code == 200
        assert response.headers["content-type"] == expected
    finally:
        mimetypes.add_type(original, suffix)
