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

    # The expanded and annotated 2026-08-12 notice is a new consent revision.
    # Keeping the previous version would silently accept the old record and skip this page.
    assert "FIRST_USE_AGREEMENT_VERSION = '2026-08-12.3'" in source
    assert "FIRST_USE_AGREEMENT_VERSION = '2026-07-26.2'" not in source
    assert "ui.first_use_agreement" in source
    assert "acceptedAt: new Date().toISOString()" in source
    assert "stored?.version === FIRST_USE_AGREEMENT_VERSION" in source
    assert "target.startsWith('//')" in source


def test_notice_and_disclaimer_are_expanded_with_one_twenty_second_countdown():
    source = read_frontend("pages/agreement.vue")

    assert 'v-for="(document, documentIndex) in documents"' in source
    assert "const COUNTDOWN_MILLISECONDS = 20_000" in source
    assert "stepIndex" not in source
    assert "currentDocument" not in source
    assert "first-use-panel" not in source
    assert "first-use-documents" in source
    assert "@media (max-height: 840px)" in source
    assert "document.visibilityState === 'visible'" in source
    assert ':disabled="!canConfirm"' in source
    assert "我已阅读全部内容并同意" in source
    assert "persistFirstUseAgreementAcceptance()" in source


def test_notice_uses_local_hand_drawn_annotations_with_humorous_plain_language():
    source = read_frontend("pages/agreement.vue")
    package = read_frontend("package.json")

    assert '"rough-notation": "0.5.1"' in package
    assert "await import('rough-notation')" in source
    assert "prefers-reduced-motion: reduce" in source
    assert "annotation.remove()" in source
    # Keep the hand-drawn layer selective: six heading callouts, not a mark on every line.
    assert source.count("annotation: '") == 6
    for annotation_type in ("highlight", "circle", "box", "crossed-off"):
        assert f"annotation: '{annotation_type}'" in source
    for copy in (
        "程序暂不负责考古",
        "别让工具隔空算命",
        "分身先下班",
        "软件没有水晶球",
        "空气不背锅",
    ):
        assert copy in source


def test_body_copy_uses_selective_bold_and_marker_emphasis():
    source = read_frontend("pages/agreement.vue")

    assert "segmentParagraph(paragraph, section.emphasis)" in source
    assert ":is=\"fragment.strong ? 'strong' : 'span'\"" in source
    assert "'first-use-body-marker': fragment.marker" in source
    assert "'first-use-annotation': fragment.annotation" not in source
    assert ".first-use-body-keyword" in source
    assert 12 <= source.count("strong: true") <= 18
    assert 5 <= source.count("marker: true") <= 8
    for copy in (
        "仅支持微信桌面端 4.x 版本",
        "微信账号和当前设备",
        "至少在当前设备成功登录一次",
        "优先使用 V4 内存扫描",
        "本人合法持有、管理或已经取得明确授权访问的数据",
        "不保证对未来微信版本持续兼容",
        "由使用者自行承担",
    ):
        assert copy in source


def test_rejected_intro_and_outdated_notice_items_are_removed():
    source = read_frontend("pages/agreement.vue")

    for removed_copy in (
        "这 12 条不是彩蛋",
        "版本、登录和密钥这三位“门神”",
        "macOS 版不提供数据库密钥获取",
        "macOS 密钥请找",
        "先备份",
        "别信“应该没事”",
        "开始前请备份重要数据",
    ):
        assert removed_copy not in source


def test_compact_agreement_uses_readable_type_sizes():
    source = read_frontend("pages/agreement.vue")

    assert ".first-use-section-copy p {" in source
    assert "font-size: 14.25px;" in source
    assert "font-size: 13.5px;" in source
    assert "font-size: 14.5px;\n    line-height: 1.4;" in source
    assert "grid-template-columns: minmax(0, 1.28fr) minmax(0, 0.72fr);" in source


def test_notice_covers_version_login_and_hook_risks():
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
        "请勿重复获取",
    ):
        assert text in source


def test_app_uses_a_route_aware_guard_with_a_hard_navigation_fallback():
    source = read_frontend("app.vue")
    index = read_frontend("pages/index.vue")

    assert "const firstUseRouteResolved = ref(isAgreementRoute())" in source
    assert "await nextTick()" in source
    assert "await enforceFirstUseRoute()" in source
    assert "正在准备使用须知" in source
    assert "直接打开使用须知" in source
    assert '<a :href="firstUseAgreementHref"' in source
    assert "window.location.replace(firstUseAgreementHref.value)" in source
    assert "if (!isFirstUseAgreementAccepted()) return" in index


def test_inline_bootstrap_can_reach_and_accept_the_notice_without_nuxt_mounting():
    config = read_frontend("nuxt.config.ts")
    bootstrap = read_frontend("lib/first-use-bootstrap-script.js")
    agreement = read_frontend("pages/agreement.vue")

    assert "createFirstUseBootstrapScript" in config
    assert "innerHTML: firstUseBootstrapScript" in config
    assert "tagPosition: 'head'" in config
    assert "window.location.replace(agreementUrl)" in bootstrap
    assert "data-first-use-mounted" in bootstrap
    assert "window.localStorage.setItem(storageKey" in bootstrap
    assert "button.disabled = false" in bootstrap
    assert "pageRef.value?.setAttribute('data-first-use-mounted', 'true')" in agreement


def test_first_use_route_guard_does_not_wait_on_remote_stylesheets():
    config = read_frontend("nuxt.config.ts")
    package = read_frontend("package.json")

    assert "https://cdnjs.cloudflare.com" not in config
    assert "@fortawesome/fontawesome-free/css/all.min.css" in config
    assert '"@fortawesome/fontawesome-free"' in package


def test_disclaimer_covers_authorization_compatibility_and_liability():
    source = read_frontend("pages/agreement.vue")

    for text in (
        "非官方开源工具",
        "已经取得明确授权访问的数据",
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
