# flame-ai-stack

Универсальный установщик AI-стека для **Autodesk Flame на Apple Silicon (M-серия)**.
Разворачивает на чистой машине два инструмента:

| Компонент | Что даёт | Модели |
|---|---|---|
| **ComfyUI + SAM3.1 + MatAnyone2** | текстово-промптовый маттинг прямо из Batch (правый клик на клипе → ComfyUI → SAM3_MatAnyone2_Matte), результат авто-импортируется в рил | SAM3.1 (1.75GB), MatAnyone ×2 (141MB×2) — скачивает установщик |
| **Sammie-Roto-2** | десктопная AI-ротоскопия: SAM2 сегментация, MatAnyone/VideoMaMa маттинг, MiniMax-Remover удаление объектов + round-trip со Flame | ~22GB — **Sammie качает сам** при первом запуске через свой интерфейс |

Проверено на: MBP M5 Max 48GB, macOS, Flame 2027, Python 3.12, PyTorch MPS.

---

## Быстрый старт

```bash
git clone <url-репозитория> flame-ai-stack
cd flame-ai-stack
./install.sh                    # всё: Comfy-стек + Sammie
```

По завершении:

1. **Перезапусти Flame** — хуки читаются при старте
2. Запусти ComfyUI: `~/Documents/ComfyUI/start_comfyui.command` (или двойной клик в Finder)
3. Проверь `http://127.0.0.1:8000` — в `/object_info` должны быть ноды `FlameLoad`, `FlameSend`, `SAM3_Detect`, `MatAnyone2`
4. Sammie: двойной клик `~/Documents/Sammie-Roto-2/run_sammie.command` — при первом запуске скачает модели

Диагностика: `./install.sh --check` — проверит всю установку и покажет, чего не хватает.

---

## Флаги

| Флаг | Действие |
|---|---|
| `./install.sh` | установить всё (Comfy + Sammie) |
| `./install.sh --comfy` | только Comfy-стек |
| `./install.sh --sammie` | только Sammie |
| `./install.sh --check` | диагностика установленного (ничего не меняет) |
| `./install.sh --skip-models` | пропустить скачивание весов (Comfy-стек) |

Переменные окружения (опциональны): `COMFY_DIR`, `SAMMIE_DIR`, `PYTHON3`, `COMFYUI_REF`, `MATANYONE_REF`, `SAMMIE_TAG`.

---

## Что именно устанавливается

### Comfy-стек (`scripts/install_comfy.sh`)

1. **ComfyUI** — клон + checkout на проверенный коммит `0d8b7510` (v0.25.0-31)
2. **venv Python 3.12** + `requirements.txt` + `OpenEXR` (настоящий EXR, иначе FlameSend молча падает в PNG) + `av` (ProRes 4444 .mov с альфой)
3. **flame_integration** — custom node `FlameLoad`/`FlameSend` (патченая копия):
   - поддержка `.mov` (ProRes 4444 + альфа) через PyAV
   - premultiply при записи ProRes и EXR (стандарт композитинга во Flame)
   - сортировка папок FlameLoad по времени, а не по имени
   - параметры `fps` и `colour_space` для ProRes
4. **ComfyUI-MatAnyone** — клон на `87cbce3` + **MPS-патч**: `mat_anyone.py`/`mat_anyone2.py` и `src/` заменяются на версии с `_detect_device()` (cuda → mps → cpu). Без патча MatAnyone на Mac молча работает на CPU — в десятки раз медленнее.
5. **Модели**: `sam3.1_multiplex_fp16.safetensors` (1.75GB, princeton-vl/SAM3.1) + `matanyone.pth`/`matanyone2.pth` (FuouM/MatAnyone)
6. **Workflow**: `SAM3_MatAnyone2_Matte.json` (API, в `flame_comfy_workflows/` — из него строятся пункты меню правого клика) + `_UI.json` (для просмотра в интерфейсе ComfyUI)
7. **Flame-хуки** в `/opt/Autodesk/shared/python/comfy_integration/`: `comfy_integration.py`, `comfy_watcher.py`, 5 пресетов экспорта (формат v15, без предупреждений Flame)
8. **Конфиг** `~/.flame_comfy_config.json` — генерируется из шаблона, пути подставляются под текущего пользователя
9. **`start_comfyui.command`** — запуск ComfyUI на порту 8000 с MPS

**Watcher** (`comfy_watcher.py`) следит за `output/flame_returns/` и авто-импортирует результаты в рил. Стартует автоматически из хука при запуске Flame (`auto_import: true`).

### Sammie (`scripts/install_sammie.sh`)

