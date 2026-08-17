#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# flame-ai-stack — универсальный установщик AI-стека для Flame на Apple Silicon
#
# Ставит:
#   1) ComfyUI + SAM3.1 + MatAnyone2 (+ Flame-хуки, presets, watcher)
#   2) Sammie-Roto-2 + round-trip скрипты для Flame
#
# Использование:
#   ./install.sh                    # всё (Comfy + Sammie)
#   ./install.sh --comfy            # только Comfy-стек
#   ./install.sh --sammie           # только Sammie
#   ./install.sh --check            # проверка уже установленного
#   ./install.sh --skip-models      # не скачивать веса моделей
#
# Идемпотентен: повторный запуск безопасен.
# ---------------------------------------------------------------------------

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/scripts/common.sh"

INSTALL_COMFY=0
INSTALL_SAMMIE=0
RUN_CHECK=0
SKIP_MODELS=0

for arg in "$@"; do
    case "$arg" in
        --comfy)       INSTALL_COMFY=1 ;;
        --sammie)      INSTALL_SAMMIE=1 ;;
        --check)       RUN_CHECK=1 ;;
        --skip-models) SKIP_MODELS=1 ;;
        --help|-h)
            grep -E "^\s+# " "$0" | sed 's/^\s*# \{0,1\}//'
            exit 0
            ;;
        *)
            err "Неизвестный аргумент: $arg"
            exit 1
            ;;
    esac
done

# По умолчанию — всё.
if [[ "$INSTALL_COMFY" -eq 0 && "$INSTALL_SAMMIE" -eq 0 && "$RUN_CHECK" -eq 0 ]]; then
    INSTALL_COMFY=1
    INSTALL_SAMMIE=1
fi

check_macos
require_cmd git
require_cmd curl

log "flame-ai-stack installer"
log "  ComfyUI dir : $COMFY_DIR"
log "  Sammie dir  : $SAMMIE_DIR"
log "  Flame hook  : $FLAME_SHARED/comfy_integration"
log ""

if [[ "$RUN_CHECK" -eq 1 ]]; then
    bash "$SCRIPT_DIR/scripts/check.sh"
    exit 0
fi

if [[ "$INSTALL_COMFY" -eq 1 ]]; then
    SKIP_MODELS="$SKIP_MODELS" bash "$SCRIPT_DIR/scripts/install_comfy.sh"
    echo
fi

if [[ "$INSTALL_SAMMIE" -eq 1 ]]; then
    bash "$SCRIPT_DIR/scripts/install_sammie.sh"
    echo
fi

echo
ok "Установка завершена. Следующие шаги:"
echo "  1) Перезапустите Flame (хуки читаются при старте)"
echo "  2) Запустите ComfyUI:  $COMFY_DIR/start_comfyui.command"
echo "  3) Проверьте  http://127.0.0.1:8000  и наличие нод FlameLoad/FlameSend/SAM3_Detect/MatAnyone2"
echo "  4) Для диагностики:  ./install.sh --check"