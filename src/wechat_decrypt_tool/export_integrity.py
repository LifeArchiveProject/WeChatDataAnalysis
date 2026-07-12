from __future__ import annotations

import base64
import hashlib
import html
import importlib.machinery
import importlib.util
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable


_NATIVE_ERROR = "导出完整性组件初始化失败。"


def load_wce_integrity_native() -> Any:
    module_name = f"{__package__}.native.wce_integrity"
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "native" / "wce_integrity" / "target" / "release" / "wce_integrity.dll",
        repo_root / "native" / "wce_integrity" / "target-next" / "release" / "wce_integrity.dll",
        Path(__file__).resolve().parent / "native" / "wce_integrity.pyd",
    ]
    candidates = [path for path in candidates if path.is_file()]
    candidates.sort(key=lambda path: path.stat().st_mtime_ns, reverse=True)
    for build_path in candidates:
        try:
            loader = importlib.machinery.ExtensionFileLoader(module_name, str(build_path))
            spec = importlib.util.spec_from_file_location(module_name, build_path, loader=loader)
            if spec is not None:
                native = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = native
                loader.exec_module(native)
                return native
        except Exception:
            sys.modules.pop(module_name, None)

    try:
        from .native import wce_integrity  # type: ignore

        return wce_integrity
    except Exception as exc:
        raise RuntimeError(_NATIVE_ERROR) from exc


def export_css(kind: str) -> str:
    try:
        value = str(load_wce_integrity_native().export_css(str(kind or "")))
    except Exception as exc:
        raise RuntimeError(_NATIVE_ERROR) from exc
    if not value.strip():
        raise RuntimeError(_NATIVE_ERROR)
    return value


def _native_text(function_name: str, *args: Any) -> str:
    try:
        value = str(getattr(load_wce_integrity_native(), function_name)(*args))
    except Exception as exc:
        raise RuntimeError(_NATIVE_ERROR) from exc
    if not value.strip():
        raise RuntimeError(_NATIVE_ERROR)
    return value


def _native_paths(function_name: str, export_id: str, length: int) -> list[str]:
    try:
        values = json.loads(_native_text(function_name, str(export_id or "")))
    except Exception as exc:
        raise RuntimeError(_NATIVE_ERROR) from exc
    if not isinstance(values, list) or len(values) < length:
        raise RuntimeError(_NATIVE_ERROR)
    result = [str(values[index] or "").strip() for index in range(length)]
    if any(not value for value in result):
        raise RuntimeError(_NATIVE_ERROR)
    return result


def _sri_sha384(value: str) -> str:
    digest = hashlib.sha384(str(value or "").encode("utf-8")).digest()
    return "sha384-" + base64.b64encode(digest).decode("ascii")


def prepare_html_zip_assets(export_id: str, css_payload: str) -> dict[str, str]:
    css_path, runtime_path, integrity_path = _native_paths("asset_paths", export_id, 3)
    manifest_path, signature_path = _native_paths("integrity_sidecar_paths", export_id, 2)
    runtime_payload = _native_text("runtime_js")
    return {
        "cssPath": css_path,
        "jsPath": runtime_path,
        "integrityPath": integrity_path,
        "manifestPath": manifest_path,
        "signaturePath": signature_path,
        "cssIntegrity": _sri_sha384(css_payload),
        "jsIntegrity": _sri_sha384(runtime_payload),
        "cssPayload": css_payload,
        "jsPayload": runtime_payload,
    }


def protect_html_document(
    document: str,
    *,
    stylesheet_tag: str,
    runtime_tag: str,
    integrity_tag: str,
) -> str:
    text = str(document or "")
    if "</head>" not in text.lower() or "</body>" not in text.lower():
        raise RuntimeError("HTML 导出页面结构不完整。")
    gate = _native_text("gate_style")
    attribution = _native_text("attribution_html")
    head_payload = gate + stylesheet_tag + integrity_tag + runtime_tag
    text = re.sub(r"(?i)</head>", head_payload + "</head>", text, count=1)

    def mark_body(match: re.Match[str]) -> str:
        attrs = str(match.group(1) or "")
        if "data-wce-protected-root" not in attrs.lower():
            attrs += ' data-wce-protected-root="1"'
        return "<body" + attrs + ">"

    text = re.sub(r"(?i)<body([^>]*)>", mark_body, text, count=1)
    text = re.sub(r"(?i)</body>", attribution + "</body>", text, count=1)
    return text


def protect_html_document_with_external_assets(document: str, assets: dict[str, str]) -> str:
    stylesheet_tag = (
        f'<link id="wceStyle" rel="stylesheet" href="{html.escape(assets["cssPath"], quote=True)}" '
        f'data-wce-sri="{html.escape(assets["cssIntegrity"], quote=True)}" />\n'
    )
    runtime_tag = (
        f'<script defer src="{html.escape(assets["jsPath"], quote=True)}" '
        f'data-wce-sri="{html.escape(assets["jsIntegrity"], quote=True)}"></script>\n'
    )
    integrity_tag = _native_text("integrity_script_tag", assets["integrityPath"])
    return protect_html_document(
        document,
        stylesheet_tag=stylesheet_tag,
        runtime_tag=runtime_tag,
        integrity_tag=integrity_tag,
    )


