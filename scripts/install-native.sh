#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PREFIX="${PREFIX:-$HOME/.local}"
BUILD_DIR="$ROOT/build/standalone-release"
NO_BUILD=0
ADD_PATH=0
UNINSTALL=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix)
      shift
      PREFIX="$1"
      ;;
    --no-build)
      NO_BUILD=1
      ;;
    --add-path)
      ADD_PATH=1
      ;;
    --uninstall)
      UNINSTALL=1
      ;;
    -h|--help)
      echo "Usage: scripts/install-native.sh [--prefix PREFIX] [--no-build] [--add-path] [--uninstall]"
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      exit 2
      ;;
  esac
  shift
done

BIN_DIR="$PREFIX/bin"

add_path_line() {
  profile="$1"
  line='export PATH="$HOME/.local/bin:$PATH"'
  [ "$PREFIX" = "$HOME/.local" ] || line="export PATH=\"$BIN_DIR:\$PATH\""
  touch "$profile"
  if ! grep -F "$BIN_DIR" "$profile" >/dev/null 2>&1; then
    printf '\n# Mellow native CLI\n%s\n' "$line" >> "$profile"
  fi
}

if [ "$UNINSTALL" -eq 1 ]; then
  rm -f "$BIN_DIR/mellow" "$BIN_DIR/mellowrt"
  echo "Mellow native install removed from $BIN_DIR"
  exit 0
fi

if [ "$NO_BUILD" -eq 0 ]; then
  cmake -S "$ROOT/native/standalone" -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE=Release
  cmake --build "$BUILD_DIR" --parallel
fi

if [ ! -f "$BUILD_DIR/mellow" ]; then
  echo "native build output not found: $BUILD_DIR/mellow" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
cp "$BUILD_DIR/mellow" "$BIN_DIR/mellow"
if [ -f "$BUILD_DIR/mellowrt" ]; then
  cp "$BUILD_DIR/mellowrt" "$BIN_DIR/mellowrt"
fi
chmod +x "$BIN_DIR/mellow" "$BIN_DIR/mellowrt" 2>/dev/null || true

if [ "$ADD_PATH" -eq 1 ]; then
  shell_name=$(basename "${SHELL:-sh}")
  case "$shell_name" in
    zsh) add_path_line "$HOME/.zshrc" ;;
    bash) add_path_line "$HOME/.bashrc" ;;
    *) add_path_line "$HOME/.profile" ;;
  esac
fi

echo "Mellow native installed:"
echo "  $BIN_DIR/mellow"
echo
"$BIN_DIR/mellow" doctor
echo
echo "Next:"
echo "  export PATH=\"$BIN_DIR:\$PATH\""
echo "  mellow doctor"
