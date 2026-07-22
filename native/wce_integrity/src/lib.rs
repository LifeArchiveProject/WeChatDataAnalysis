use base64::{engine::general_purpose, Engine as _};
use html5ever::tendril::TendrilSink;
use html5ever::{local_name, namespace_url, ns, parse_document, parse_fragment, QualName};
use markup5ever_rcdom::{Handle, NodeData, RcDom};
use once_cell::sync::Lazy;
use p256::ecdsa::{signature::Signer, Signature, SigningKey};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use regex::Regex;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::fs;
use std::io::{Cursor, Read};

const ASSET_SALT: &str = "wce-html-export-assets-202607";
const PROJECT_URL: &str = "https://github.com/LifeArchiveProject/WeChatDataAnalysis";
const BRAND_TOKEN: &str = "wce-attr-202607";
const DEFAULT_SIGNING_KEY_HEX: &str =
    "931d8704d656acc64ca808b925b1c1c1b0688b2b70ca4f3fb33de1b659a3345e";
const RUNTIME_JS: &str = include_str!("runtime.js");
include!(concat!(env!("OUT_DIR"), "/styles.rs"));

static PAGE_FRAGMENT_JSON_RE: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"(?s)\bconst\s+html\s*=\s*(?P<json>.*?);\s*\n").expect("valid regex"));
static PAGE_FRAGMENT_GUARD_RE: Lazy<Regex> = Lazy::new(|| {
    Regex::new(r#"(?i)\bconst\s+seal\s*=\s*['\"](?P<seal>[0-9a-f]{64})['\"]\s*;"#)
        .expect("valid regex")
});

fn py_err(msg: impl Into<String>) -> PyErr {
    PyRuntimeError::new_err(msg.into())
}

fn sha256_hex(data: &[u8]) -> String {
    let digest = Sha256::digest(data);
    hex::encode(digest)
}

fn sha256_bytes(data: &[u8]) -> Vec<u8> {
    Sha256::digest(data).to_vec()
}

fn escape_attr(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('"', "&quot;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn zip_arcname(value: &str) -> String {
    let mut s = value.trim().replace('\\', "/");
    while s.starts_with('/') {
        s.remove(0);
    }
    while s.contains("//") {
        s = s.replace("//", "/");
    }
    s
}

fn base64_url_no_pad(data: &[u8]) -> String {
    general_purpose::URL_SAFE_NO_PAD.encode(data)
}

fn decode_style(data: &[u8]) -> PyResult<String> {
    let raw: Vec<u8> = data
        .iter()
        .enumerate()
        .map(|(index, byte)| byte ^ STYLE_KEY[index % STYLE_KEY.len()])
        .collect();
    String::from_utf8(raw).map_err(|e| py_err(format!("decode export style failed: {e}")))
}

fn signing_key() -> PyResult<SigningKey> {
    let raw_hex = option_env!("WCE_SIGNING_KEY_HEX")
        .filter(|v| !v.trim().is_empty())
        .unwrap_or(DEFAULT_SIGNING_KEY_HEX)
        .trim();
    let bytes =
        hex::decode(raw_hex).map_err(|e| py_err(format!("invalid signing key hex: {e}")))?;
    SigningKey::from_slice(&bytes).map_err(|e| py_err(format!("invalid signing key: {e}")))
}

fn public_key_value() -> PyResult<Value> {
    let sk = signing_key()?;
    let vk = sk.verifying_key();
    let point = vk.to_encoded_point(false);
    let x = point.x().ok_or_else(|| py_err("public key missing x"))?;
    let y = point.y().ok_or_else(|| py_err("public key missing y"))?;
    Ok(json!({
        "kty": "EC",
        "crv": "P-256",
        "x": base64_url_no_pad(x),
        "y": base64_url_no_pad(y),
    }))
}

fn asset_paths_value(export_id: &str) -> Value {
    let seed = sha256_hex(format!("{}:{}", ASSET_SALT, export_id).as_bytes());
    let short = &seed[..16];
    json!([
        format!("assets/_wce/c-{short}.css"),
        format!("assets/_wce/r-{short}.js"),
        format!("assets/_wce/i-{short}.js")
    ])
}

fn sidecar_paths_value(export_id: &str) -> Value {
    let seed = sha256_hex(format!("{}:manifest:{}", ASSET_SALT, export_id).as_bytes());
    let short = &seed[..16];
    json!([
        format!("assets/_wce/m-{short}.wce"),
        format!("assets/_wce/s-{short}.wce")
    ])
}

fn runtime_source() -> PyResult<String> {
    let key = public_key_value()?;
    let x = key.get("x").and_then(Value::as_str).unwrap_or("");
    let y = key.get("y").and_then(Value::as_str).unwrap_or("");
    if x.is_empty() || y.is_empty() {
        return Err(py_err("empty public key"));
    }
    Ok(RUNTIME_JS
        .replace("__WCE_PUBLIC_KEY_X__", x)
        .replace("__WCE_PUBLIC_KEY_Y__", y))
}

fn obfuscate_runtime_js(source: &str) -> String {
    let key_full = sha256_bytes(format!("{}:runtime", ASSET_SALT).as_bytes());
    let key = &key_full[..17];
    let packed: Vec<u8> = source
        .as_bytes()
        .iter()
        .enumerate()
        .map(|(i, b)| b ^ key[i % key.len()])
        .collect();
    let b64 = general_purpose::STANDARD.encode(packed);
    let chunks: Vec<String> = b64
        .as_bytes()
        .chunks(79)
        .map(|c| String::from_utf8_lossy(c).to_string())
        .collect();
    let chunks_json = serde_json::to_string(&chunks).unwrap_or_else(|_| "[]".to_string());
    let key_json = serde_json::to_string(&key.to_vec()).unwrap_or_else(|_| "[]".to_string());
    format!(
        "(()=>{{const _0={},_1={};let _2=atob(_0.join('')),_3=new Uint8Array(_2.length);for(let _4=0;_4<_2.length;_4++)_3[_4]=_2.charCodeAt(_4)^_1[_4%_1.length];let _5=(typeof TextDecoder!='undefined'?new TextDecoder('utf-8').decode(_3):String.fromCharCode.apply(null,_3));(0,Function)(_5)();}})();\n",
        chunks_json, key_json
    )
}

fn gate_style_value() -> String {
    "<style id=\"wceGateStyle\">html:not([data-wce-brand-ok=\"1\"]) .wce-root,html:not([data-wce-brand-ok=\"1\"]) .wce-index,html:not([data-wce-integrity-ok=\"1\"]) .wce-root,html:not([data-wce-integrity-ok=\"1\"]) .wce-index,html:not([data-wce-brand-ok=\"1\"]) body[data-wce-protected-root=\"1\"]>:not(#wceBrandBlocker),html:not([data-wce-integrity-ok=\"1\"]) body[data-wce-protected-root=\"1\"]>:not(#wceBrandBlocker){visibility:hidden}#wceBrandBlocker{position:fixed;inset:0;z-index:2147483647;display:grid;place-items:center;padding:24px;background:#ededed;color:#191919;font:14px/1.6 \"Segoe UI\",\"Microsoft YaHei UI\",sans-serif}#wceBrandBlocker .wce-brand-blocker-card{width:min(520px,100%);padding:24px;border:1px solid #d3d7d3;border-radius:8px;background:#fff}#wceBrandBlocker .wce-brand-blocker-title{font-size:18px;font-weight:600}#wceBrandBlocker .wce-brand-blocker-body{margin-top:8px;color:#6d746e}.wce-brand-attribution{display:flex;flex-wrap:wrap;align-items:center;justify-content:center;gap:6px 10px;padding:12px 16px;border-top:1px solid #e2e5e2;background:#fff;color:#6d746e;font-size:12px}.wce-brand-attribution a{color:#576b95;text-decoration:none}.wce-brand-dot{width:6px;height:6px;border-radius:50%;background:#07c160}</style>\n".to_string()
}

fn attribution_html_value() -> String {
    format!(
        "<div id=\"wceBrandAttribution\" class=\"wce-brand-attribution\" data-wce-brand=\"{}\"><span class=\"wce-brand-dot\" aria-hidden=\"true\"></span><span>通过 <strong>WeChatDataAnalysis</strong> 导出</span><a href=\"{}\" target=\"_blank\" rel=\"noreferrer noopener\">项目地址</a><span>仅用于个人数据备份、迁移与研究，请尊重聊天参与者隐私。</span></div>\n",
        escape_attr(BRAND_TOKEN),
        escape_attr(PROJECT_URL)
    )
}

fn integrity_script_tag_value(src: &str) -> String {
    format!(
        "  <script defer data-wce-integrity-bundle=\"1\" src=\"{}\"></script>\n",
        escape_attr(src)
    )
}

fn page_fragment_js_value(
    export_id: &str,
    arc_js: &str,
    page_no: i64,
    fragment_html: &str,
) -> PyResult<String> {
    let arc = zip_arcname(arc_js);
    let guard = page_fragment_guard_inner(export_id, &arc, page_no, fragment_html);
    let html_json = serde_json::to_string(fragment_html)
        .map_err(|e| py_err(format!("encode page fragment failed: {e}")))?;
    let seal_json = serde_json::to_string(&guard)
        .map_err(|e| py_err(format!("encode page guard failed: {e}")))?;
    Ok(format!(
        "(() => {{\n  const pageNo = {};\n  const seal = {};\n  const html = {};\n  try {{\n    const fn = window.__WCE_PAGE_LOADED__;\n    if (typeof fn === 'function') fn(pageNo, html, seal);\n    else {{\n      const q = (window.__WCE_PAGE_QUEUE__ = window.__WCE_PAGE_QUEUE__ || []);\n      q.push([pageNo, html, seal]);\n    }}\n  }} catch {{}}\n}})();\n",
        page_no, seal_json, html_json
    ))
}

fn sign_manifest(canonical: &str) -> PyResult<String> {
    let sk = signing_key()?;
    let sig: Signature = sk.sign(canonical.as_bytes());
    let sig_bytes = sig.to_bytes();
    Ok(base64_url_no_pad(sig_bytes.as_ref()))
}

fn push_dom_tokens(handle: &Handle, out: &mut Vec<Value>) {
    match &handle.data {
        NodeData::Document => {
            for child in handle.children.borrow().iter() {
                push_dom_tokens(child, out);
            }
        }
        NodeData::Element { name, attrs, .. } => {
            let tag = name.local.to_string().to_ascii_lowercase();
            let mut attr_rows: Vec<(String, String)> = Vec::new();
            for attr in attrs.borrow().iter() {
                let key = attr.name.local.to_string().to_ascii_lowercase();
                if key.is_empty() || key == "style" {
                    continue;
                }
                attr_rows.push((key, attr.value.to_string()));
            }
            attr_rows.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)));
            let attrs_json: Vec<Value> =
                attr_rows.into_iter().map(|(k, v)| json!([k, v])).collect();
            out.push(json!(["E", tag, attrs_json]));
            if tag == "script" || tag == "style" {
                return;
            }
            for child in handle.children.borrow().iter() {
                push_dom_tokens(child, out);
            }
        }
        NodeData::Text { contents } => {
            let text = contents.borrow().to_string();
            if !text.trim().is_empty() {
                out.push(json!(["T", text]));
            }
        }
        _ => {
            for child in handle.children.borrow().iter() {
                push_dom_tokens(child, out);
            }
        }
    }
}

