#!/usr/bin/env bash
# ============================================================
#  MellowLang v2.3.4 — Linux / macOS installer
#  Usage:
#    chmod +x install.sh && ./install.sh
#    ./install.sh --prefix /opt/mellow   # custom install dir
#    ./install.sh --dev                  # also install dev deps
#    ./install.sh --uninstall            # remove MellowLang
# ============================================================
set -euo pipefail

VERSION="2.3.4"
APPNAME="MellowLang"
DEFAULT_PREFIX="$HOME/.local"
INSTALL_PREFIX="$DEFAULT_PREFIX"
DEV_MODE=0
UNINSTALL=0

# ── colour helpers ──────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'
info()  { echo -e "${CYAN}[INFO]${RESET}  $*"; }
ok()    { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error() { echo -e "${RED}[ERROR]${RESET} $*" >&2; }
die()   { error "$*"; exit 1; }

# ── argument parsing ────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)    INSTALL_PREFIX="$2"; shift 2 ;;
    --prefix=*)  INSTALL_PREFIX="${1#*=}"; shift ;;
    --dev)       DEV_MODE=1; shift ;;
    --uninstall) UNINSTALL=1; shift ;;
    -h|--help)
      echo "Usage: $0 [--prefix DIR] [--dev] [--uninstall]"
      exit 0 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

# ── detect OS ───────────────────────────────────────────────
OS="linux"
[[ "$(uname -s)" == "Darwin" ]] && OS="macos"

echo -e "${BOLD}"
echo "  ╔══════════════════════════════════════╗"
echo "  ║  $APPNAME v$VERSION Installer         ║"
echo "  ║  Platform: $OS                        "
echo "  ╚══════════════════════════════════════╝"
echo -e "${RESET}"

# ── uninstall ───────────────────────────────────────────────
if [[ $UNINSTALL -eq 1 ]]; then
  info "Uninstalling MellowLang..."
  pip3 uninstall mellowlang -y 2>/dev/null || true
  rm -f "$INSTALL_PREFIX/bin/mellow"
  rm -f "$HOME/.local/bin/mellow"
  rm -f "/usr/local/bin/mellow"
  ok "MellowLang removed. You may also delete this directory."
  exit 0
fi

# ── locate Python ───────────────────────────────────────────
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" &>/dev/null; then
    _ver=$("$candidate" -c "import sys; print(sys.version_info[:2])")
    # accept 3.10+
    if "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done

if [[ -z "$PY" ]]; then
  error "Python 3.10 or newer is required but not found."
  if [[ "$OS" == "macos" ]]; then
    echo "  Install via Homebrew:  brew install python@3.12"
  else
    echo "  Ubuntu/Debian:  sudo apt install python3.12 python3-pip"
    echo "  Fedora:         sudo dnf install python3.12"
  fi
  die "Please install Python 3.10+ and re-run this installer."
fi

