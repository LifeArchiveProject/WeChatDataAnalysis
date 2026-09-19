from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_frontend(path: str) -> str:
    return (ROOT / "frontend" / path).read_text(encoding="utf-8")


def _linux_hook_branch(source: str) -> str:
    """截出 handleGetDbKey 里 Linux 的那一段分支（不含后续 Windows 分支）。"""
    branch = source.split("if (isLinux.value) {", 1)[1]
    return branch.split("} else if (dbStoragePath) {", 1)[0]


def test_decrypt_page_skips_v4_memory_scan_on_linux() -> None:
    """Linux 取密钥不尝试内存扫描：直接走 Hook，也不提示「内存扫描失败」。"""
    source = read_frontend("pages/decrypt.vue")

    linux_branch = _linux_hook_branch(source)
    assert "await fetchByHook()" in linux_branch
    # 不给后端发 V4 请求（'key_v4' 才是请求体里的字面量），也不需要数据库路径来验证候选。
    assert "'key_v4'" not in linux_branch
    assert "dbStoragePath" not in linux_branch


def test_decrypt_page_guide_dialog_tells_linux_users_the_truth() -> None:
    source = read_frontend("pages/decrypt.vue")

    linux_dialog = source.split("await requestGuideDialog(isLinux.value", 1)[1].split(": {", 1)[0]
    assert "Linux 不执行内存扫描" in linux_dialog
    # Linux 分支不能承诺「先扫内存、失败再改用 Hook」。
    assert "如果内存扫描失败，系统会再次询问是否切换到 Hook 获取。" not in linux_dialog
    # 该文案必须仍然保留给 Windows 分支。
    assert "如果内存扫描失败，系统会再次询问是否切换到 Hook 获取。" in source


def test_v4_copy_and_attribution_are_hidden_where_memory_scan_does_not_exist() -> None:
    source = read_frontend("pages/decrypt.vue")

    # 「优先使用 V4 内存扫描」的按钮提示只在 Windows 显示。
    assert (
        "'点击按钮将优先使用 V4 内存扫描获取【数据库解密密钥】；失败时会询问您是否改用 Hook。"
        "您也可以手动输入已知的64位密钥。'"
    ) in source
    # V4 扫内存的技术出处说明不适用于 Linux。
    assert 'v-if="!isMacos && !isLinux"' in source
