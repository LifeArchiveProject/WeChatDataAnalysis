"""从项目锁文件生成 Windows Qwen 外置运行组件清单。"""
import json
from pathlib import Path
import tomllib
from urllib.parse import unquote, urlparse

import httpx
from packaging.markers import Marker, default_environment
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import parse_wheel_filename


def main():
    root = Path(__file__).resolve().parents[1]
    packages = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))["package"]
    variants = {}
    for minor in (11, 12, 13):
        env = {**default_environment(), "sys_platform": "win32", "platform_system": "Windows",
               "platform_machine": "AMD64", "python_version": f"3.{minor}",
               "python_full_version": f"3.{minor}.3"}
        tags = list(cpython_tags((3, minor), abis=[f"cp3{minor}"], platforms=["win_amd64"]))
        tags += list(compatible_tags((3, minor), interpreter=f"cp3{minor}", platforms=["win_amd64"]))
        ranks = {tag: i for i, tag in enumerate(tags)}
        resolved = {}
        pending = [{"name": "torch", "version": "2.9.1+cu128"}, {"name": "transformers", "version": "5.17.0"}]
        while pending:
            requirement = pending.pop()
            if requirement.get("marker") and not Marker(requirement["marker"]).evaluate(env):
                continue
            name = requirement["name"]
            if name in resolved:
                continue
            candidates = [p for p in packages if p["name"] == name and
                          (not requirement.get("version") or p["version"] == requirement["version"])]
            choices = []
            for package in candidates:
                for wheel in package.get("wheels", []):
                    filename = unquote(urlparse(wheel["url"]).path.rsplit("/", 1)[-1])
                    matching = parse_wheel_filename(filename)[3] & ranks.keys()
                    if matching:
                        choices.append((min(ranks[tag] for tag in matching), package, wheel, filename))
            if not choices:
                raise ValueError(f"没有兼容 wheel: {name} / cp3{minor}")
            _, package, wheel, filename = min(choices, key=lambda item: item[0])
            size = wheel.get("size")
            if size is None:
                response = httpx.head(wheel["url"], follow_redirects=True, timeout=60)
                response.raise_for_status()
                size = int(response.headers["content-length"])
            resolved[name] = dict(name=filename, package=name, version=package["version"],
                                  url=wheel["url"], size=size, sha256=wheel["hash"].removeprefix("sha256:"))
            pending.extend(package.get("dependencies", []))
        variants[f"cp3{minor}"] = sorted(resolved.values(), key=lambda f: f["package"])
        print(f"cp3{minor}: {len(resolved)} wheels, {sum(f['size'] for f in resolved.values())} bytes", flush=True)
    manifest = dict(id="qwen-torch2.9.1-cu128-transformers5.17.0-v1", platform="win32",
                    architecture="AMD64", variants=variants)
    (root / "src/wechat_decrypt_tool/resources/qwen_gpu_runtime.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