def _arcname(value: Any) -> str:
    result = str(value or "").strip().replace("\\", "/").lstrip("/")
    while "//" in result:
        result = result.replace("//", "/")
    return result


def _native_entry_bytes(arcname: Any, data: Any) -> dict[str, Any]:
    if isinstance(data, str):
        raw = data.encode("utf-8")
    elif isinstance(data, bytes):
        raw = data
    elif isinstance(data, bytearray):
        raw = bytes(data)
    elif isinstance(data, memoryview):
        raw = data.tobytes()
    else:
        raw = bytes(data or b"")
    try:
        return json.loads(str(load_wce_integrity_native().record_bytes(_arcname(arcname), raw)))
    except Exception as exc:
        raise RuntimeError("导出完整性组件记录文件失败。") from exc


def native_file_entry(path: Path, arcname: Any = None) -> dict[str, Any]:
    target = Path(path)
    try:
        return json.loads(
            str(load_wce_integrity_native().record_file(str(target), _arcname(arcname or target.name)))
        )
    except Exception as exc:
        raise RuntimeError("导出完整性组件记录文件失败。") from exc


def seal_entries(
    export_id: str,
    entries: Iterable[dict[str, Any]],
    *,
    html_assets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        result = json.loads(
            str(
                load_wce_integrity_native().seal_export(
                    str(export_id or ""),
                    json.dumps(list(entries), ensure_ascii=False, separators=(",", ":")),
                    json.dumps(dict(html_assets or {}), ensure_ascii=False, separators=(",", ":")),
                )
            )
        )
    except Exception as exc:
        raise RuntimeError("导出完整性组件生成签名失败。") from exc
    if not isinstance(result, dict) or not str(result.get("signature") or "").strip():
        raise RuntimeError("导出完整性组件返回结果为空。")
    return result


class IntegrityZipWriter:
    def __init__(self, archive: zipfile.ZipFile):
        load_wce_integrity_native()
        self._archive = archive
        self._entries: dict[str, dict[str, Any]] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._archive, name)

    def writestr(self, zinfo_or_arcname: Any, data: Any, *args: Any, **kwargs: Any) -> Any:
        result = self._archive.writestr(zinfo_or_arcname, data, *args, **kwargs)
        arcname = getattr(zinfo_or_arcname, "filename", zinfo_or_arcname)
        normalized = _arcname(arcname)
        if normalized and not normalized.endswith("/"):
            self._entries[normalized] = _native_entry_bytes(normalized, data)
        return result

    def write(self, filename: Any, arcname: Any = None, *args: Any, **kwargs: Any) -> Any:
        if arcname is None:
            result = self._archive.write(filename, *args, **kwargs)
        else:
            result = self._archive.write(filename, arcname, *args, **kwargs)
        normalized = _arcname(arcname if arcname is not None else filename)
        if normalized and not normalized.endswith("/"):
            self._entries[normalized] = native_file_entry(Path(filename), normalized)
        return result

    def add_file_entry(self, path: Path, arcname: Any) -> None:
        normalized = _arcname(arcname)
        if normalized and not normalized.endswith("/"):
            self._entries[normalized] = native_file_entry(Path(path), normalized)

    def integrity_entries(self) -> list[dict[str, Any]]:
        return [self._entries[key] for key in sorted(self._entries)]


def write_zip_integrity_sidecars(
    writer: IntegrityZipWriter,
    export_id: str,
    *,
    manifest_path: str = "_integrity/manifest.wce",
    signature_path: str = "_integrity/signature.wce",
) -> dict[str, Any]:
    assets = {
        "manifestPath": _arcname(manifest_path),
        "signaturePath": _arcname(signature_path),
    }
    sealed = seal_entries(export_id, writer.integrity_entries(), html_assets=assets)
    writer.writestr(assets["manifestPath"], str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""))
    writer.writestr(assets["signaturePath"], str(sealed.get("signature") or "") + "\n")
    return sealed


def write_active_html_zip_integrity(
    writer: IntegrityZipWriter,
    export_id: str,
    assets: dict[str, str],
) -> dict[str, Any]:
    sealed = seal_entries(export_id, writer.integrity_entries(), html_assets=assets)
    writer.writestr(
        assets["manifestPath"],
        str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""),
    )
    writer.writestr(assets["signaturePath"], str(sealed.get("signature") or "") + "\n")
    writer.writestr(assets["integrityPath"], str(sealed.get("bundle") or ""))
    return sealed


