import sqlite3
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


from wechat_decrypt_tool.routers import sns  # noqa: E402


def test_sidebar_uses_batched_rendering_and_lazy_avatars():
    page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
    assert "const SNS_USER_RENDER_BATCH = 80" in page
    assert 'v-for="u in renderedSnsUsers"' in page
    assert 'v-chat-lazy-src="postAvatarUrl(u.username)"' in page
    assert "snsUserRenderLimit.value + SNS_USER_RENDER_BATCH" in page


def test_snapshot_refresh_merges_latest_page_without_resetting_scroll():
    page = (ROOT / "frontend" / "pages" / "sns.vue").read_text(encoding="utf-8")
    merge = page.split("const mergeVisiblePostsWindow = async", 1)[1].split(
        "\n\nconst mergeLatestPosts", 1
    )[0]
    assert "offset: scanOffset" in merge
    assert "const anchor = captureSnsScrollAnchor()" in merge
    assert "await restoreSnsScrollAnchor(anchor)" in merge
    assert "scrollTop = 0" not in merge


def test_media_heuristic_runs_in_bounded_background_thread():
    source = (ROOT / "src" / "wechat_decrypt_tool" / "routers" / "sns.py").read_text(encoding="utf-8")
    assert "threading.BoundedSemaphore(4)" in source
    assert "await asyncio.to_thread(\n                    _resolve_sns_cached_image_path_bounded" in source
    assert "candidates = candidates[:128]" in source


def test_sns_user_stats_cache_reuses_unchanged_database_version():
    with TemporaryDirectory() as td:
        account_dir = Path(td) / "wxid_me"
        account_dir.mkdir()
        conn = sqlite3.connect(account_dir / "sns.db")
        conn.execute("CREATE TABLE SnsTimeLine (tid INTEGER, user_name TEXT, content TEXT)")
        conn.execute("CREATE INDEX idx_sns_timeline_user_tid ON SnsTimeLine(user_name, tid DESC)")
        conn.execute(
            "INSERT INTO SnsTimeLine VALUES (?, ?, ?)",
            (1, "wxid_friend", "<TimelineObject><ContentObject><type>1</type></ContentObject></TimelineObject>"),
        )
        conn.commit()
        conn.close()
        sns._load_sns_users_cached.cache_clear()

        with mock.patch.object(sns, "_resolve_account_dir", return_value=account_dir):
            first = sns.list_sns_users(account=account_dir.name)
            before = sns._load_sns_users_cached.cache_info()
            second = sns.list_sns_users(account=account_dir.name)
            after = sns._load_sns_users_cached.cache_info()

        assert first == second
        assert after.hits == before.hits + 1
