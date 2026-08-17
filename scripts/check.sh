#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# flame-ai-stack / check.sh
# Диагностика установки: проверяет Comfy-стек и/или Sammie.
# Ничего не меняет. Выход: 0 = всё ок, 1 = есть проблемы.
#
#   ./install.sh --check
#   bash scripts/check.sh
# ---------------------------------------------------------------------------

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

FAILS=0
WARNS=0

report() { # report PASS|WARN|FAIL msg
    case "$1" in
        PASS) ok   "$2" ;;
        WARN) warn "$2"; WARNS=$((WARNS+1)) ;;
        FAIL) err  "$2"; FAILS=$((FAILS+1)) ;;
    esac
}

check_macos
log "Проверка окружения: $(uname -m), macOS $(sw_vers -ProductVersion)"

# --- Python ----------------------------------------------------------------
if PY="$(detect_python3)"; then
    report PASS "Python: $PY ($("$PY" --version 2>&1))"
else
    report FAIL "Python 3.10+ не найден (нужен python3.12)"
    PY=""
fi

# --- Comfy-стек ------------------------------------------------------------
log ""
log "── Comfy-стек ─────────────────────────────────────────"

if [[ -d "$COMFY_DIR/.git" ]]; then
    report PASS "ComfyUI клонирован ($(git -C "$COMFY_DIR" rev-parse --short HEAD 2>/dev/null))"
else
    report FAIL "ComfyUI отсутствует: $COMFY_DIR"
fi

if [[ -x "$COMFY_DIR/venv/bin/python" ]]; then
    report PASS "venv есть"
    TORCH="$("$COMFY_DIR/venv/bin/python" -c "import torch; print(torch.__version__)" 2>/dev/null || echo 'не установлен')"
    MPS="$("$COMFY_DIR/venv/bin/python" -c "import torch; print(torch.backends.mps.is_available())" 2>/dev/null || echo '?')"
    if [[ "$MPS" == "True" ]]; then
        report PASS "PyTorch $TORCH (MPS: True)"
    else
        report WARN "PyTorch $TORCH (MPS: $MPS — ожидается True)"
    fi
    "$COMFY_DIR/venv/bin/python" -c "import OpenEXR" 2>/dev/null \
        && report PASS "OpenEXR установлен" \
        || report WARN "OpenEXR НЕ установлен (EXR будет падать в PNG)"
    "$COMFY_DIR/venv/bin/python" -c "import av" 2>/dev/null \
        && report PASS "PyAV установлен" \
        || report WARN "PyAV НЕ установлен (.mov/ProRes не будет)"
else
    report FAIL "venv отсутствует: $COMFY_DIR/venv"
fi

# Custom nodes
for n in flame_integration ComfyUI-MatAnyone; do
    [[ -d "$COMFY_DIR/custom_nodes/$n" ]] \
        && report PASS "Custom node: $n" \
        || report FAIL "Custom node отсутствует: $n"
done

# MPS-патч
if [[ -f "$COMFY_DIR/custom_nodes/ComfyUI-MatAnyone/mat_anyone2.py" ]] \
   && grep -q "mps" "$COMFY_DIR/custom_nodes/ComfyUI-MatAnyone/mat_anyone2.py"; then
    report PASS "MPS-патч MatAnyone применён"
else
    report FAIL "MPS-патч MatAnyone НЕ применён (mat_anyone2.py без mps)"
fi

# Модели
[[ -s "$COMFY_DIR/models/checkpoints/sam3.1_multiplex_fp16.safetensors" ]] \
    && report PASS "SAM3.1 веса есть ($(du -h "$COMFY_DIR/models/checkpoints/sam3.1_multiplex_fp16.safetensors" | cut -f1))" \
    || report WARN "SAM3.1 веса отсутствуют (нужен ./install.sh без --skip-models)"

for m in matanyone.pth matanyone2.pth; do
    [[ -s "$COMFY_DIR/custom_nodes/ComfyUI-MatAnyone/checkpoint/$m" ]] \
        && report PASS "Модель: $m" \
        || report WARN "Модель отсутствует: $m"
done

# Workflow
[[ -f "$COMFY_DIR/flame_comfy_workflows/SAM3_MatAnyone2_Matte.json" ]] \
    && report PASS "Workflow (API): SAM3_MatAnyone2_Matte.json" \
    || report FAIL "Workflow API отсутствует"

[[ -f "$COMFY_DIR/user/default/workflows/SAM3_MatAnyone2_Matte_UI.json" ]] \
    && report PASS "Workflow (UI): SAM3_MatAnyone2_Matte_UI.json" \
    || report WARN "Workflow UI отсутствует (просмотр в ComfyUI невозможен)"

