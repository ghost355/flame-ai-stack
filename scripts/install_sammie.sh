#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# flame-ai-stack / install_sammie.sh
# Устанавливает Sammie-Roto-2 (SAM2 + MatAnyone + VideoMaMa + MiniMax-Remover)
# и round-trip скрипты для Flame.
#
# Модели (~22GB) НЕ скачиваются установщиком — Sammie качает их сам
# при первом запуске через свой интерфейс.
#
# Переменные окружения (опциональны):
#   SAMMIE_DIR   — куда ставить Sammie     (default: ~/Documents/Sammie-Roto-2)
#   SAMMIE_TAG   — версия релиза           (default: v2.3.3)
#   PYTHON3      — путь к python3.10+      (default: autodetect)
# ---------------------------------------------------------------------------

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/common.sh"

PY="$(detect_python3)"
log "Python: $PY ($("$PY" --version 2>&1))"

# --- 1. Загрузка и распаковка ----------------------------------------------

mkdir -p "$SAMMIE_DIR"

if [[ -f "$SAMMIE_DIR/sammie_main.py" ]]; then
    log "Sammie уже установлен: $SAMMIE_DIR"
else
    TMP_ZIP="$(mktemp -t sammie).zip"
    TMP_DIR="$(mktemp -d -t sammie)"
    log "Скачиваю Sammie-Roto-2 $SAMMIE_TAG с GitHub releases..."
    curl -L --fail --retry 3 -o "$TMP_ZIP" "$URL_SAMMIE_ZIP"
    log "Распаковываю..."
    unzip -q "$TMP_ZIP" -d "$TMP_DIR"
    INNER="$(find "$TMP_DIR" -maxdepth 2 -name "run_sammie.command" -print -quit | xargs dirname)"
    if [[ -z "$INNER" || ! -d "$INNER" ]]; then
        die "Не удалось найти содержимое архива Sammie."
    fi
    log "Копирую содержимое в $SAMMIE_DIR ..."
    cp -R "$INNER/." "$SAMMIE_DIR/"
    rm -rf "$TMP_ZIP" "$TMP_DIR"
    ok "Sammie $SAMMIE_TAG распакован в $SAMMIE_DIR"
fi

# --- 2. venv + зависимости -------------------------------------------------

if [[ ! -x "$SAMMIE_DIR/venv/bin/python" ]]; then
    log "Создаю venv для Sammie..."
    "$PY" -m venv "$SAMMIE_DIR/venv"
fi
VENV_PY="$SAMMIE_DIR/venv/bin/python"

log "Устанавливаю PyTorch (MPS) + зависимости (может занять 10–20 мин)..."
"$VENV_PY" -m pip install --upgrade pip wheel >/dev/null

# PyTorch с поддержкой MPS (стандартный pip-релиз на macOS уже включает MPS)
if ! "$VENV_PY" -c "import torch; assert torch.backends.mps.is_available()" 2>/dev/null; then
    "$VENV_PY" -m pip install "torch==2.11.0" torchvision
fi

if [[ -f "$SAMMIE_DIR/requirements.txt" ]]; then
    "$VENV_PY" -m pip install -r "$SAMMIE_DIR/requirements.txt"
fi

ok "venv Sammie готов. Torch: $("$VENV_PY" -c "import torch; print(torch.__version__, '| MPS:', torch.backends.mps.is_available())" 2>/dev/null || echo 'не установлен')"

# --- 3. Round-trip скрипты -------------------------------------------------

log "Устанавливаю round-trip скрипты в $FLAME_SHARED ..."
copy_preserving_owner "$PAYLOAD_SAMMIE/flame_scripts/sammieroto_roundtrip.py" "$FLAME_SHARED/"
copy_preserving_owner "$PAYLOAD_SAMMIE/flame_scripts/sammie_roto_ui.py"       "$FLAME_SHARED/"
copy_preserving_owner "$PAYLOAD_SAMMIE/flame_scripts/pyflame_lib_sammie_roto.py" "$FLAME_SHARED/"
copy_preserving_owner "$PAYLOAD_SAMMIE/flame_scripts/EXPORT_JPEG_SAMMIE.xml"  "$FLAME_SHARED/"

mkdir -p "$FLAME_SHARED/config"
render_template "$PAYLOAD_SAMMIE/flame_scripts/config/sammie_config.json.template" \
                "$FLAME_SHARED/config/sammie_config.json"
ok "Round-trip скрипты и конфиг установлены"

# --- 4. Запуск -------------------------------------------------------------

make_executable "$SAMMIE_DIR/run_sammie.command"
ok "Запуск: $SAMMIE_DIR/run_sammie.command"

echo
ok "Sammie-Roto-2 установлен."
echo "  Первый запуск:  двойной клик run_sammie.command (или: bash \"$SAMMIE_DIR/run_sammie.command\")"
echo "  При первом запуске Sammie скачает модели (~22GB) в $SAMMIE_DIR/checkpoints/"
echo "  Во Flame: правый клик на клипе → SammieRoto → Open Sammie 2.0"