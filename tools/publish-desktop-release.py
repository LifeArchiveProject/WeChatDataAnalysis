"""Publish existing Advanced packages and release notes from the public API."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from hashlib import file_digest
from pathlib import Path
from shutil import copyfileobj
from urllib.parse import urlsplit
from urllib.request import urlopen

REPOSITORY = "LifeArchiveProject/WeChatDataAnalysis"
PLATFORM_LABELS = {
    "windows": "Windows x64",
    "windows-arm64": "Windows ARM64",
    "macos": "macOS Apple Silicon",
    "linux-x64": "Linux x64",
    "linux-arm64": "Linux ARM64",
}
PLATFORM_GROUPS = {
    "desktop-all": ("windows", "windows-arm64", "macos"),
    "linux-all": ("linux-x64", "linux-arm64"),
}
CHANGELOG_PLATFORMS = {
    "windows": "windows", "windows-arm64": "windows", "macos": "macos",
    "linux-x64": "linux", "linux-arm64": "linux",
}
CHANGE_LABELS = {"feature": "新增", "improve": "优化", "fix": "修复"}


def gh(*args: str) -> str:
    result = subprocess.run(["gh", *args, "--repo", REPOSITORY], check=True, text=True, capture_output=True)
    return result.stdout


def package_name(version: str, platform: str) -> str:
    edition = "Web" if platform.startswith("linux-") else "Advanced"
    suffix = {
        "windows": "-Setup.exe", "windows-arm64": "-win-arm64-Setup.exe",
        "macos": "-mac-arm64.dmg", "linux-x64": "-linux-x86_64.tar.gz",
        "linux-arm64": "-linux-arm64.tar.gz",
    }[platform]
    return f"WeChatDataAnalysis-{edition}-Unlimited-{version}{suffix}"


def official_download_url(version: str, platform: str) -> str:
    source_directory = {
        "windows": "windows", "windows-arm64": "windows-arm64", "macos": "mac",
        "linux-x64": "linux", "linux-arm64": "linux",
    }[platform]
    return f"https://dl.fqyw.love/desktop-updates/{source_directory}/{package_name(version, platform)}"


def download_package(url: str, directory: Path, version: str, platform: str) -> Path:
    name = package_name(version, platform)
    expected_url = official_download_url(version, platform)
    if urlsplit(url) != urlsplit(expected_url):
        raise ValueError(f"下载直链必须是 {expected_url}")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    with urlopen(url) as response, target.open("wb") as output:
        expected_size = response.headers.get("Content-Length")
        copyfileobj(response, output)
    if expected_size is not None and target.stat().st_size != int(expected_size):
        raise ValueError(f"下载文件大小与服务器声明不一致：{name}")
    return target


def package_files(directory: Path, version: str, platform: str) -> list[Path]:
    name = package_name(version, platform)
    optional = []
    metadata = None
    if platform == "windows":
        optional = [f"{name}.blockmap"]
        metadata = "latest.yml"
        update_package = name
    elif platform == "windows-arm64":
        optional = [f"{name}.blockmap"]
    elif platform == "macos":
        update_package = name.removesuffix(".dmg") + ".zip"
        optional = [update_package, f"{update_package}.blockmap"]
        metadata = "latest-mac.yml"
    files = [directory / name]
    for file in files:
        if not file.is_file():
            raise ValueError(f"缺少现成安装包：{file}")
    files.extend(directory / name for name in optional if (directory / name).is_file())
    update_file = directory / metadata if metadata else None
    if update_file and update_file.is_file():
        content = update_file.read_text(encoding="utf-8-sig")
        if not (directory / update_package).is_file() or update_package not in content:
            raise ValueError(f"{metadata} 未指向本次包体，不能发布。")
        files.append(update_file)
    return files


def release_notes(version: str, platforms: set[str], links_only: bool = False) -> str:
    notes_url = os.environ.get("CHANGELOG_URL", "").strip()
    if not notes_url:
        raise ValueError("请设置 CHANGELOG_URL，与官网更新日志使用同一个接口。")
    with urlopen(notes_url) as response:
        payload = json.load(response)
    rows = [row for row in payload["items"] if row.get("version") == version]
    parts = [f"# WeChatDataAnalysis {version}"]
    if links_only:
        downloads = ["| 平台 | 官方下载 |", "| --- | --- |"]
        downloads.extend(f"| {label} | [下载安装包]({official_download_url(version, platform)}) |"
                         for platform, label in PLATFORM_LABELS.items() if platform in platforms)
        parts.append("## 官方下载\n\n" + "\n".join(downloads))
    parts.append("发行包使用高级版构建。普通功能与高级版功能的使用范围以本版本应用内说明为准。")
    if version.startswith("2.6.") and any(not platform.startswith("linux-") for platform in platforms):
        parts.append("2.6 系列已加入应用内更新源；请更新至最新版本后再提交反馈。")
        parts.append("旧普通版用户需手动安装一次高级版，之后通过应用内更新源获取更新。")
    else:
        parts.append("请更新至最新版本后再提交反馈。")
    groups: dict[str, list[str]] = {}
    for platform, label in PLATFORM_LABELS.items():
        if platform in platforms:
            groups.setdefault(CHANGELOG_PLATFORMS[platform], []).append(label)
    for platform, labels in groups.items():
        changes = [change for row in rows if platform in row.get("platforms", []) for change in row.get("changes", [])]
        if not changes:
            raise ValueError(f"更新日志接口尚无 {version} / {platform} 的内容，请先同步对应版本的更新日志。")
        parts.append(f"## {' / '.join(labels)}")
        parts.append("\n".join(f"- {CHANGE_LABELS[change['type']]}：{change['text']}" for change in changes))
    parts.append("[查看全部更新日志](https://wuuud.com/changelog)")
    return "\n\n".join(parts) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="安装包实际发布版本，如 2.5.11.0")
    parser.add_argument("--platform", required=True, choices=[*PLATFORM_LABELS, *PLATFORM_GROUPS])
    parser.add_argument("--assets", default=Path("release-assets"), type=Path, help="高级版构建产物目录或直链下载目录")
    parser.add_argument("--download-url", help="与版本和平台一致的官方成品直链")
    parser.add_argument("--links-only", action="store_true", help="仅发布官方直链，不下载或上传包体")
    parser.add_argument("--publish", action="store_true", help="上传包体并发布 GitHub Release；省略时只准备更新说明")
    args = parser.parse_args()
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", args.version):
        parser.error("version 必须与安装包一致，使用四段数字。")
    if args.platform in PLATFORM_GROUPS and not args.links_only:
        parser.error("平台组仅可与 --links-only 一起使用。")
    if args.links_only and args.download_url:
        parser.error("--links-only 不接受 --download-url。")
    directory = args.assets.resolve()
    if args.links_only:
        directory.mkdir(parents=True, exist_ok=True)
        assets = []
    else:
        assets = ([download_package(args.download_url, directory, args.version, args.platform)]
                  if args.download_url else package_files(directory, args.version, args.platform))
    tag = f"v{args.version}"
    existing = None
    platforms = set(PLATFORM_GROUPS.get(args.platform, (args.platform,)))
    if args.publish:
        try:
            existing = json.loads(gh("release", "view", tag, "--json", "isDraft,assets"))
        except subprocess.CalledProcessError as error:
            if "release not found" not in error.stderr.lower() and "404" not in error.stderr:
                raise
        if existing:
            names = {asset["name"] for asset in existing["assets"]}
            platforms.update(platform for platform in PLATFORM_LABELS
                             if package_name(args.version, platform) in names)
            if not existing["isDraft"] and any(asset.name in names for asset in assets):
                raise ValueError("该平台包体已经发布，请为不同内容使用新的实际构建版本。")
    notes = directory / f"release-notes-{args.platform}.md"
    notes.write_text(release_notes(args.version, platforms, args.links_only), encoding="utf-8")
    print(f"更新说明：{notes}")
    for asset in assets:
        with asset.open("rb") as package:
            checksum = file_digest(package, "sha256").hexdigest()
        print(f"安装包附件：{asset} ({asset.stat().st_size} bytes, SHA256: {checksum})")
    if not args.publish:
        return
    if existing:
        if assets:
            upload = ["release", "upload", tag, *(str(asset) for asset in assets)]
            if existing["isDraft"]:
                upload.append("--clobber")
            gh(*upload)
    else:
        gh("release", "create", tag, *(str(asset) for asset in assets), "--draft", "--target", "main",
           "--title", f"WeChatDataAnalysis {args.version}", "--notes-file", str(notes))
    latest = "--latest=false" if args.links_only or all(platform.startswith("linux-") for platform in platforms) else "--latest"
    gh("release", "edit", tag, "--notes-file", str(notes), "--draft=false", latest)
    print(f"已发布：https://github.com/{REPOSITORY}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