fn find_body(handle: &Handle) -> Option<Handle> {
    if let NodeData::Element { name, .. } = &handle.data {
        if name.local.as_ref().eq_ignore_ascii_case("body") {
            return Some(handle.clone());
        }
    }
    for child in handle.children.borrow().iter() {
        if let Some(found) = find_body(child) {
            return Some(found);
        }
    }
    None
}

fn push_fragment_document_tokens(document: &Handle, out: &mut Vec<Value>) {
    if let Some(body) = find_body(document) {
        for child in body.children.borrow().iter() {
            push_dom_tokens(child, out);
        }
        return;
    }
    let children = document.children.borrow();
    if children.len() == 1 {
        if let NodeData::Element { name, .. } = &children[0].data {
            if name.local.as_ref().eq_ignore_ascii_case("html") {
                for child in children[0].children.borrow().iter() {
                    push_dom_tokens(child, out);
                }
                return;
            }
        }
    }
    for child in children.iter() {
        push_dom_tokens(child, out);
    }
}

fn markup_seal(text: &str, body_only: bool) -> String {
    let mut tokens: Vec<Value> = Vec::new();
    if body_only {
        let mut cursor = Cursor::new(text.as_bytes());
        if let Ok(dom) = parse_document(RcDom::default(), Default::default())
            .from_utf8()
            .read_from(&mut cursor)
        {
            if let Some(body) = find_body(&dom.document) {
                push_dom_tokens(&body, &mut tokens);
            }
        }
    } else {
        let context = QualName::new(None, ns!(html), local_name!("template"));
        let mut cursor = Cursor::new(text.as_bytes());
        if let Ok(dom) = parse_fragment(RcDom::default(), Default::default(), context, Vec::new())
            .from_utf8()
            .read_from(&mut cursor)
        {
            push_fragment_document_tokens(&dom.document, &mut tokens);
        }
    }
    let payload = serde_json::to_string(&tokens).unwrap_or_else(|_| "[]".to_string());
    sha256_hex(payload.as_bytes())
}

