import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wechat_decrypt_tool.sns_media import fix_sns_cdn_url  # noqa: E402


def test_fix_sns_cdn_url_preserves_credential_bound_image_sizes():
    assert fix_sns_cdn_url("http://example.qpic.cn/path/150") == "https://example.qpic.cn/path/150"
    assert fix_sns_cdn_url("https://example.qpic.cn/path/200?x=1") == "https://example.qpic.cn/path/200?x=1"
    assert fix_sns_cdn_url("https://example.qpic.cn/path/480", token="abc") == (
        "https://example.qpic.cn/path/480?token=abc&idx=1"
    )
    assert fix_sns_cdn_url(
        "https://example.qpic.cn/path/480", token="origin", force_original=True
    ) == (
        "https://example.qpic.cn/path/0?token=origin&idx=1"
    )
