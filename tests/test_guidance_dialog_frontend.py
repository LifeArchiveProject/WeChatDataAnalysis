from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / path).read_text(encoding="utf-8")


def test_guide_dialog_is_accessible_and_reusable():
    source = read_frontend("components/GuideDialog.vue")

    assert '<Teleport to="body">' in source
    assert 'role="dialog"' in source
    assert 'aria-modal="true"' in source
    assert "defineEmits(['primary', 'secondary', 'close'])" in source
    assert "event.key === 'Escape'" in source


def test_detection_guides_cover_login_and_both_directory_types():
    source = read_frontend("pages/detection-result.vue")

    assert "title: '请先登录电脑版微信'" in source
    assert "title: '请选择微信数据根目录'" in source
    assert "title: '请选择微信安装目录'" in source
    assert "const handlePickDirectory = () => openGuide('dataPath')" in source
    assert "const pickWechatInstallDirectory = () => openGuide('installPath')" in source
    assert "openGuide('detection')" in source


def test_decrypt_guides_replace_native_confirms_and_cover_media_choices():
    source = read_frontend("pages/decrypt.vue")

    assert "window.confirm" not in source
    assert "window.alert" not in source
    assert "title: '获取前请确认微信已登录'" in source
    assert "title: '是否改用 Hook 获取密钥？'" in source
    assert "title: '内存扫描失败，是否改用 Hook？'" in source
    assert "title: '尚未填写图片 XOR 密钥'" in source
    assert "title: '确定暂时跳过图片解密？'" in source


def test_account_dependent_pages_share_the_no_account_guide():
    source = read_frontend("app.vue")

    for route in (
        "/chat",
        "/edits",
        "/sns",
        "/favorites",
        "/contacts",
        "/biz",
        "/mini-programs",
        "/finder",
        "/payments",
        "/revokes",
        "/wrapped",
    ):
        assert f"'{route}'" in source

    assert 'title="还没有可查看的微信数据"' in source
    assert 'secondary-label="暂时留在此页"' in source
    assert "await navigateTo('/detection-result')" in source
