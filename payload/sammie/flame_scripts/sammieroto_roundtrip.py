"""
SammieRoto RoundTrip for Flame 2025/2026/2027
Custom Action Type: Media Panel / Batch
"""
import flame
import os
import re
import time
import subprocess
import json
import datetime
from pathlib import Path

from sammie_roto_ui import prompt_for_result_import, show_setup_window

# ================== CONFIG ==================
SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(SCRIPT_PATH, 'config', 'sammie_config.json')
_PRESET_PATH = os.path.join(SCRIPT_PATH, 'EXPORT_JPEG_SAMMIE.xml')

DEFAULT_CONFIG = {
    'sammie_cmd': '/bin/bash',
    'sammie_launcher': os.path.expanduser('~/Documents/Sammie-Roto-2/run_sammie.command'),
    'preset_path': _PRESET_PATH,
    'export_path_template': '{nickname_raw}/{project_name_raw}/sammieroto',
    'result_reel_name': 'SammieRoto Results',
    'file_wait_timeout': 60
}

# ============================================

def log(msg):
    print(f"==SammieRoto_RoundTrip: {msg}")

def load_config():
    config_dir = os.path.dirname(CONFIG_PATH)
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                for key, value in DEFAULT_CONFIG.items():
                    if key not in config:
                        config[key] = value
                return config
        except Exception as e:
            log(f'Error loading config: {e}')
            return DEFAULT_CONFIG.copy()
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    try:
        config_dir = os.path.dirname(CONFIG_PATH)
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(CONFIG_PATH, 'w') as f:
            json.dump(config, f, indent=4)
        return True
    except Exception as e:
        log(f'Error saving config: {e}')
        return False

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', "_", name)

# ================== CLIP HELPERS ==================

def _typename(obj):
    return type(obj).__name__

def get_clip_from_item(item):
    """Extract clip from selection — works in Flame 2025/2026/2027."""
    # Check by type name (isinstance can fail if flame module context differs)
    item_type = _typename(item)
    if item_type in ('PyClip', 'PySequence'):
        return item
    if item_type == 'PyClipNode':
        for attr in ('clip', 'source', 'media', 'sequence', 'input'):
            val = getattr(item, attr, None)
            if val is not None and _typename(val) in ('PyClip', 'PySequence'):
                return val
        # Try input sockets as fallback
        if hasattr(item, 'input_sockets'):
            try:
                for s in item.input_sockets:
                    if hasattr(s, 'source') and _typename(s.source) in ('PyClip', 'PySequence'):
                        return s.source
            except Exception:
                pass
        return item
    return None

def get_clip_name(clip):
    try:
        name = clip.name.get_value()
        return name if name else 'unnamed_clip'
    except Exception:
        try:
            return str(clip.name)
        except Exception:
            return 'unnamed_clip'

def get_sequence_path(clip, subfolder="source"):
    config = load_config()
    clip_name = get_clip_name(clip)
    base = resolve_path_template(config['export_path_template'], clip=clip, clip_name=clip_name)
    return os.path.join(base, subfolder)

# ================== TOKEN RESOLUTION ==================

def get_current_project_info():
    try:
        p = flame.project.current_project
        return str(p.name), str(p.nickname)
    except Exception:
        return "Unknown_Project", "No_Nickname"

def resolve_path_template(template, clip=None, clip_name='', batch_name=''):
    project_name_raw, nickname_raw = get_current_project_info()
    now = datetime.datetime.now()
    try:
        batch_group_name = flame.batch.name.get_value() if not batch_name else batch_name
    except Exception:
        batch_group_name = batch_name or 'batch'
    try:
        batch_iter = str(flame.batch.batch_iteration)
    except Exception:
        batch_iter = '1'
    tokens = {
        'project_name_raw': project_name_raw,
        'nickname_raw': nickname_raw,
        'clip_name': sanitize_filename(clip_name),
        'shot_name': sanitize_filename(clip_name),
        'batch_name': sanitize_filename(batch_group_name),
        'batch_iteration': batch_iter,
        'user_name': os.environ.get('USER', 'unknown'),
        'date_YYYY': now.strftime('%Y'),
        'date_MM': now.strftime('%m'),
        'date_DD': now.strftime('%d'),
        'date_YYYY_MM_DD': now.strftime('%Y-%m-%d'),
        'timestamp': str(int(now.timestamp())),
    }
    try:
        return template.format(**tokens)
    except KeyError:
        import string
        fmt = string.Formatter()
        result = template
        for _, fn, _, _ in fmt.parse(template):
            if fn and fn in tokens:
                result = result.replace(f'{{{fn}}}', tokens[fn])
        return result

# ================== EXPORT ==================

def export_clip_to_jpeg_sequence(clip, preset_path):
    sequence_dir = get_sequence_path(clip, subfolder="source")
    clip_name = sanitize_filename(get_clip_name(clip))
    log(f"Exporting clip: {clip_name} -> {sequence_dir}")
    try:
        if not os.path.exists(sequence_dir):
            os.makedirs(sequence_dir)
        if not os.path.exists(preset_path):
            log(f"ERROR: Preset not found: {preset_path}")
            return None
        exporter = flame.PyExporter()
        exporter.foreground = True
        exporter.export(clip, preset_path, sequence_dir)
        return sequence_dir
    except Exception as e:
        log(f"Export error: {e}")
        return None