def write_file_integrity_sidecars(path: Path, export_id: str) -> tuple[Path, Path]:
    target = Path(path)
    manifest_path = target.with_name(target.name + ".wce")
    signature_path = target.with_name(target.name + ".wce.sig")
    sealed = seal_entries(
        export_id,
        [native_file_entry(target, target.name)],
        html_assets={
            "manifestPath": manifest_path.name,
            "signaturePath": signature_path.name,
        },
    )
    manifest_path.write_text(
        str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""),
        encoding="utf-8",
        newline="\n",
    )
    signature_path.write_text(str(sealed.get("signature") or "") + "\n", encoding="utf-8", newline="\n")
    return manifest_path, signature_path


def _prepare_inline_protected_html(file_name: str, document: str, export_id: str) -> tuple[str, dict[str, str]]:
    style_match = re.search(r"(?is)<style>(.*?)</style>", str(document or ""))
    if style_match is None:
        raise RuntimeError("HTML 导出页面缺少原生样式。")
    css_payload = str(style_match.group(1) or "")
    runtime_payload = _native_text("runtime_js")
    safe_name = Path(str(file_name or "export.html")).name or "export.html"
    short = hashlib.sha256(f"{export_id}:{safe_name}".encode("utf-8")).hexdigest()[:16]
    assets = {
        "cssPath": "@inline-style",
        "jsPath": "@inline-runtime",
        "integrityPath": f"{safe_name}.{short}.wce.js",
        "manifestPath": safe_name + ".wce",
        "signaturePath": safe_name + ".wce.sig",
        "cssIntegrity": _sri_sha384(css_payload),
        "jsIntegrity": _sri_sha384(runtime_payload),
    }
    styled_document = re.sub(
        r"(?is)<style>",
        f'<style id="wceStyle" data-wce-style="1" data-wce-sri="{html.escape(assets["cssIntegrity"], quote=True)}">',
        str(document or ""),
        count=1,
    )
    protected = protect_html_document(
        styled_document,
        stylesheet_tag="",
        integrity_tag=_native_text("integrity_script_tag", assets["integrityPath"]),
        runtime_tag=(
            f'<script data-wce-runtime="1" data-wce-sri="{html.escape(assets["jsIntegrity"], quote=True)}">'
            f"{runtime_payload}</script>\n"
        ),
    )
    return protected, assets


def write_protected_html_file(path: Path, document: str, export_id: str) -> tuple[Path, Path]:
    target = Path(path)
    protected, assets = _prepare_inline_protected_html(target.name, document, export_id)
    integrity_path = target.with_name(assets["integrityPath"])
    manifest_path = target.with_name(assets["manifestPath"])
    signature_path = target.with_name(assets["signaturePath"])
    candidates = [target, integrity_path, manifest_path, signature_path]
    try:
        target.write_text(protected, encoding="utf-8", newline="\n")
        sealed = seal_entries(export_id, [native_file_entry(target, target.name)], html_assets=assets)
        integrity_path.write_text(str(sealed.get("bundle") or ""), encoding="utf-8", newline="\n")
        manifest_path.write_text(
            str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""),
            encoding="utf-8",
            newline="\n",
        )
        signature_path.write_text(str(sealed.get("signature") or "") + "\n", encoding="utf-8", newline="\n")
    except Exception:
        for candidate in candidates:
            try:
                candidate.unlink(missing_ok=True)
            except Exception:
                pass
        raise
    return manifest_path, signature_path


def seal_protected_html_bytes(file_name: str, data: bytes, export_id: str) -> dict[str, str]:
    safe_name = Path(str(file_name or "export.html")).name or "export.html"
    try:
        document = bytes(data or b"").decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("HTML 导出内容不是有效 UTF-8。") from exc
    protected, assets = _prepare_inline_protected_html(safe_name, document, export_id)
    protected_bytes = protected.encode("utf-8")
    sealed = seal_entries(export_id, [_native_entry_bytes(safe_name, protected_bytes)], html_assets=assets)
    return {
        "protectedContentBase64": base64.b64encode(protected_bytes).decode("ascii"),
        "integrityFileName": assets["integrityPath"],
        "integrity": str(sealed.get("bundle") or ""),
        "manifestFileName": assets["manifestPath"],
        "signatureFileName": assets["signaturePath"],
        "manifest": str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""),
        "signature": str(sealed.get("signature") or "") + "\n",
    }


def seal_bytes_artifact(file_name: str, data: bytes, export_id: str) -> dict[str, str]:
    safe_name = Path(str(file_name or "export.bin")).name or "export.bin"
    manifest_name = safe_name + ".wce"
    signature_name = safe_name + ".wce.sig"
    sealed = seal_entries(
        export_id,
        [_native_entry_bytes(safe_name, data)],
        html_assets={
            "manifestPath": manifest_name,
            "signaturePath": signature_name,
        },
    )
    return {
        "manifestFileName": manifest_name,
        "signatureFileName": signature_name,
        "manifest": str(sealed.get("manifestJson") or sealed.get("manifestCanonical") or ""),
        "signature": str(sealed.get("signature") or "") + "\n",
    }