1. **Скачивание релиза** с GitHub (`Zarxrax/Sammie-Roto-2`, по умолчанию `v2.3.3`)
2. **venv Python 3.12** + PyTorch MPS + `requirements.txt`
3. **Round-trip скрипты** в `/opt/Autodesk/shared/python/`: `sammieroto_roundtrip.py`, `sammie_roto_ui.py`, `pyflame_lib_sammie_roto.py`, пресет `EXPORT_JPEG_SAMMIE.xml`, конфиг `config/sammie_config.json` (генерируется из шаблона)
4. **Модели НЕ скачиваются** — Sammie тянет их сам при первом запуске (~22GB в `checkpoints/`)

---

## Рабочий цикл

### Маттинг через ComfyUI (текстовый промпт)

1. В Batch: правый клик на клипе → **ComfyUI** → **SAM3_MatAnyone2_Matte**
2. В диалоге: Output Mode (`Matte` EXR / `Video with Alpha` ProRes), Key Frame, промпт
3. Flame экспортирует кадры → ComfyUI обрабатывает → результат авто-импортируется в рил

### Ротоскопия через Sammie

1. В Batch: правый клик на клипе → **SammieRoto** → **Open Sammie 2.0**
2. Маска/маттинг/удаление в Sammie, сохранение
3. Правый клик на том же клипе → **SammieRoto** → **Import Results** — результат в риле `SammieRoto Results`

---

## Требования

- macOS на **Apple Silicon** (arm64)
- **Autodesk Flame** установлен (хуки ставятся в `/opt/Autodesk/shared/python/`)
- **Python 3.10+** (рекомендуется 3.12) — если нет: `brew install python@3.12`
- **git**, **curl**
- 8GB+ VRAM (рекомендуется 16GB+)
- Свободное место: ~5GB (Comfy-стек) + ~22GB (модели Sammie при первом запуске)

Установщик идемпотентен — повторный запуск безопасен. При установке в `/opt/Autodesk/` может попросить sudo.

---

## Troubleshooting

| Симптом | Причина / решение |
|---|---|
| Результат PNG вместо EXR | нет `OpenEXR` в venv → `./install.sh --comfy` (доустановит) |
| `.mov` не приходит | ошибка PyAV → проверить `pip install av` в venv |
| Маттинг очень медленный (секунды на кадр) | MPS-патч не применён — переустановить: `./install.sh --comfy` |
| Нет пункта меню ComfyUI в правом клике | Flame запущен до установки хука → перезапустить Flame |
| Всё стоит, но что-то не работает | `./install.sh --check` — покажет, чего не хватает |

## Резервные адреса моделей 
Модель	   URL
SAM3.1	   https://huggingface.co/Comfy-Org/sam3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors

MatAnyone2	https://github.com/pq-yang/MatAnyone2/releases/download/v1.0.0/matanyone2.pth

MatAnyone1	https://github.com/pq-yang/MatAnyone/releases/download/v1.0.0/matanyone.pth

ComfyUI-MatAnyone (коммит)	https://github.com/FuouM/ComfyUI-MatAnyone/commit/87cbce3

---

## English summary

Self-contained installer for the Flame AI stack on Apple Silicon. Two components:
**ComfyUI + SAM3.1 + MatAnyone2** (text-prompt matting from Batch, auto-import results)
and **Sammie-Roto-2** (AI rotoscoping with Flame round-trip). Idempotent bash scripts,
configs generated per-user. Models for Sammie auto-download on first launch.
Verify any installation with `./install.sh --check`.


## Credits

Этот стек собран на основе чужих наработок. Уважение и благодарность авторам:

| Проект | Автор | Роль в стеке |
|---|---|---|
| **Sammie-Roto-2** | [Zarxrax](https://github.com/Zarxrax/Sammie-Roto-2) | десктопная AI-ротоскопия (SAM2, MatAnyone, VideoMaMa, MiniMax-Remover) + round-trip со Flame |
| **ComfyUI** | [comfyanonymous](https://github.com/comfyanonymous/ComfyUI) | базовый движок Comfy-стека |
| **SAM 3.1** | [princeton-vl](https://github.com/princeton-vl/SAM3) | сегментация по текстовому промпту (модель качается из зеркала [Comfy-Org/sam3.1](https://huggingface.co/Comfy-Org/sam3.1)) |
| **MatAnyone** | [pq-yang](https://github.com/pq-yang/MatAnyone) | маттинг видео (объект по референсному кадру) |
| **MatAnyone2** | [pq-yang](https://github.com/pq-yang/MatAnyone2) | следующее поколение маттинга |
| **ComfyUI-MatAnyone** | [FuouM](https://github.com/FuouM/ComfyUI-MatAnyone) | обвязка MatAnyone под ComfyUI (патчена под MPS) |


Модели и чекпоинты принадлежат их авторам; установщик лишь скачивает их по публичным ссылкам.
