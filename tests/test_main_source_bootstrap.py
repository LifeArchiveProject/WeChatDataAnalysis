from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_prefers_checkout_src_over_stale_installed_copy(tmp_path: Path) -> None:
    # 模拟 `uv sync --no-editable` 留在 site-packages 的旧副本。PYTHONPATH 排在
    # site-packages 与 editable 安装的 .pth 之前，因此 editable 环境下也不会碰巧通过。
    stale = tmp_path / "stale-site-packages"
    package = stale / "wechat_decrypt_tool"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        'raise ImportError("stale installed copy of wechat_decrypt_tool was imported")\n',
        encoding="utf-8",
    )
    # main.py 顶层会 import uvicorn；用空桩代替，测试既不加载也不启动真实服务。
    (stale / "uvicorn.py").write_text("", encoding="utf-8")

    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{stale}{os.pathsep}{inherited}" if inherited else str(stale)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import main, wechat_decrypt_tool; print(wechat_decrypt_tool.__file__)",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    resolved = Path(result.stdout.strip().splitlines()[-1]).resolve()
    assert resolved == (ROOT / "src" / "wechat_decrypt_tool" / "__init__.py").resolve()
