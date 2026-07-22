use regex::Regex;
use std::env;
use std::fs;
use std::path::{Path, PathBuf};

const STYLE_KEY: &[u8] = b"wce-export-style-202607";

fn read(path: &Path) -> String {
    println!("cargo:rerun-if-changed={}", path.display());
    fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("failed to read export style {}: {e}", path.display()))
}

fn ui_public_dir(crate_dir: &Path) -> PathBuf {
    if let Ok(value) = env::var("WCE_UI_PUBLIC_DIR") {
        let path = PathBuf::from(value);
        if path.is_dir() {
            return path;
        }
    }
    crate_dir
        .join("..")
        .join("..")
        .join("frontend")
        .join(".output")
        .join("public")
}

fn generated_ui_css(crate_dir: &Path) -> String {
    let nuxt_dir = ui_public_dir(crate_dir).join("_nuxt");
    let mut entries: Vec<PathBuf> = fs::read_dir(&nuxt_dir)
        .unwrap_or_else(|e| panic!("Nuxt UI output missing at {}: {e}", nuxt_dir.display()))
        .filter_map(Result::ok)
        .map(|item| item.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .map(|name| name.starts_with("entry.") && name.ends_with(".css"))
                .unwrap_or(false)
        })
        .collect();
    entries.sort_by_key(|path| fs::metadata(path).map(|meta| meta.len()).unwrap_or(0));
    let entry = entries
        .pop()
        .unwrap_or_else(|| panic!("Nuxt entry CSS missing at {}", nuxt_dir.display()));
    println!("cargo:rerun-if-changed={}", entry.display());

    let scoped = Regex::new(r"\[data-v-[0-9a-fA-F]{8}\]").expect("valid scoped selector regex");
    let mut css = scoped.replace_all(&read(&entry), "").into_owned();

    let mut chunks: Vec<PathBuf> = fs::read_dir(&nuxt_dir)
        .expect("Nuxt UI output remains readable")
        .filter_map(Result::ok)
        .map(|item| item.path())
        .filter(|path| {
            path.file_name()
                .and_then(|name| name.to_str())
                .map(|name| name.contains("_username_") && name.ends_with(".css"))
                .unwrap_or(false)
        })
        .collect();
    chunks.sort();
    for path in chunks {
        css.push('\n');
        css.push_str(&scoped.replace_all(&read(&path), ""));
    }
    css
}

fn encoded_const(name: &str, value: &str) -> String {
    let bytes: Vec<String> = value
        .as_bytes()
        .iter()
        .enumerate()
        .map(|(index, byte)| (byte ^ STYLE_KEY[index % STYLE_KEY.len()]).to_string())
        .collect();
    format!("const {name}: &[u8] = &[{}];\n", bytes.join(","))
}

fn main() {
    if env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("macos") {
        println!("cargo:rustc-link-arg=-undefined");
        println!("cargo:rustc-link-arg=dynamic_lookup");
    }

    let crate_dir = PathBuf::from(env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR"));
    let src = crate_dir.join("src");

    let fallback = read(&src.join("css_fallback.css"));
    let patch = read(&src.join("css_patch.css"));
    let ui = generated_ui_css(&crate_dir);
    let chat = format!("{ui}\n{patch}");
    let sns = format!("{chat}\n{}", read(&src.join("css_sns.css")));
    let records_project = read(&src.join("css_records_project.css"));
    let records_generic = read(&src.join("css_records_generic.css"));
    let contacts = read(&src.join("css_contacts.css"));

    let mut generated = format!("const STYLE_KEY: &[u8] = &{:?};\n", STYLE_KEY);
    for (name, value) in [
        ("STYLE_FALLBACK", fallback.as_str()),
        ("STYLE_PATCH", patch.as_str()),
        ("STYLE_CHAT", chat.as_str()),
        ("STYLE_SNS", sns.as_str()),
        ("STYLE_RECORDS_PROJECT", records_project.as_str()),
        ("STYLE_RECORDS_GENERIC", records_generic.as_str()),
        ("STYLE_CONTACTS", contacts.as_str()),
    ] {
        generated.push_str(&encoded_const(name, value));
    }

    let out = PathBuf::from(env::var("OUT_DIR").expect("OUT_DIR")).join("styles.rs");
    fs::write(&out, generated).unwrap_or_else(|e| panic!("failed to write {}: {e}", out.display()));
}
