#!/usr/bin/env bash
# ============================================================
#  MellowLang v2.3.4 — macOS .pkg installer builder
#  Produces:  dist/MellowLang-2.3.4.pkg
#  Requirements: macOS, Python 3.10+, PyInstaller, pkgbuild/productbuild
#  Usage: bash packaging/macos/build_pkg.sh
# ============================================================
set -euo pipefail

VERSION="2.3.4"
BUNDLE_ID="org.mellowlang.mellow"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST="$ROOT/dist"
STAGE="$DIST/_pkg_stage"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()   { echo -e "${GREEN}[OK]${RESET}    $*"; }
die()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "This script must run on macOS."

# ── locate Python ─────────────────────────────────────────────
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" &>/dev/null && \
       "$c" -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>/dev/null; then
        PY="$c"; break
    fi
done
[[ -z "$PY" ]] && die "Python 3.10+ required.  Install: brew install python@3.12"
ok "Python: $($PY --version)"

pushd "$ROOT" > /dev/null
mkdir -p "$DIST"

# ── [1] pip install ───────────────────────────────────────────
info "[1/5] Installing MellowLang..."
$PY -m pip install -e . --quiet

# ── [2] PyInstaller ───────────────────────────────────────────
info "[2/5] Checking PyInstaller..."
$PY -m pip show pyinstaller &>/dev/null || $PY -m pip install pyinstaller --quiet

# ── [3] standalone C runtime ──────────────────────────────────
info "[3/5] Building mellowrt..."
if command -v cmake &>/dev/null; then
    cmake -S native/standalone -B native/standalone/build \
          -DCMAKE_BUILD_TYPE=Release --log-level=WARNING -Wno-dev 2>/dev/null
    cmake --build native/standalone/build --parallel 2>/dev/null
    ok "mellowrt built"
else
    info "cmake not found — skip (brew install cmake to enable)"
fi

# ── [4] PyInstaller both modes ────────────────────────────────
info "[4a/5] PyInstaller onedir..."
$PY -m PyInstaller packaging/pyinstaller/mellowlang_onedir.spec --clean --noconfirm
ok "dist/mellow/mellow"

info "[4b/5] PyInstaller onefile..."
$PY -m PyInstaller packaging/pyinstaller/mellowlang_onefile.spec --clean --noconfirm
ok "dist/mellow_onefile"

# ── [5] Build .pkg ────────────────────────────────────────────
info "[5/5] Building .pkg installer..."
rm -rf "$STAGE"
PAYLOAD="$STAGE/payload/usr/local/bin"
SCRIPTS="$STAGE/scripts"
mkdir -p "$PAYLOAD" "$SCRIPTS"

cp "$DIST/mellow_onefile" "$PAYLOAD/mellow"
chmod +x "$PAYLOAD/mellow"

cat > "$SCRIPTS/postinstall" << 'PEOF'
#!/bin/bash
/usr/local/bin/mellow --version >/dev/null 2>&1 && \
    echo "MellowLang installed successfully." || true
exit 0
PEOF
chmod +x "$SCRIPTS/postinstall"

COMP_PKG="$DIST/_component-$VERSION.pkg"
pkgbuild \
    --root "$STAGE/payload" \
    --scripts "$SCRIPTS" \
    --identifier "$BUNDLE_ID" \
    --version "$VERSION" \
    --install-location "/" \
    "$COMP_PKG"

DIST_XML="$STAGE/dist.xml"
cat > "$DIST_XML" << XMLEOF
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>MellowLang $VERSION</title>
    <organization>org.mellowlang</organization>
    <options customize="never" require-scripts="false"/>
    <pkg-ref id="$BUNDLE_ID"/>
    <choices-outline>
        <line choice="default"><line choice="$BUNDLE_ID"/></line>
    </choices-outline>
    <choice id="default"/>
    <choice id="$BUNDLE_ID" visible="false">
        <pkg-ref id="$BUNDLE_ID"/>
    </choice>
    <pkg-ref id="$BUNDLE_ID" version="$VERSION" onConclusion="none">_component-$VERSION.pkg</pkg-ref>
</installer-gui-script>
XMLEOF

productbuild \
    --distribution "$DIST_XML" \
    --package-path "$DIST" \
    "$DIST/MellowLang-$VERSION.pkg"

rm -f "$COMP_PKG"
rm -rf "$STAGE"
popd > /dev/null

ok "macOS installer: dist/MellowLang-$VERSION.pkg"
echo ""
echo "Install:  sudo installer -pkg dist/MellowLang-$VERSION.pkg -target /"
echo "Or:       double-click dist/MellowLang-$VERSION.pkg in Finder"
echo ""
echo "Test:     mellow --version"
