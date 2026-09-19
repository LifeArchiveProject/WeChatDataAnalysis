#!/bin/sh
# @@PRODUCT@@ @@VERSION@@ (linux-@@ARCH@@) 一键安装脚本 —— 由 Build-LinuxInstaller 生成，请勿手改。
#
# 设计取舍（Linux 没有安装包是刻意的）：
#   * 不做 AppImage / deb：作者的分发形态只有 Windows 安装包与 macOS dmg。
#   * 所以这里给一个「用户级、免 root」的安装脚本：解包到用户目录 + 桌面项 + 启动器。
#   * 产物身份靠内容哈希：脚本里内嵌 tarball 的 SHA-256，装之前先校验。
#
# 用法:
#   ./install.sh                  # 装到 ${XDG_DATA_HOME:-~/.local/share}/wechat-data-analysis
#   ./install.sh --prefix /opt/x  # 自定义前缀
#   ./install.sh --uninstall      # 卸载
set -eu

PRODUCT='@@PRODUCT@@'
VERSION='@@VERSION@@'
ARCH='@@ARCH@@'
PAYLOAD_NAME='@@PAYLOAD@@'
PAYLOAD_SHA256='@@SHA256@@'

DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
BIN_HOME="${XDG_BIN_HOME:-$HOME/.local/bin}"
DEFAULT_PREFIX="$DATA_HOME/wechat-data-analysis"
PREFIX="$DEFAULT_PREFIX"
UNINSTALL=0

die() { printf '错误: %s\n' "$1" >&2; exit 1; }
info() { printf '%s\n' "$1"; }

usage() {
  cat <<EOF
$PRODUCT $VERSION (linux-$ARCH)

  ./install.sh [--prefix DIR] [--uninstall]

  --prefix DIR   安装前缀，默认 $DEFAULT_PREFIX
  --uninstall    删除已安装版本、桌面项与启动器
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) [ $# -ge 2 ] || die "--prefix 需要一个目录参数"; PREFIX="$2"; shift 2 ;;
    --prefix=*) PREFIX="${1#--prefix=}"; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知参数: $1（用 --help 看用法）" ;;
  esac
done

case "$PREFIX" in
  /*) ;;
  *) die "--prefix 必须是绝对路径（收到 $PREFIX）" ;;
esac

# @@PRODUCT@@ 的微信内存扫描/提权边界：安装脚本本身绝不使用 sudo，
# 应用也必须在用户身份下运行（root 下 AppImage 的 FUSE 挂载对 root 不可见）。
if [ "$(id -u)" -eq 0 ]; then
  die "请以普通用户身份运行本脚本（不要用 sudo）。应用需要用户身份运行。"
fi

DESKTOP_FILE="$DATA_HOME/applications/wechat-data-analysis.desktop"
BIN_LINK="$BIN_HOME/wechat-data-analysis"

if [ "$UNINSTALL" -eq 1 ]; then
  removed=0
  rm -f "$DESKTOP_FILE" "$BIN_LINK" && removed=1
  if [ -d "$PREFIX" ]; then
    rm -rf "$PREFIX" && removed=1
  fi
  if [ "$removed" -eq 1 ]; then
    info "已卸载 $PRODUCT（$PREFIX）"
    info "提示: 用户数据目录没有被删除，需要时请自行清理。"
  else
    info "没有找到已安装的 $PRODUCT"
  fi
  exit 0
fi

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PAYLOAD="$SCRIPT_DIR/$PAYLOAD_NAME"
[ -f "$PAYLOAD" ] || die "找不到安装包 $PAYLOAD（请把 install.sh 与 $PAYLOAD_NAME 放在同一目录）"

verify_hash() {
  if command -v sha256sum >/dev/null 2>&1; then
    actual=$(sha256sum "$PAYLOAD" | awk '{print $1}')
  elif command -v shasum >/dev/null 2>&1; then
    actual=$(shasum -a 256 "$PAYLOAD" | awk '{print $1}')
  else
    die "找不到 sha256sum 或 shasum，无法校验安装包完整性"
  fi
  [ "$actual" = "$PAYLOAD_SHA256" ] || die "安装包校验失败：期望 $PAYLOAD_SHA256，实际 $actual"
}

verify_hash
info "校验通过: $PAYLOAD_NAME"

TARGET="$PREFIX/$VERSION"
[ "$TARGET" != "$PREFIX" ] || die "安装目标解析异常: $TARGET"

mkdir -p "$PREFIX" "$BIN_HOME"
STAGING="$PREFIX/.staging-$$"
rm -rf "$STAGING"
mkdir -p "$STAGING"

cleanup() { rm -rf "$STAGING"; }
trap cleanup EXIT HUP INT TERM

info "解包到 $TARGET ..."
tar -xzf "$PAYLOAD" -C "$STAGING" || die "解包失败"
[ -x "$STAGING/@@EXECUTABLE@@" ] || die "安装包里找不到可执行文件 @@EXECUTABLE@@"

rm -rf "$TARGET"
# staging 与 TARGET 同处 $PREFIX 下，rename 是原子的：不会留下半新半旧的目录。
mv "$STAGING" "$TARGET"
cleanup
trap - EXIT HUP INT TERM

# current 是原子切换的指针，升级时不会留下半新半旧的目录。
ln -sfn "$TARGET" "$PREFIX/current"

LAUNCHER="$PREFIX/bin/wechat-data-analysis"
mkdir -p "$PREFIX/bin"
cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/bin/sh
# 由 install.sh 生成：转发参数到当前版本的 Electron 主程序。
exec "$PREFIX/current/@@EXECUTABLE@@" "\$@"
LAUNCHER_EOF
chmod 0755 "$LAUNCHER"
ln -sfn "$LAUNCHER" "$BIN_LINK"

ICON="$PREFIX/current/resources/wechat-data-analysis.png"
mkdir -p "$DATA_HOME/applications"
{
  printf '[Desktop Entry]\n'
  printf 'Type=Application\n'
  printf 'Name=%s\n' "$PRODUCT"
  printf 'Comment=微信数据解密与分析工具\n'
  printf 'Exec=%s\n' "$LAUNCHER"
  if [ -f "$ICON" ]; then printf 'Icon=%s\n' "$ICON"; fi
  printf 'Terminal=false\n'
  printf 'Categories=Utility;\n'
  printf 'StartupWMClass=%s\n' "$PRODUCT"
} > "$DESKTOP_FILE"
chmod 0644 "$DESKTOP_FILE"

info "已安装: $TARGET"
info "启动器: $LAUNCHER"
info "桌面项: $DESKTOP_FILE"
case ":$PATH:" in
  *":$BIN_HOME:"*) info "命令行可用: wechat-data-analysis" ;;
  *) info "提示: 把 $BIN_HOME 加进 PATH 后可直接用 wechat-data-analysis" ;;
esac

# Electron 在 Linux 上依赖「非特权用户命名空间」来开沙箱；内核关掉它时应用会起不来。
# 这里只做提示，不替用户改内核参数，也不默认加 --no-sandbox（那会削弱沙箱）。
if [ -r /proc/sys/user/max_user_namespaces ] && [ "$(cat /proc/sys/user/max_user_namespaces)" = "0" ]; then
  info "警告: 当前内核禁用了非特权用户命名空间，Electron 沙箱无法启动。"
  info "      可用 sysctl user.max_user_namespaces=10000 打开，或自行以 --no-sandbox 运行（不推荐）。"
fi

info "卸载: $SCRIPT_DIR/install.sh --uninstall --prefix $PREFIX"
