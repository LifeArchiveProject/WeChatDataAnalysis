#!/bin/zsh
set -euo pipefail

tool_dir="${0:A:h}"
repo_root="${tool_dir:h}"
python_bin="$repo_root/.venv/bin/python"
dist_dir="${WEDATA_KEY_EXTRACTOR_DIST_DIR:-$tool_dir/dist}"
work_dir="$tool_dir/build"
spec_dir="$tool_dir/spec"
app_path="$dist_dir/WeDataKeyExtractor.app"
version="1.1.11"
build_number="14"
arch_name="$(/usr/bin/uname -m)"
case "$arch_name" in
  arm64|x86_64) ;;
  *)
    print -u2 "不支持的 Mac 架构: $arch_name"
    exit 1
    ;;
esac
zip_path="$dist_dir/WeDataKeyExtractor-$version-mac-$arch_name.zip"
temporary_zip="$dist_dir/.WeDataKeyExtractor-$version-mac-$arch_name.zip.building"
notary_zip="$dist_dir/.WeDataKeyExtractor-$version-notary.zip"

set_plist_string() {
  local key="$1"
  local value="$2"
  local plist="$3"
  if /usr/libexec/PlistBuddy -c "Print :$key" "$plist" >/dev/null 2>&1; then
    /usr/libexec/PlistBuddy -c "Set :$key $value" "$plist"
  else
    /usr/libexec/PlistBuddy -c "Add :$key string $value" "$plist"
  fi
}

clear_signature_breaking_xattrs() {
  local target="$1"
  local attribute
  for attribute in com.apple.FinderInfo com.apple.ResourceFork; do
    if /usr/bin/xattr -p "$attribute" "$target" >/dev/null 2>&1; then
      /usr/bin/xattr -d "$attribute" "$target"
    fi
  done
}

if [[ ! -x "$python_bin" ]]; then
  print -u2 "找不到项目 Python 环境: $python_bin"
  exit 1
fi

"$python_bin" -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --onedir \
  --name WeDataKeyExtractor \
  --osx-bundle-identifier com.wedata.keyextractor \
  --paths "$repo_root/src" \
  --distpath "$dist_dir" \
  --workpath "$work_dir" \
  --specpath "$spec_dir" \
  --hidden-import tkinter \
  --hidden-import _tkinter \
  --add-data "$repo_root/src/wechat_decrypt_tool/native/macos/source/wcdb_native_capture.c:wechat_decrypt_tool/native/macos/source" \
  --add-data "$tool_dir/THIRD_PARTY_NOTICES.md:." \
  "$tool_dir/main.py"

set_plist_string "CFBundleDisplayName" "WeData 密钥提取器" "$app_path/Contents/Info.plist"
set_plist_string "CFBundleShortVersionString" "$version" "$app_path/Contents/Info.plist"
set_plist_string "CFBundleVersion" "$build_number" "$app_path/Contents/Info.plist"
clear_signature_breaking_xattrs "$app_path"

identity="${WEDATA_CODESIGN_IDENTITY:-}"
[[ -n "$identity" ]] || identity="-"
if [[ "$identity" != "-" ]] && ! /usr/bin/security find-identity -v -p codesigning | /usr/bin/grep -Fq "\"$identity\""; then
  print -u2 "找不到指定的代码签名证书: $identity"
  exit 1
fi

signing_arguments=(
  --force
  --deep
  --options runtime
  --entitlements "$tool_dir/entitlements.plist"
  --identifier com.wedata.keyextractor
  --sign "$identity"
)
if [[ "$identity" == "WeData Local Code Signing" ]]; then
  signer_sha1="$(
    /usr/bin/security find-identity -v -p codesigning \
      | /usr/bin/sed -nE '/"WeData Local Code Signing"/s/^[[:space:]]*[0-9]+\) ([0-9A-Fa-f]{40}).*/\1/p' \
      | /usr/bin/head -1
  )"
  if [[ -z "$signer_sha1" ]]; then
    print -u2 "无法读取本地代码签名证书指纹"
    exit 1
  fi
  signing_arguments+=(
    --timestamp=none
    --requirements "=designated => identifier \"com.wedata.keyextractor\" and certificate leaf = H\"$signer_sha1\""
  )
fi
/usr/bin/codesign "${signing_arguments[@]}" "$app_path"
clear_signature_breaking_xattrs "$app_path"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app_path"

if [[ -n "${WEDATA_NOTARY_PROFILE:-}" ]]; then
  if [[ "$identity" == "-" ]]; then
    print -u2 "公证必须同时提供 Developer ID Application 签名证书"
    exit 1
  fi
  /usr/bin/ditto -c -k --sequesterRsrc --keepParent "$app_path" "$notary_zip"
  /usr/bin/xcrun notarytool submit "$notary_zip" \
    --keychain-profile "$WEDATA_NOTARY_PROFILE" \
    --wait
  /usr/bin/xcrun stapler staple "$app_path"
  /usr/bin/xcrun stapler validate "$app_path"
fi

"$python_bin" "$tool_dir/release_audit.py" "$app_path"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$app_path" "$temporary_zip"
/bin/mv -f "$temporary_zip" "$zip_path"
clear_signature_breaking_xattrs "$app_path"
clear_signature_breaking_xattrs "$zip_path"
"$python_bin" "$tool_dir/release_audit.py" "$zip_path"
verification_dir="$(/usr/bin/mktemp -d /tmp/wedata-key-package.XXXXXX)"
/usr/bin/ditto -x -k "$zip_path" "$verification_dir"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$verification_dir/WeDataKeyExtractor.app"
/bin/rm -rf "$verification_dir"
/usr/bin/shasum -a 256 "$zip_path" > "$zip_path.sha256"

print "已生成: $app_path"
print "安装包: $zip_path"