PY_VER=$("$PY" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
ok "Found Python $PY_VER at $(command -v "$PY")"

# ── locate pip ──────────────────────────────────────────────
PIP="$PY -m pip"
$PIP --version &>/dev/null || die "pip not found. Install python3-pip and retry."

# ── locate project root ─────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR"
[[ -f "$ROOT/pyproject.toml" ]] || die "pyproject.toml not found in $ROOT — run this script from the MellowLang directory."

# ── install Python package ──────────────────────────────────
info "Installing MellowLang Python package..."
if [[ $DEV_MODE -eq 1 ]]; then
  $PIP install -e "$ROOT[dev]" --quiet
  ok "Installed in editable/dev mode"
else
  $PIP install "$ROOT" --quiet
  ok "Installed MellowLang $VERSION"
fi

# ── build standalone C runtime ──────────────────────────────
if command -v cmake &>/dev/null && command -v cc &>/dev/null; then
  info "Building standalone C runtime (mellowrt)..."
  CMAKE_BUILD="$ROOT/native/standalone/build"
  cmake -S "$ROOT/native/standalone" -B "$CMAKE_BUILD" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL_PREFIX" \
        --log-level=WARNING -Wno-dev 2>/dev/null
  cmake --build "$CMAKE_BUILD" --parallel 2>/dev/null
  # Install binary to prefix/bin
  mkdir -p "$INSTALL_PREFIX/bin"
  cp "$CMAKE_BUILD/mellowrt" "$INSTALL_PREFIX/bin/mellowrt"
  chmod +x "$INSTALL_PREFIX/bin/mellowrt"
  ok "mellowrt installed to $INSTALL_PREFIX/bin/mellowrt"
else
  warn "cmake or C compiler not found — skipping standalone C runtime build."
  warn "Scripts will run via the Python VM (fully functional)."
  if [[ "$OS" == "macos" ]]; then
    echo "  To enable: brew install cmake gcc"
  else
    echo "  To enable: sudo apt install cmake gcc"
  fi
fi

# ── create mellow wrapper in prefix/bin ─────────────────────
MELLOW_BIN="$(command -v mellow 2>/dev/null || true)"
if [[ -z "$MELLOW_BIN" ]]; then
  # pip may have installed to ~/.local/bin — check if it's in PATH
  LOCAL_BIN="$HOME/.local/bin"
  if [[ -f "$LOCAL_BIN/mellow" ]]; then
    MELLOW_BIN="$LOCAL_BIN/mellow"
  fi
fi

# ── PATH check ──────────────────────────────────────────────
SHELL_RC=""
case "$SHELL" in
  */zsh)  SHELL_RC="$HOME/.zshrc" ;;
  */fish) SHELL_RC="$HOME/.config/fish/config.fish" ;;
  *)      SHELL_RC="$HOME/.bashrc" ;;
esac

LOCAL_BIN="$HOME/.local/bin"
if [[ ":$PATH:" != *":$LOCAL_BIN:"* ]]; then
  warn "$LOCAL_BIN is not in PATH."
  echo ""
  echo "  Add this line to $SHELL_RC:"
  if [[ "$SHELL" == */fish ]]; then
    echo "    fish_add_path $LOCAL_BIN"
  else
    echo "    export PATH=\"\$PATH:$LOCAL_BIN\""
  fi
  echo ""
  echo "  Then restart your terminal or run:"
  echo "    source $SHELL_RC"
  echo ""
  # Auto-append if interactive
  if [[ -t 0 ]]; then
    read -rp "  Add to $SHELL_RC automatically? [y/N] " _ans
    if [[ "$_ans" =~ ^[Yy]$ ]]; then
      echo "" >> "$SHELL_RC"
      echo "# MellowLang $VERSION" >> "$SHELL_RC"
      if [[ "$SHELL" == */fish ]]; then
        echo "fish_add_path $LOCAL_BIN" >> "$SHELL_RC"
      else
        echo "export PATH=\"\$PATH:$LOCAL_BIN\"" >> "$SHELL_RC"
      fi
      ok "PATH updated in $SHELL_RC"
    fi
  fi
fi

# ── verify ──────────────────────────────────────────────────
echo ""
echo -e "${BOLD}Verifying installation...${RESET}"
if command -v mellow &>/dev/null || [[ -f "$LOCAL_BIN/mellow" ]]; then
  _mellow="${MELLOW_BIN:-$LOCAL_BIN/mellow}"
  _ver=$("$_mellow" --version 2>/dev/null || echo "?")
  ok "mellow --version → $_ver"
  ok "mellow doctor:"
  "$_mellow" doctor 2>/dev/null || true
else
  warn "mellow not found in PATH yet — restart terminal after updating PATH."
fi

# ── summary ─────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}══════════════════════════════════════════${RESET}"
echo -e "${BOLD}  $APPNAME v$VERSION installed!${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════${RESET}"
echo ""
echo "  Quick start:"
echo "    mellow run examples/hello.mellow"
echo "    mellow standalone compile examples/hello.mellow -o hello.mvi"
echo "    mellowrt hello.mvi"
echo ""
echo "  Docs: docs/  |  Examples: examples/"
echo ""