fn page_fragment_guard_inner(
    export_id: &str,
    arc_js: &str,
    page_no: i64,
    fragment_html: &str,
) -> String {
    let raw = format!(
        "{}:page:{}:{}:{}:{}",
        ASSET_SALT,
        export_id,
        zip_arcname(arc_js),
        page_no,
        fragment_html
    );
    sha256_hex(raw.as_bytes())
}

fn page_fragment_seal_from_js(text: &str) -> String {
    let Some(caps) = PAGE_FRAGMENT_JSON_RE.captures(text) else {
        return String::new();
    };
    let Some(raw_json) = caps.name("json").map(|m| m.as_str()) else {
        return String::new();
    };
    match serde_json::from_str::<String>(raw_json) {
        Ok(fragment) => markup_seal(&fragment, false),
        Err(_) => String::new(),
    }
}

fn page_fragment_guard_from_js(text: &str) -> String {
    PAGE_FRAGMENT_GUARD_RE
        .captures(text)
        .and_then(|caps| caps.name("seal").map(|m| m.as_str().to_ascii_lowercase()))
        .unwrap_or_default()
}

fn entry_for_bytes(arcname: &str, raw: &[u8]) -> Value {
    let arc = zip_arcname(arcname);
    let lower = arc.to_ascii_lowercase();
    let mut obj = serde_json::Map::new();
    obj.insert("path".to_string(), json!(arc));
    obj.insert("size".to_string(), json!(raw.len()));
    obj.insert("sha256".to_string(), json!(sha256_hex(raw)));
    if lower.ends_with(".html") || lower.ends_with(".htm") {
        let text = String::from_utf8_lossy(raw);
        obj.insert("domSha256".to_string(), json!(markup_seal(&text, true)));
    } else if lower.contains("/pages/page-") && lower.ends_with(".js") {
        let text = String::from_utf8_lossy(raw);
        obj.insert(
            "fragmentDomSha256".to_string(),
            json!(page_fragment_seal_from_js(&text)),
        );
        obj.insert(
            "fragmentGuard".to_string(),
            json!(page_fragment_guard_from_js(&text)),
        );
    }
    Value::Object(obj)
}