# Хуки Flame
HOOK_DIR="$FLAME_SHARED/comfy_integration"
for f in comfy_integration.py comfy_watcher.py; do
    [[ -f "$HOOK_DIR/$f" ]] \
        && report PASS "Хук: $f" \
        || report FAIL "Хук отсутствует: $HOOK_DIR/$f"
done
for p in EXPORT_PNG_COMFYUI EXPORT_PNG16_COMFYUI EXPORT_EXR_COMFYUI EXPORT_EXR32_COMFYUI EXPORT_JPEG_COMFYUI; do
    [[ -f "$HOOK_DIR/export_presets/$p.xml" ]] \
        && report PASS "Пресет: $p.xml" \
        || report FAIL "Пресет отсутствует: $p.xml"
done

# Конфиг
if [[ -f "$HOME/.flame_comfy_config.json" ]]; then
    report PASS "Конфиг: $HOME/.flame_comfy_config.json"
else
    report FAIL "Конфиг отсутствует: $HOME/.flame_comfy_config.json"
fi

# Скрипт запуска
[[ -x "$COMFY_DIR/start_comfyui.command" ]] \
    && report PASS "start_comfyui.command (исполняемый)" \
    || report WARN "start_comfyui.command отсутствует/не исполняемый"

# Живой сервер
if curl -s --max-time 2 "http://127.0.0.1:8000/object_info" >/dev/null 2>&1; then
    NODES="$(curl -s --max-time 5 "http://127.0.0.1:8000/object_info" | python3 -c "import json,sys; d=json.load(sys.stdin); print(' '.join(n for n in ['FlameLoad','FlameSend','SAM3_Detect','MatAnyone2'] if n in d))" 2>/dev/null)"
    report PASS "ComfyUI на :8000 отвечает. Ноды: $NODES"
else
    report WARN "ComfyUI не запущен на :8000 (запустите start_comfyui.command)"
fi

# --- Sammie ----------------------------------------------------------------
log ""
log "── Sammie-Roto-2 ──────────────────────────────────────"

if [[ -f "$SAMMIE_DIR/sammie_main.py" ]]; then
    report PASS "Sammie установлен: $SAMMIE_DIR"
else
    report FAIL "Sammie отсутствует: $SAMMIE_DIR"
fi

if [[ -x "$SAMMIE_DIR/venv/bin/python" ]]; then
    TORCH="$("$SAMMIE_DIR/venv/bin/python" -c "import torch; print(torch.__version__)" 2>/dev/null || echo 'не установлен')"
    MPS="$("$SAMMIE_DIR/venv/bin/python" -c "import torch; print(torch.backends.mps.is_available())" 2>/dev/null || echo '?')"
    if [[ "$MPS" == "True" ]]; then
        report PASS "venv Sammie: PyTorch $TORCH (MPS: True)"
    else
        report WARN "venv Sammie: PyTorch $TORCH (MPS: $MPS)"
    fi
else
    report FAIL "venv Sammie отсутствует"
fi

for f in sammieroto_roundtrip.py sammie_roto_ui.py pyflame_lib_sammie_roto.py EXPORT_JPEG_SAMMIE.xml; do
    [[ -f "$FLAME_SHARED/$f" ]] \
        && report PASS "Round-trip: $f" \
        || report FAIL "Round-trip отсутствует: $f"
done

[[ -f "$FLAME_SHARED/config/sammie_config.json" ]] \
    && report PASS "sammie_config.json есть" \
    || report FAIL "sammie_config.json отсутствует"

[[ -x "$SAMMIE_DIR/run_sammie.command" ]] \
    && report PASS "run_sammie.command (исполняемый)" \
    || report WARN "run_sammie.command отсутствует/не исполняемый"

# Модели Sammie (скачиваются самим приложением при первом запуске)
CKPT="$SAMMIE_DIR/checkpoints"
if [[ -d "$CKPT" ]] && [[ "$(ls -A "$CKPT" 2>/dev/null)" ]]; then
    report PASS "Модели Sammie есть ($(du -sh "$CKPT" 2>/dev/null | cut -f1))"
else
    report WARN "Модели Sammie ещё не скачаны — появятся после первого запуска (~22GB)"
fi

# --- Итог ------------------------------------------------------------------
log ""
if [[ "$FAILS" -eq 0 && "$WARNS" -eq 0 ]]; then
    ok "Всё на месте. Стек готов к работе."
elif [[ "$FAILS" -eq 0 ]]; then
    warn "Проблем нет, но есть предупреждения ($WARNS)."
else
    err "Найдено проблем: $FAILS (предупреждений: $WARNS)."
fi
exit $(( FAILS > 0 ? 1 : 0 ))