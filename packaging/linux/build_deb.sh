#!/usr/bin/env bash
# ============================================================
#  MellowLang v2.3.4 — Linux .deb package builder
#  Produces:  dist/mellowlang_2.3.4_amd64.deb  (or arm64)
#  Requirements: dpkg-deb, Python 3.10+, PyInstaller
#  Usage: bash packaging/linux/build_deb.sh
# ============================================================
set -euo pipefail

VERSION="2.3.4"
MAINTAINER="Seashyne <hello@mellowlang.org>"
DESCRIPTION="MellowLang Sandbox Scripting Engine (game/AI focused)"
ARCH="$(dpkg --print-architecture 2>/dev/null || uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/')"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DIST="$ROOT/dist"
DEBROOT="$DIST/_deb_$VERSION"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info() { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()   { echo -e "${GREEN}[OK]${RESET}    $*"; }
die()  { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }

command -v dpkg-deb &>/dev/null || die "dpkg-deb not found (Debian/Ubuntu only). Use install.sh on other distros."

# ── locate Python ─────────────────────────────────────────────
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$c" &>/dev/null && \
       "$c" -c "import sys; sys.exit(0 if sys.version_info>=(3,10) else 1)" 2>/dev/null; then
        PY="$c"; break
    fi
done
[[ -z "$PY" ]] && die "Python 3.10+ required. sudo apt install python3.12 python3-pip"
ok "Python: $($PY --version)"

pushd "$ROOT" > /dev/null
mkdir -p "$DIST"

# ── [1] pip install ───────────────────────────────────────────
info "[1/5] Installing package..."
$PY -m pip install -e . --quiet

# ── [2] PyInstaller ───────────────────────────────────────────
info "[2/5] Checking PyInstaller..."
$PY -m pip show pyinstaller &>/dev/null || $PY -m pip install pyinstaller --quiet

# ── [3] mellowrt ─────────────────────────────────────────────
info "[3/5] Building mellowrt..."
if command -v cmake &>/dev/null && command -v cc &>/dev/null; then
    cmake -S native/standalone -B native/standalone/build \
          -DCMAKE_BUILD_TYPE=Release --log-level=WARNING -Wno-dev 2>/dev/null
    cmake --build native/standalone/build --parallel 2>/dev/null
    ok "mellowrt built"
else
    info "cmake/cc not found — skip  (sudo apt install cmake gcc)"
fi

# ── [4] PyInstaller both modes ────────────────────────────────
info "[4a/5] PyInstaller onedir..."
$PY -m PyInstaller packaging/pyinstaller/mellowlang_onedir.spec --clean --noconfirm
ok "dist/mellow/"

info "[4b/5] PyInstaller onefile..."
$PY -m PyInstaller packaging/pyinstaller/mellowlang_onefile.spec --clean --noconfirm
ok "dist/mellow_onefile"

# ── [5] Build .deb ────────────────────────────────────────────
info "[5/5] Building .deb package..."
rm -rf "$DEBROOT"

# Install directories
BINDIR="$DEBROOT/usr/bin"
SHAREDIR="$DEBROOT/usr/share/mellowlang"
DOCDIR="$DEBROOT/usr/share/doc/mellowlang"
DESKTOPDIR="$DEBROOT/usr/share/applications"
MIMEDIR="$DEBROOT/usr/share/mime/packages"

mkdir -p "$BINDIR" "$SHAREDIR" "$DOCDIR" "$DESKTOPDIR" "$MIMEDIR"
mkdir -p "$DEBROOT/DEBIAN"

# Copy onefile binary as primary CLI
cp "$DIST/mellow_onefile" "$BINDIR/mellow"
chmod 755 "$BINDIR/mellow"

# Copy mellowrt if built
if [[ -f "$ROOT/native/standalone/build/mellowrt" ]]; then
    cp "$ROOT/native/standalone/build/mellowrt" "$BINDIR/mellowrt"
    chmod 755 "$BINDIR/mellowrt"
fi

# Copy examples and docs
cp -r "$ROOT/examples" "$SHAREDIR/examples" 2>/dev/null || true
cp "$ROOT/docs/INSTALL.md" "$DOCDIR/README.md" 2>/dev/null || true
cp "$ROOT/LICENSE" "$DOCDIR/copyright" 2>/dev/null || true

# .desktop file
cat > "$DESKTOPDIR/mellowlang.desktop" << 'DEOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=MellowLang
Comment=MellowLang Sandbox Scripting Engine
Exec=mellow run %f
Icon=mellowlang
Terminal=true
MimeType=text/x-mellow;
Categories=Development;
DEOF

# MIME type for .mellow files
cat > "$MIMEDIR/mellowlang.xml" << 'MEOF'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="text/x-mellow">
    <comment>MellowLang Script</comment>
    <glob pattern="*.mellow"/>
    <glob pattern="*.mel"/>
  </mime-type>
</mime-info>
MEOF

# DEBIAN/control
INSTALLED_SIZE=$(du -sk "$DEBROOT" | cut -f1)
cat > "$DEBROOT/DEBIAN/control" << CTRLEOF
Package: mellowlang
Version: $VERSION
Architecture: $ARCH
Maintainer: $MAINTAINER
Installed-Size: $INSTALLED_SIZE
Depends: libc6 (>= 2.31), libm6 | libc6
Recommends: python3 (>= 3.10), cmake, gcc
Description: $DESCRIPTION
 MellowLang is a sandbox scripting language focused on games and AI behavior.
 Features deterministic execution, record/replay, safe sandboxing, and a
 Python-free standalone runtime (mellowrt).
 .
 v$VERSION adds complete standalone opcode coverage: MOD, POW, BOOL ops,
 GETITEM, LEN, function calls, and a full syscall table (print/len/range/math).
Homepage: https://mellowlang.org
CTRLEOF

# DEBIAN/postinst — update mime database
cat > "$DEBROOT/DEBIAN/postinst" << 'PEOF'
#!/bin/bash
update-mime-database /usr/share/mime 2>/dev/null || true
update-desktop-database 2>/dev/null || true
exit 0
PEOF
chmod 755 "$DEBROOT/DEBIAN/postinst"

DEB_NAME="mellowlang_${VERSION}_${ARCH}.deb"
dpkg-deb --build --root-owner-group "$DEBROOT" "$DIST/$DEB_NAME"
rm -rf "$DEBROOT"

popd > /dev/null
ok "Debian package: dist/$DEB_NAME"
echo ""
echo "Install:  sudo dpkg -i dist/$DEB_NAME"
echo "Remove:   sudo dpkg -r mellowlang"
echo "Test:     mellow --version"