fn valid_hex64(value: &str) -> bool {
    value.len() == 64 && value.as_bytes().iter().all(|b| b.is_ascii_hexdigit())
}

fn obfuscate_integrity_bundle(payload: &Value, export_id: &str) -> PyResult<String> {
    let raw = serde_json::to_string(payload)
        .map_err(|e| py_err(format!("encode integrity payload failed: {e}")))?
        .into_bytes();
    let seed_raw = format!("{}:integrity:{}", ASSET_SALT, export_id);
    let seed = Sha256::digest(seed_raw.as_bytes());
    let left: Vec<u8> = seed[..19].to_vec();
    let mut right_hasher = Sha256::new();
    right_hasher.update(&seed);
    right_hasher.update(b":split");
    let right_seed = right_hasher.finalize();
    let right: Vec<u8> = right_seed[..23].to_vec();
    let key_len = left.len().max(right.len());
    let mut key = Vec::with_capacity(key_len);
    for i in 0..key_len {
        key.push(left[i % left.len()] ^ right[(i * 7 + 3) % right.len()] ^ ((i * 13) as u8));
    }
    let packed: Vec<u8> = raw
        .iter()
        .enumerate()
        .map(|(i, b)| b ^ key[i % key.len()])
        .collect();
    let b64 = general_purpose::STANDARD.encode(packed);
    let chunks: Vec<String> = b64
        .as_bytes()
        .chunks(83)
        .map(|c| String::from_utf8_lossy(c).to_string())
        .collect();
    let chunks_json = serde_json::to_string(&chunks).unwrap_or_else(|_| "[]".to_string());
    let left_json = serde_json::to_string(&left).unwrap_or_else(|_| "[]".to_string());
    let right_json = serde_json::to_string(&right).unwrap_or_else(|_| "[]".to_string());
    Ok(format!(
        "(()=>{{const _p={};const _a={};const _b={};const _n=['__','WCE','_I'].join('');try{{Object.defineProperty(window,_n,{{value:{{p:_p,a:_a,b:_b}},configurable:false,writable:false}});}}catch(e){{window[_n]={{p:_p,a:_a,b:_b}};}}}})();\n",
        chunks_json, left_json, right_json
    ))
}