def wait_for_sequence(sequence_dir, timeout=None):
    config = load_config()
    timeout = timeout or config['file_wait_timeout']
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(sequence_dir):
            files = [f for f in os.listdir(sequence_dir)
                     if f.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff', '.exr'))]
            if files:
                first = os.path.join(sequence_dir, sorted(files)[0])
                if os.path.getsize(first) > 0:
                    time.sleep(1)
                    return first
        time.sleep(0.5)
    return None

# ================== SAMMIE LAUNCHER ==================

def open_sequence_in_sammie(first_frame_path):
    config = load_config()
    launcher = config['sammie_launcher']
    if not os.path.exists(launcher):
        log(f"ERROR: Sammie launcher not found: {launcher}")
        return
    if not os.access(launcher, os.X_OK):
        log(f"ERROR: Sammie launcher not executable: {launcher}")
        return
    try:
        cmd = [config['sammie_cmd'], launcher, first_frame_path]
        log(f"Launching: {' '.join(cmd)}")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception as e:
        log(f"ERROR launching Sammie: {e}")

# ================== IMPORT ==================

def get_or_create_result_reel(reel_name):
    try:
        for reel in flame.batch.reels:
            if reel.name == reel_name:
                return reel
        return flame.batch.create_reel(reel_name)
    except Exception as e:
        log(f"ERROR creating reel '{reel_name}': {e}")
        return None

def import_sequences_to_batch(sequence_list):
    config = load_config()
    reel = get_or_create_result_reel(config['result_reel_name'])
    if not reel:
        return []
    imported = []
    for seq in sequence_list:
        try:
            clip_node = flame.batch.import_clip(seq['import_pattern'], config['result_reel_name'])
            if clip_node:
                try:
                    clip_node.name = seq['name']
                except Exception:
                    pass
                imported.append(clip_node)
        except Exception as e:
            log(f"ERROR importing {seq['name']}: {e}")
    return imported

# ================== MAIN ACTIONS ==================

_import_dialog_ref = None
_setup_window_ref = None

def export_and_open_sammie(selection):
    global _import_dialog_ref
    config = load_config()
    log("=" * 50)
    log("OPEN SAMMIE 2.0")
    log("=" * 50)

    import flame

    if not os.path.exists(config['preset_path']):
        log(f"ERROR: Preset not found: {config['preset_path']}")
        flame.messages.show_in_console("SammieRoto: Preset not found", duration=8)
        return
    if not os.path.exists(config['sammie_launcher']):
        log(f"ERROR: Launcher not found: {config['sammie_launcher']}")
        flame.messages.show_in_console("SammieRoto: Launcher not found", duration=8)
        return

    flame.messages.show_in_console("SammieRoto: Exporting clip as JPEG sequence...", duration=5)

    for item in selection:
        clip = get_clip_from_item(item)
        if clip and not _typename(clip) in ('PyClipNode',):
            log(f"Exporting clip: {get_clip_name(clip)}")
            seq_dir = export_clip_to_jpeg_sequence(clip, config['preset_path'])
            if seq_dir:
                log(f"Waiting for frames in: {seq_dir}")
                flame.messages.show_in_console(f"SammieRoto: Waiting for frames...", duration=3)
                first_frame = wait_for_sequence(seq_dir)
                if first_frame:
                    result_dir = get_sequence_path(clip, subfolder="result")
                    log(f"Result dir: {result_dir}")
                    os.makedirs(result_dir, exist_ok=True)
                    flame.messages.show_in_console("SammieRoto: Launching Sammie...", duration=5)
                    open_sequence_in_sammie(first_frame)
                    def on_import_requested(seq_list, group_mattes):
                        imported_clips = import_sequences_to_batch(seq_list)
                    dialog = prompt_for_result_import(
                        result_dir, import_callback=on_import_requested,
                        get_existing_groups=lambda: [],
                        log_func=log)
                    if dialog:
                        _import_dialog_ref = dialog
                        dialog.show()
                    return
                else:
                    log(f"ERROR: Export timeout: {seq_dir}")
                    flame.messages.show_in_console("SammieRoto: Export timeout", duration=8)
            else:
                log("ERROR: Export failed")
                flame.messages.show_in_console("SammieRoto: Export failed (check Console)", duration=8)
        else:
            log(f"ERROR: Invalid clip: {clip}")
            flame.messages.show_in_console("SammieRoto: Invalid clip selection", duration=5)

def import_results_only(selection):
    global _import_dialog_ref
    config = load_config()
    if not selection:
        return
    item = selection[0]
    clip = get_clip_from_item(item)
    if clip:
        result_dir = get_sequence_path(clip, subfolder="result")
        def on_import_requested(seq_list, group_mattes):
            imported_clips = import_sequences_to_batch(seq_list)
        dialog = prompt_for_result_import(
            result_dir, import_callback=on_import_requested,
            get_existing_groups=lambda: [],
            log_func=log)
        if dialog:
            _import_dialog_ref = dialog
            dialog.show()

def setup_window(selection):
    global _setup_window_ref
    config = load_config()
    _setup_window_ref = show_setup_window(config, save_config, log_func=log)

# ================== MENUS ==================

def get_main_menu_custom_ui_actions():
    return [{'name': 'SammieRoto Setup', 'actions': [{
        'name': 'SammieRoto Setup', 'execute': setup_window
    }]}]

def get_media_panel_custom_ui_actions():
    return [{"name": "SammieRoto...", "actions": [
        {"name": "Open Sammie 2.0", "execute": export_and_open_sammie},
        {"name": "Import Results", "execute": import_results_only},
        {"name": "Setup", "execute": setup_window},
    ]}]

def get_batch_custom_ui_actions():
    return [{"name": "SammieRoto...", "actions": [
        {"name": "Open Sammie 2.0", "execute": export_and_open_sammie},
        {"name": "Import Results", "execute": import_results_only},
        {"name": "Setup", "execute": setup_window},
    ]}]

get_media_panel_custom_ui_actions.minimum_version = "2022"
get_batch_custom_ui_actions.minimum_version = "2022"
get_main_menu_custom_ui_actions.minimum_version = "2022"
