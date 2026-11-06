#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
VERSION=""
TARGET=""
BUILD_DIR=""
DIST_DIR="$ROOT/dist"
NO_BUILD=0
CC_ARG=""
CMAKE_SYSTEM_PROCESSOR=""

usage() {
  echo "Usage: scripts/package-native-release.sh --target linux-x64|linux-arm64|macos-x64|macos-arm64 [--version VERSION] [--build-dir DIR] [--dist-dir DIR] [--no-build]"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --version) shift; VERSION="$1" ;;
    --target) shift; TARGET="$1" ;;
    --build-dir) shift; BUILD_DIR="$1" ;;
    --dist-dir) shift; DIST_DIR="$1" ;;
    --cc) shift; CC_ARG="$1" ;;
    --cmake-system-processor) shift; CMAKE_SYSTEM_PROCESSOR="$1" ;;
    --no-build) NO_BUILD=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

if [ -z "$TARGET" ]; then
  os=$(uname -s | tr '[:upper:]' '[:lower:]')
  machine=$(uname -m)
  case "$os:$machine" in
    linux:x86_64|linux:amd64) TARGET="linux-x64" ;;
    linux:aarch64|linux:arm64) TARGET="linux-arm64" ;;
    darwin:x86_64) TARGET="macos-x64" ;;
    darwin:arm64|darwin:aarch64) TARGET="macos-arm64" ;;
    *) echo "cannot infer target for $os/$machine; pass --target" >&2; exit 2 ;;
  esac
fi

if [ -z "$VERSION" ]; then
  VERSION=$(python3 -c "import pathlib,re; text=pathlib.Path('src/mellowlang/__init__.py').read_text(); m=re.search(r'__version__\s*=\s*[\"'\"']([^\"'\"']+)', text); print(m.group(1) if m else 'dev')" 2>/dev/null || echo dev)
fi

if [ -z "$BUILD_DIR" ]; then
  BUILD_DIR="$ROOT/build/standalone-release-$TARGET"
fi

case "$TARGET" in
  linux-x64|macos-x64)
    : "${CMAKE_SYSTEM_PROCESSOR:=x86_64}"
    ;;
  linux-arm64|macos-arm64)
    : "${CMAKE_SYSTEM_PROCESSOR:=aarch64}"
    ;;
  *)
    echo "unsupported target: $TARGET" >&2
    usage >&2
    exit 2
    ;;
esac

if [ "$NO_BUILD" -eq 0 ]; then
  cmake_args="-S $ROOT/native/standalone -B $BUILD_DIR -DCMAKE_BUILD_TYPE=Release -DCMAKE_SYSTEM_PROCESSOR=$CMAKE_SYSTEM_PROCESSOR"
  if [ -n "$CC_ARG" ]; then
    cmake_args="$cmake_args -DCMAKE_C_COMPILER=$CC_ARG"
  fi
  # shellcheck disable=SC2086
  cmake $cmake_args
  cmake --build "$BUILD_DIR" --parallel 2
fi

if [ ! -f "$BUILD_DIR/mellow" ]; then
  echo "native build output not found: $BUILD_DIR/mellow" >&2
  exit 1
fi

pkg="mellow-$VERSION-$TARGET"
pkg_root="$DIST_DIR/$pkg"
rm -rf "$pkg_root"
mkdir -p "$pkg_root/bin"
mkdir -p "$pkg_root/share/mellow"
cp "$BUILD_DIR/mellow" "$pkg_root/bin/mellow"
if [ -f "$BUILD_DIR/mellowrt" ]; then
  cp "$BUILD_DIR/mellowrt" "$pkg_root/bin/mellowrt"
fi
chmod +x "$pkg_root/bin/mellow" "$pkg_root/bin/mellowrt" 2>/dev/null || true
cp "$ROOT/LICENSE" "$pkg_root/LICENSE"
cp "$ROOT/NOTICE.md" "$pkg_root/NOTICE.md"
cp "$ROOT/README.md" "$pkg_root/README.md"
cp "$ROOT/docs/INSTALL.md" "$pkg_root/INSTALL.md"
cp "$ROOT/scripts/install-native.sh" "$pkg_root/install-native.sh"
cp -R "$ROOT/starter_packages" "$pkg_root/share/mellow/starter_packages"
mkdir -p "$pkg_root/share/mellow/mellow_packages"
cp -R "$ROOT/mellow_packages/registry" "$pkg_root/share/mellow/mellow_packages/registry"
find "$pkg_root/share" -name __pycache__ -type d -prune -exec rm -rf {} +

cat > "$pkg_root/manifest.json" <<EOF
{
  "name": "mellow",
  "version": "$VERSION",
  "target": "$TARGET",
  "runtime": "standalone-c",
  "binaries": ["bin/mellow", "bin/mellowrt"],
  "packages": ["share/mellow/starter_packages", "share/mellow/mellow_packages/registry"]
}
EOF

mkdir -p "$DIST_DIR"
archive="$DIST_DIR/$pkg.tar.gz"
tar -C "$DIST_DIR" -czf "$archive" "$pkg"

if command -v sha256sum >/dev/null 2>&1; then
  (cd "$DIST_DIR" && sha256sum "$pkg.tar.gz" > "$pkg.SHA256SUMS")
else
  hash=$(shasum -a 256 "$archive" | awk '{print $1}')
  printf '%s  %s\n' "$hash" "$pkg.tar.gz" > "$DIST_DIR/$pkg.SHA256SUMS"
fi

echo "release archive: $archive"
echo "sha256: $(cat "$DIST_DIR/$pkg.SHA256SUMS")"