fn build_signed_manifest(
    export_id: &str,
    entries: Vec<Value>,
    html_assets: Value,
) -> PyResult<(Value, String, String)> {
    let css_path = zip_arcname(
        html_assets
            .get("cssPath")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    let js_path = zip_arcname(
        html_assets
            .get("jsPath")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    let integrity_path = zip_arcname(
        html_assets
            .get("integrityPath")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    let manifest_path = zip_arcname(
        html_assets
            .get("manifestPath")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );
    let signature_path = zip_arcname(
        html_assets
            .get("signaturePath")
            .and_then(Value::as_str)
            .unwrap_or(""),
    );

    let mut pages: Vec<String> = Vec::new();
    let mut page_seals: Vec<Value> = Vec::new();
    let mut fragment_seals: Vec<Value> = Vec::new();
    let mut files: Vec<Value> = Vec::new();

    for item in entries.iter() {
        let Some(path_raw) = item.get("path").and_then(Value::as_str) else {
            continue;
        };
        let path = zip_arcname(path_raw);
        if path.is_empty()
            || path == integrity_path
            || path == manifest_path
            || path == signature_path
        {
            continue;
        }
        let lower = path.to_ascii_lowercase();
        let size = item.get("size").and_then(Value::as_u64).unwrap_or(0);
        let sha = item
            .get("sha256")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_ascii_lowercase();
        if valid_hex64(&sha) {
            files.push(json!({"path": path, "size": size, "sha256": sha}));
        }
        if lower.ends_with(".html") || lower.ends_with(".htm") {
            pages.push(path.clone());
            let seal = item
                .get("domSha256")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            if valid_hex64(&seal) {
                page_seals.push(json!([path, seal]));
            }
        } else if lower.contains("/pages/page-") && lower.ends_with(".js") {
            let seal = item
                .get("fragmentDomSha256")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            let guard = item
                .get("fragmentGuard")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_ascii_lowercase();
            if valid_hex64(&seal) {
                if valid_hex64(&guard) {
                    fragment_seals.push(json!([path, seal, guard]));
                } else {
                    fragment_seals.push(json!([path, seal]));
                }
            }
        }
    }

    pages.sort();
    pages.dedup();
    page_seals.sort_by(|a, b| {
        a.get(0)
            .and_then(Value::as_str)
            .cmp(&b.get(0).and_then(Value::as_str))
    });
    fragment_seals.sort_by(|a, b| {
        a.get(0)
            .and_then(Value::as_str)
            .cmp(&b.get(0).and_then(Value::as_str))
    });
    files.sort_by(|a, b| {
        a.get("path")
            .and_then(Value::as_str)
            .cmp(&b.get("path").and_then(Value::as_str))
    });

    let manifest = json!({
        "v": 2,
        "e": export_id,
        "a": {
            "c": css_path,
            "r": js_path,
            "i": integrity_path,
            "m": manifest_path,
            "s": signature_path,
            "cs": html_assets.get("cssIntegrity").and_then(Value::as_str).unwrap_or(""),
            "rs": html_assets.get("jsIntegrity").and_then(Value::as_str).unwrap_or(""),
        },
        "p": pages,
        "h": page_seals,
        "q": fragment_seals,
        "f": files,
    });
    let canonical = serde_json::to_string(&manifest)
        .map_err(|e| py_err(format!("encode signed manifest failed: {e}")))?;
    let signature = sign_manifest(&canonical)?;
    Ok((manifest, canonical, signature))
}

#[pyfunction]
fn asset_paths(export_id: &str) -> PyResult<String> {
    serde_json::to_string(&asset_paths_value(export_id))
        .map_err(|e| py_err(format!("encode asset paths failed: {e}")))
}

#[pyfunction]
fn integrity_sidecar_paths(export_id: &str) -> PyResult<String> {
    serde_json::to_string(&sidecar_paths_value(export_id))
        .map_err(|e| py_err(format!("encode sidecar paths failed: {e}")))
}

#[pyfunction]
fn runtime_js() -> PyResult<String> {
    runtime_source().map(|source| obfuscate_runtime_js(&source))
}

#[pyfunction]
fn css_fallback() -> PyResult<String> {
    decode_style(STYLE_FALLBACK)
}

#[pyfunction]
fn css_patch() -> PyResult<String> {
    decode_style(STYLE_PATCH)
}

#[pyfunction]
fn export_css(kind: &str) -> PyResult<String> {
    let style = match kind.trim().to_ascii_lowercase().as_str() {
        "chat" => STYLE_CHAT,
        "sns" => STYLE_SNS,
        "records-project" => STYLE_RECORDS_PROJECT,
        "records-generic" => STYLE_RECORDS_GENERIC,
        "contacts" => STYLE_CONTACTS,
        _ => return Err(py_err(format!("unsupported export style: {kind}"))),
    };
    decode_style(style)
}

#[pyfunction]
fn gate_style() -> PyResult<String> {
    Ok(gate_style_value())
}

#[pyfunction]
fn attribution_html() -> PyResult<String> {
    Ok(attribution_html_value())
}

#[pyfunction]
fn integrity_script_tag(src: &str) -> PyResult<String> {
    Ok(integrity_script_tag_value(src))
}

#[pyfunction]
fn page_fragment_js(
    export_id: &str,
    arc_js: &str,
    page_no: i64,
    fragment_html: &str,
) -> PyResult<String> {
    page_fragment_js_value(export_id, arc_js, page_no, fragment_html)
}

#[pyfunction]
fn public_key_jwk_json() -> PyResult<String> {
    let value = public_key_value()?;
    serde_json::to_string(&value).map_err(|e| py_err(format!("encode public key failed: {e}")))
}

#[pyfunction]
fn page_fragment_guard(
    export_id: &str,
    arc_js: &str,
    page_no: i64,
    fragment_html: &str,
) -> PyResult<String> {
    Ok(page_fragment_guard_inner(
        export_id,
        arc_js,
        page_no,
        fragment_html,
    ))
}

#[pyfunction]
fn record_bytes(arcname: &str, data: &[u8]) -> PyResult<String> {
    serde_json::to_string(&entry_for_bytes(arcname, data))
        .map_err(|e| py_err(format!("encode entry failed: {e}")))
}

#[pyfunction]
fn record_file(filename: &str, arcname: &str) -> PyResult<String> {
    let arc = zip_arcname(arcname);
    let lower = arc.to_ascii_lowercase();
    if lower.ends_with(".html")
        || lower.ends_with(".htm")
        || (lower.contains("/pages/page-") && lower.ends_with(".js"))
    {
        let raw = fs::read(filename).map_err(|e| py_err(format!("read file failed: {e}")))?;
        return record_bytes(&arc, &raw);
    }

    let mut file = fs::File::open(filename).map_err(|e| py_err(format!("open file failed: {e}")))?;
    let mut hasher = Sha256::new();
    let mut size: u64 = 0;
    let mut buffer = vec![0u8; 1024 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|e| py_err(format!("read file failed: {e}")))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
        size += count as u64;
    }
    let entry = json!({
        "path": arc,
        "size": size,
        "sha256": hex::encode(hasher.finalize()),
    });
    serde_json::to_string(&entry).map_err(|e| py_err(format!("encode entry failed: {e}")))
}

#[pyfunction]
fn seal_export(export_id: &str, entries_json: &str, html_assets_json: &str) -> PyResult<String> {
    let entries: Vec<Value> = serde_json::from_str(entries_json)
        .map_err(|e| py_err(format!("invalid entries json: {e}")))?;
    let html_assets: Value = serde_json::from_str(html_assets_json)
        .map_err(|e| py_err(format!("invalid html assets json: {e}")))?;
    let (manifest, canonical_manifest, signature) =
        build_signed_manifest(export_id, entries, html_assets)?;
    let payload = json!({
        "v": 2,
        "g": canonical_manifest,
        "s": signature,
    });
    let bundle = obfuscate_integrity_bundle(&payload, export_id)?;
    let result = json!({
        "bundle": bundle,
        "manifestJson": serde_json::to_string_pretty(&manifest).unwrap_or_else(|_| canonical_manifest.clone()),
        "manifestCanonical": canonical_manifest,
        "signature": signature,
        "publicKey": public_key_value()?,
    });
    serde_json::to_string(&result).map_err(|e| py_err(format!("encode seal result failed: {e}")))
}

#[pymodule]
fn wce_integrity(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(asset_paths, m)?)?;
    m.add_function(wrap_pyfunction!(integrity_sidecar_paths, m)?)?;
    m.add_function(wrap_pyfunction!(runtime_js, m)?)?;
    m.add_function(wrap_pyfunction!(css_fallback, m)?)?;
    m.add_function(wrap_pyfunction!(css_patch, m)?)?;
    m.add_function(wrap_pyfunction!(export_css, m)?)?;
    m.add_function(wrap_pyfunction!(gate_style, m)?)?;
    m.add_function(wrap_pyfunction!(attribution_html, m)?)?;
    m.add_function(wrap_pyfunction!(integrity_script_tag, m)?)?;
    m.add_function(wrap_pyfunction!(page_fragment_js, m)?)?;
    m.add_function(wrap_pyfunction!(public_key_jwk_json, m)?)?;
    m.add_function(wrap_pyfunction!(page_fragment_guard, m)?)?;
    m.add_function(wrap_pyfunction!(record_bytes, m)?)?;
    m.add_function(wrap_pyfunction!(record_file, m)?)?;
    m.add_function(wrap_pyfunction!(seal_export, m)?)?;
    Ok(())
}
