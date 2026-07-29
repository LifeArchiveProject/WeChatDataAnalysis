from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / path).read_text(encoding="utf-8")


def test_global_middleware_blocks_business_routes_until_agreement_is_accepted():
    source = read_frontend("middleware/first-use-agreement.global.js")

    assert "import.meta.server" in source
    assert "useNuxtApp().isHydrating" in source
    assert "to.path === '/agreement'" in source
    assert "isFirstUseAgreementAccepted()" in source
    assert "query: { redirect: to.fullPath || '/' }" in source
    assert "{ replace: true }" in source


def test_agreement_uses_versioned_acceptance_with_timestamp():
    source = read_frontend("lib/first-use-agreement.js")

    assert "FIRST_USE_AGREEMENT_VERSION" in source
    assert "ui.first_use_agreement" in source
    assert "acceptedAt: new Date().toISOString()" in source
    assert "stored?.version === FIRST_USE_AGREEMENT_VERSION" in source
    assert "target.startsWith('//')" in source


def test_notice_and_disclaimer_have_independent_ten_second_countdowns():
    source = read_frontend("pages/agreement.vue")

    assert "const COUNTDOWN_MILLISECONDS = 10_000" in source
    assert "stepIndex.value += 1\n    startCountdown()" in source
    assert "document.visibilityState === 'visible'" in source
    assert ':disabled="!canConfirm"' in source
    assert "我已阅读，继续" in source
    assert "我已阅读并同意，开始使用" in source
    assert "persistFirstUseAgreementAcceptance()" in source


def test_notice_covers_version_platform_login_and_hook_risks():
    source = read_frontend("pages/agreement.vue")

    for text in (
        "仅支持微信桌面端 4.x 版本",
        "同一账号在不同设备上的密钥通常不同",
        "请至少在当前设备成功登录一次",
        "首次解密该账号前仍至少需要成功登录一次",
        "请仅运行并登录一个微信实例",
        "优先使用 V4 内存扫描",
        "才会询问是否改用 Hook",
        "可能延迟出现或集中触达",
        "macOS 版不提供数据库密钥获取",
        "图片密钥仍可按页面提示获取",
        "请勿重复获取",
    ):
        assert text in source


def test_app_uses_a_hydration_safe_initial_route_guard():
    source = read_frontend("app.vue")
    index = read_frontend("pages/index.vue")

    assert "const firstUseRouteResolved = ref(false)" in source
    assert "await nextTick()" in source
    assert "await enforceFirstUseRoute()" in source
    assert "正在准备使用须知" in source
    assert "if (!isFirstUseAgreementAccepted()) return" in index


def test_disclaimer_covers_authorization_backup_compatibility_and_liability():
    source = read_frontend("pages/agreement.vue")

    for text in (
        "非官方开源工具",
        "已经取得明确授权访问的数据",
        "开始前请备份重要数据",
        "本项目不保证对未来微信版本持续兼容",
        "由使用者自行承担",
        "点击确认即表示您已完整阅读",
    ):
        assert text in source


def test_readme_contains_the_full_disclaimer():
    source = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "## 免责声明" in source
    assert "非官方开源工具" in source
    assert "已经取得明确授权访问的数据" in source
    assert "开始前请备份重要数据" in source
    assert "本项目不保证对未来微信版本持续兼容" in source
    assert "由使用者自行承担" in source
