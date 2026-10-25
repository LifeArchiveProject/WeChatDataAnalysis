"""Publish existing desktop packages and release notes from the public API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.request import urlopen

REPOSITORY = "LifeArchiveProject/WeChatDataAnalysis"
PLATFORM_LABELS = {"windows": "Windows x64", "macos": "macOS Apple Silicon"}
CHANGE_LABELS = {"feature": "新增", "improve": "优化", "fix": "修复"}


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args, "--repo", REPOSITORY], check=True, text=True, capture_output=True)
    return result.stdout


def package_files(directory: Path, version: str, platform: str) -> list[Path]:
    prefix = f"WeChatDataAnalysis-Advanced-Unlimited-{version}"
    if platform == "windows":
        names = [f"{prefix}-Setup.exe"]
        optional = [f"{prefix}-Setup.exe.blockmap"]
        metadata = "latest.yml"
    else:
        names = [f"{prefix}-mac-arm64.dmg"]
        optional = [f"{prefix}-mac-arm64.zip", f"{prefix}-mac-arm64.zip.blockmap"]
        metadata = "latest-mac.yml"
    files = [directory / name for name in names]
    for file in files:
        if not file.is_file():
            raise ValueError(f"缺少现成安装包：{file}")
    files.extend(directory / name for name in optional if (directory / name).is_file())
    update_file = directory / metadata
    if update_file.is_file():
        content = update_file.read_text(encoding="utf-8-sig")
        update_package = f"{prefix}-Setup.exe" if platform == "windows" else f"{prefix}-mac-arm64.zip"
        if not (directory / update_package).is_file() or update_package not in content:
            raise ValueError(f"{metadata} 未指向本次包体，不能发布。")
        files.append(update_file)
    return files


def release_notes(version: str, platforms: set[str]) -> str:
    notes_url = os.environ.get("CHANGELOG_URL", "").strip()
    if not notes_url:
        raise ValueError("请设置 CHANGELOG_URL，与官网更新日志使用同一个接口。")
    with urlopen(notes_url) as response:
        payload = json.load(response)
    rows = [row for row in payload["items"] if row.get("version") == version]
    parts = [f"# WeChatDataAnalysis {version}",
             "桌面安装包统一使用高级版构建。普通功能与高级版功能的使用范围以本版本应用内说明为准。"]
    for platform in sorted(platforms):
        changes = [change for row in rows if platform in row.get("platforms", []) for change in row.get("changes", [])]
        if not changes:
            raise ValueError(f"更新日志接口尚无 {version} / {platform} 的内容，请先同步对应版本的更新日志。")
        parts.append(f"## {PLATFORM_LABELS[platform]}")
        parts.append("\n".join(f"- {CHANGE_LABELS[change['type']]}：{change['text']}" for change in changes))
    parts.append("[查看全部更新日志](https://lifearchiveproject.github.io/WeChatDataAnalysis/changelog.html)")
    return "\n\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="安装包实际发布版本，如 2.5.11.0")
    parser.add_argument("--platform", required=True, choices=PLATFORM_LABELS)
    parser.add_argument("--assets", required=True, type=Path, help="高级版构建产物目录")
    parser.add_argument("--publish", action="store_true", help="上传包体并发布 GitHub Release；省略时只准备更新说明")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", args.version):
        parser.error("version 必须与安装包一致，使用四段数字。")
    assets = package_files(args.assets.resolve(), args.version, args.platform)
    tag = f"v{args.version}"
    existing = None
    platforms = {args.platform}
    if args.publish:
        try:
            existing = json.loads(gh("release", "view", tag, "--json", "isDraft,assets"))
        except subprocess.CalledProcessError as error:
            if "release not found" not in error.stderr.lower() and "404" not in error.stderr:
                raise
        if existing:
            names = {asset["name"] for asset in existing["assets"]}
            prefix = f"WeChatDataAnalysis-Advanced-Unlimited-{args.version}"
            if f"{prefix}-Setup.exe" in names:
                platforms.add("windows")
            if f"{prefix}-mac-arm64.dmg" in names:
                platforms.add("macos")
            if not existing["isDraft"] and any(asset.name in names for asset in assets):
                raise ValueError("该平台包体已经发布，请为不同内容使用新的实际构建版本。")
    notes = args.assets.resolve() / f"release-notes-{args.platform}.md"
    notes.write_text(release_notes(args.version, platforms), encoding="utf-8")
    print(f"更新说明：{notes}")
    for asset in assets:
        print(f"安装包附件：{asset}")
    if not args.publish:
        return
    if existing:
        upload = ["release", "upload", tag, *(str(asset) for asset in assets)]
        if existing["isDraft"]:
            upload.append("--clobber")
        gh(*upload)
    else:
        gh("release", "create", tag, *(str(asset) for asset in assets), "--draft", "--target", "main",
           "--title", f"WeChatDataAnalysis {args.version}", "--notes-file", str(notes))
    gh("release", "edit", tag, "--notes-file", str(notes), "--draft=false", "--latest")
    print(f"已发布：https://github.com/{REPOSITORY}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
