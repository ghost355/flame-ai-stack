#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# flame-ai-stack / install_comfy.sh
# Устанавливает: ComfyUI + flame_integration (FlameLoad/FlameSend) +
# ComfyUI-MatAnyone (MPS-патч) + SAM3.1 + рабочие хуки Flame + presets + watcher.
#
# Переменные окружения (все опциональны):
#   COMFY_DIR      — куда ставить ComfyUI          (default: ~/Documents/ComfyUI)
#   COMFYUI_REF    — коммит ComfyUI                (default: 0d8b7510 — проверен)
#   MATANYONE_REF  — коммит ComfyUI-MatAnyone      (default: 87cbce3)
#   SKIP_MODELS=1  — не скачивать веса (sam3.1, matanyone)
#   PYTHON3        — путь к python3.10+ (default: autodetect)
# ---------------------------------------------------------------------------

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

# --- 0. Проверки -----------------------------------------------------------

PY="$(detect_python3)"
log "Python: $PY ($("$PY" --version 2>&1))"
mkdir -p "$COMFY_DIR"

# --- 1. ComfyUI ------------------------------------------------------------

if [[ -d "$COMFY_DIR/.git" ]]; then
    log "ComfyUI уже клонирован: $COMFY_DIR"
else
    log "Клонирую ComfyUI (ref: $COMFYUI_REF)..."
    git clone https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
fi

CURRENT_REF="$(git -C "$COMFY_DIR" rev-parse --short HEAD 2>/dev/null || echo none)"
if [[ "$CURRENT_REF" != "${COMFYUI_REF:0:7}" ]]; then
    log "Переключаю ComfyUI на проверенный коммит $COMFYUI_REF (было: $CURRENT_REF)..."
    git -C "$COMFY_DIR" fetch --depth 1 origin "$COMFYUI_REF" 2>/dev/null \
        || git -C "$COMFY_DIR" fetch origin
    git -C "$COMFY_DIR" checkout -f "$COMFYUI_REF"
fi
ok "ComfyUI: $(git -C "$COMFY_DIR" rev-parse --short HEAD)"

# --- 2. venv + зависимости -------------------------------------------------

if [[ ! -x "$COMFY_DIR/venv/bin/python" ]]; then
    log "Создаю venv (Python 3.12)..."
    "$PY" -m venv "$COMFY_DIR/venv"
fi
VENV_PY="$COMFY_DIR/venv/bin/python"

log "Устанавливаю requirements.txt (может занять 5–15 мин)..."
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null
"$VENV_PY" -m pip install -r "$COMFY_DIR/requirements.txt"

# OpenEXR — иначе FlameSend молча пишет PNG вместо EXR
if ! "$VENV_PY" -c "import OpenEXR" 2>/dev/null; then
    log "Устанавливаю OpenEXR (нужен для настоящего EXR)..."
    "$VENV_PY" -m pip install OpenEXR
fi

# PyAV — нужен для .mov (ProRes 4444 с альфой)
if ! "$VENV_PY" -c "import av" 2>/dev/null; then
    log "Устанавливаю PyAV (нужен для ProRes .mov)..."
    "$VENV_PY" -m pip install av
fi

ok "venv готов. OpenEXR: $("$VENV_PY" -c "import OpenEXR; print(OpenEXR.__version__)" 2>/dev/null || echo нет), av: $("$VENV_PY" -c "import av; print(av.__version__)" 2>/dev/null || echo нет)"

# --- 3. Custom nodes -------------------------------------------------------

# 3.1 flame_integration (FlameLoad / FlameSend) — патченый
NODE_DIR="$COMFY_DIR/custom_nodes/flame_integration"
mkdir -p "$NODE_DIR/web"
if [[ -f "$NODE_DIR/__init__.py" ]] && ! cmp -s "$NODE_DIR/__init__.py" "$PAYLOAD_COMFY/flame_integration/__init__.py"; then
    warn "flame_integration/__init__.py отличается от эталона — перезаписываю."
fi
cp "$PAYLOAD_COMFY/flame_integration/__init__.py" "$NODE_DIR/__init__.py"
ok "flame_integration установлен ($NODE_DIR)"

# 3.2 ComfyUI-MatAnyone
MA_DIR="$COMFY_DIR/custom_nodes/ComfyUI-MatAnyone"
if [[ -d "$MA_DIR/.git" ]]; then
    log "ComfyUI-MatAnyone уже клонирован."
else
    log "Клонирую ComfyUI-MatAnyone (ref: $MATANYONE_REF)..."
    git clone https://github.com/FuouM/ComfyUI-MatAnyone.git "$MA_DIR"
fi
MA_CURRENT="$(git -C "$MA_DIR" rev-parse --short HEAD 2>/dev/null || echo none)"
if [[ "$MA_CURRENT" != "${MATANYONE_REF:0:7}" ]]; then
    log "Переключаю ComfyUI-MatAnyone на $MATANYONE_REF (было: $MA_CURRENT)..."
    git -C "$MA_DIR" fetch --depth 1 origin "$MATANYONE_REF" 2>/dev/null \
        || git -C "$MA_DIR" fetch origin
    git -C "$MA_DIR" checkout -f "$MATANYONE_REF"
