#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# flame-ai-stack / common.sh
# Shared helpers: logging, prerequisites, python detection.
# Sourced by install.sh, scripts/install_comfy.sh, scripts/install_sammie.sh,
# scripts/check.sh
# ---------------------------------------------------------------------------

set -euo pipefail

# --- ANSI colors -----------------------------------------------------------
if [[ -t 1 ]]; then
    C_RED=$'\033[31m';  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'
    C_BLUE=$'\033[34m'; C_BOLD=$'\033[1m';   C_RESET=$'\033[0m'
else
    C_RED=""; C_GREEN=""; C_YELLOW=""; C_BLUE=""; C_BOLD=""; C_RESET=""
fi

log()  { printf '%s[INFO]%s %s\n'  "$C_BLUE"   "$C_RESET" "$*"; }
ok()   { printf '%s[ OK ]%s %s\n'  "$C_GREEN"  "$C_RESET" "$*"; }
warn() { printf '%s[WARN]%s %s\n'  "$C_YELLOW" "$C_RESET" "$*"; }
err()  { printf '%s[FAIL]%s %s\n'  "$C_RED"    "$C_RESET" "$*" >&2; }

die()  { err "$*"; exit 1; }

# --- basic prerequisites ---------------------------------------------------

require_cmd() {
    local bin="$1"
    if ! command -v "$bin" >/dev/null 2>&1; then
        die "Отсутствует '$bin'. Установите и повторите."
    fi
}

check_macos() {
    [[ "$(uname -s)" == "Darwin" ]] || die "Поддерживается только macOS."
    [[ "$(uname -m)" == "arm64" ]]  || die "Требуется Apple Silicon (M-серия)."
}

# Detect a usable Python 3.10+ (3.12 preferred). Prints the path or exits.
detect_python3() {
    local candidates=(
        "${PYTHON3:-}"
        /opt/homebrew/bin/python3.12
        /usr/local/bin/python3.12
        "$(command -v python3.12 2>/dev/null || true)"
        /opt/homebrew/bin/python3
        "$(command -v python3 2>/dev/null || true)"
    )
    local py major minor
    for py in "${candidates[@]}"; do
        [[ -n "$py" ]] || continue
        [[ -x "$py" ]] || continue
        major="$("$py" -c 'import sys; print(sys.version_info.major)' 2>/dev/null || echo 0)"
        minor="$("$py" -c 'import sys; print(sys.version_info.minor)' 2>/dev/null || echo 0)"
        if [[ "$major" -eq 3 && "$minor" -ge 10 ]]; then
            printf '%s\n' "$py"
            return 0
        fi
    done
    cat >&2 <<'EOF'
[FAIL] Не найден Python 3.10+ (рекомендуется 3.12).
       Установите через Homebrew:  brew install python@3.12
EOF
    return 1
}

# --- shared constants ------------------------------------------------------

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PAYLOAD_COMFY="$REPO_ROOT/payload/comfy"
PAYLOAD_SAMMIE="$REPO_ROOT/payload/sammie"

COMFY_DIR="${COMFY_DIR:-$HOME/Documents/ComfyUI}"
SAMMIE_DIR="${SAMMIE_DIR:-$HOME/Documents/Sammie-Roto-2}"
FLAME_SHARED="${FLAME_SHARED:-/opt/Autodesk/shared/python}"

# Known-good refs (verified on the author machine).
COMFYUI_REF="${COMFYUI_REF:-0d8b7510}"          # v0.25.0-31-g0d8b7510
MATANYONE_REF="${MATANYONE_REF:-87cbce3}"       # "publish from cli test"
SAMMIE_TAG="${SAMMIE_TAG:-v2.3.3}"

# Model URLs (verified 2026-08-18; upstream princeton-vl/FuouM dead: 401/404)
URL_MATANYONE1="https://github.com/pq-yang/MatAnyone/releases/download/v1.0.0/matanyone.pth"
URL_MATANYONE2="https://github.com/pq-yang/MatAnyone2/releases/download/v1.0.0/matanyone2.pth"
URL_SAM31="https://huggingface.co/Comfy-Org/sam3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors"
URL_SAMMIE_ZIP="https://github.com/Zarxrax/Sammie-Roto-2/releases/download/v2.3.3/Sammie-Roto-2.3.3.zip"

# --- helpers ---------------------------------------------------------------

# ensure_dir DIR — mkdir -p with sudo fallback for root-owned parents
ensure_dir() {
    local d="$1"
    if [[ -d "$d" ]]; then
        return 0
    fi
    if ! mkdir -p "$d" 2>/dev/null; then
        log "Создаю папку $d (sudo)..."
        sudo mkdir -p "$d"
    fi
}

# copy_preserving_owner SRC DESTDIR
# Tries plain cp; falls back to sudo when the destination is not writable
# (e.g. /opt/Autodesk/shared/python is root-owned on some machines).
# Creates DESTDIR (with sudo if needed) when it does not exist.
copy_preserving_owner() {
    local src="$1" dest="$2"
    local dest_parent
    if [[ "$dest" == */ ]]; then
        dest_parent="${dest%/}"
    else
        dest_parent="$(dirname "$dest")"
    fi
    ensure_dir "$dest_parent"
    if cp -R "$src" "$dest" 2>/dev/null; then
        return 0
    fi
    log "Нужны права sudo для записи в $dest"
    sudo cp -R "$src" "$dest"
}

# make_executable FILE — chmod +x (with sudo fallback for root-owned paths)
make_executable() {
    local f="$1"
    if chmod +x "$f" 2>/dev/null; then
        return 0
    fi
    sudo chmod +x "$f"
}

# render_template TEMPLATE OUT  — replaces __HOME__ with $HOME
render_template() {
    sed "s|__HOME__|$HOME|g" "$1" > "$2"
}