fi

# MPS-патч: заменяем mat_anyone.py / mat_anyone2.py + src/ на проверенные
log "Применяю MPS-патч MatAnyone (CPU→MPS детекция устройства)..."
cp "$PAYLOAD_COMFY/matanyone/mat_anyone.py"  "$MA_DIR/mat_anyone.py"
cp "$PAYLOAD_COMFY/matanyone/mat_anyone2.py" "$MA_DIR/mat_anyone2.py"
cp -R "$PAYLOAD_COMFY/matanyone/src/." "$MA_DIR/src/"
ok "ComfyUI-MatAnyone + MPS-патч готов"

# --- 4. Модели -------------------------------------------------------------

MODELS_DIR="$COMFY_DIR/models/checkpoints"
mkdir -p "$MODELS_DIR"
MA_CKPT_DIR="$MA_DIR/checkpoint"
mkdir -p "$MA_CKPT_DIR"

download_if_missing() {
    local url="$1" dest="$2" label="$3"
    if [[ -f "$dest" && -s "$dest" ]]; then
        ok "Модель уже есть: $label ($(du -h "$dest" | cut -f1))"
        return 0
    fi
    if [[ "${SKIP_MODELS:-0}" == "1" ]]; then
        warn "SKIP_MODELS=1 — пропускаю скачивание $label. Файл: $dest"
        return 0
    fi
    log "Скачиваю $label ..."
    curl -L --fail --retry 3 -o "$dest" "$url"
    ok "$label → $dest"
}

download_if_missing "$URL_SAM31" \
    "$MODELS_DIR/sam3.1_multiplex_fp16.safetensors" "SAM3.1 (1.75GB)"

download_if_missing "$URL_MATANYONE2" \
    "$MA_CKPT_DIR/matanyone2.pth" "MatAnyone v2"

download_if_missing "$URL_MATANYONE1" \
    "$MA_CKPT_DIR/matanyone.pth" "MatAnyone v1"

# --- 5. Workflow -----------------------------------------------------------

mkdir -p "$COMFY_DIR/flame_comfy_workflows"
cp "$PAYLOAD_COMFY/workflows/SAM3_MatAnyone2_Matte.json" \
   "$COMFY_DIR/flame_comfy_workflows/"

mkdir -p "$COMFY_DIR/user/default/workflows"
cp "$PAYLOAD_COMFY/workflows/SAM3_MatAnyone2_Matte_UI.json" \
   "$COMFY_DIR/user/default/workflows/"
ok "Workflow скопированы (API + UI форматы)"

# --- 6. Flame-хуки ---------------------------------------------------------

HOOK_DIR="$FLAME_SHARED/comfy_integration"
log "Устанавливаю Flame-хуки в $HOOK_DIR ..."
ensure_dir "$HOOK_DIR"
copy_preserving_owner "$PAYLOAD_COMFY/hook/comfy_integration.py" "$HOOK_DIR/"
copy_preserving_owner "$PAYLOAD_COMFY/hook/comfy_watcher.py"     "$HOOK_DIR/"
ensure_dir "$HOOK_DIR/export_presets"
copy_preserving_owner "$PAYLOAD_COMFY/hook/EXPORT_EXR_COMFYUI.xml"   "$HOOK_DIR/export_presets/"
copy_preserving_owner "$PAYLOAD_COMFY/hook/EXPORT_EXR32_COMFYUI.xml" "$HOOK_DIR/export_presets/"
copy_preserving_owner "$PAYLOAD_COMFY/hook/EXPORT_JPEG_COMFYUI.xml"  "$HOOK_DIR/export_presets/"
copy_preserving_owner "$PAYLOAD_COMFY/hook/EXPORT_PNG_COMFYUI.xml"   "$HOOK_DIR/export_presets/"
copy_preserving_owner "$PAYLOAD_COMFY/hook/EXPORT_PNG16_COMFYUI.xml" "$HOOK_DIR/export_presets/"
ok "Хуки и presets установлены"

# --- 7. Конфиг -------------------------------------------------------------

render_template "$PAYLOAD_COMFY/config/.flame_comfy_config.json.template" \
                "$HOME/.flame_comfy_config.json"
ok "Конфиг: $HOME/.flame_comfy_config.json"

# --- 8. Скрипт запуска -----------------------------------------------------

cp "$PAYLOAD_COMFY/config/start_comfyui.command" "$COMFY_DIR/start_comfyui.command"
make_executable "$COMFY_DIR/start_comfyui.command"
ok "Скрипт запуска: $COMFY_DIR/start_comfyui.command"

echo
ok "Comfy-стек установлен."
echo "  Запуск:        $COMFY_DIR/start_comfyui.command  (или двойной клик в Finder)"
echo "  Проверка нод:  http://127.0.0.1:8000/object_info  → FlameLoad, FlameSend, SAM3_Detect, MatAnyone2"
echo "  Watcher стартует автоматически из хука при запуске Flame (auto_import=true)"