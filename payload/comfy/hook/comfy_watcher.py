"""
ComfyUI Watcher - QTimer Polling Mode
Compatible with Flame (no raw threading)

Monitors ComfyUI output for new results and auto-imports into Flame.
Uses flame.schedule_idle_event() for safe Flame API calls — this is the
official Flame mechanism for executing Python in the idle loop, avoiding
timer conflicts (CoTimer assertions, SIGABRT/SIGSEGV).

Import target: Batch Schematic Reel "ComfyUI Results"
Optional: Pipeline result path copy (if configured in settings)
"""

import os
import re
import json
import shutil
from PySide6 import QtCore

try:
    import flame
except ImportError:
    flame = None


_HOME = os.path.expanduser("~")
CONFIG_FILE = os.path.join(_HOME, ".flame_comfy_config.json")


def log(msg):
    print(f"[ComfyUI] {msg}")
    try:
        if flame:
            flame.messages.show_in_console(msg, duration=0)
    except:
        pass


def _load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}


def _get_flame_attr_str(attr):
    """Safely extract string from Flame attribute, stripping quotes"""
    try:
        if hasattr(attr, 'get_value'):
            val = str(attr.get_value())
        else:
            val = str(attr)
        return val.strip("'\"")
    except:
        return ''


def _resolve_flame_tokens(path_template, clip_name=''):
    from datetime import datetime
    result = path_template
    now = datetime.now()
    replacements = {
        '<date>': now.strftime('%Y-%m-%d'),
        '<time>': now.strftime('%H%M%S'),
        '<YYYY>': now.strftime('%Y'),
        '<YY>': now.strftime('%y'),
        '<MM>': now.strftime('%m'),
        '<DD>': now.strftime('%d'),
        '<hh>': now.strftime('%H'),
        '<mm>': now.strftime('%M'),
        '<ss>': now.strftime('%S'),
        '<clip name>': clip_name,
    }
    try:
        if flame:
            project = flame.project.current_project
            replacements['<project>'] = _get_flame_attr_str(project.name)
            try: replacements['<project nickname>'] = _get_flame_attr_str(project.nickname)
            except: pass
            try: replacements['<user>'] = _get_flame_attr_str(flame.users.current_user.name)
            except: pass
            try: replacements['<user nickname>'] = _get_flame_attr_str(flame.users.current_user.nickname)
            except: pass
            try:
                import socket
                replacements['<workstation>'] = socket.gethostname()
            except: pass
            try:
                if hasattr(flame, 'batch') and flame.batch:
                    replacements['<batch name>'] = _get_flame_attr_str(flame.batch.name)
            except: pass
    except:
        pass
    for token, value in replacements.items():
        result = result.replace(token, value)
    return result


def _build_import_pattern(folder_path, files):
    """Build Flame-compatible import pattern from file list."""
    if not files:
        return None
    if len(files) == 1:
        return os.path.join(folder_path, files[0])
    match = re.search(r'(\d{4,})\.[^\.]+$', files[0])
    if match:
        seq_num = match.group(1)
        padding = len(seq_num)
        last_match = re.search(r'(\d{4,})\.[^\.]+$', files[-1])
        if last_match:
            start_str = str(int(seq_num)).zfill(padding)
            end_str = str(int(last_match.group(1))).zfill(padding)
            ext_part = files[0][match.end(1):]
            prefix = files[0][:match.start(1)]
            pattern_name = f"{prefix}[{start_str}-{end_str}]{ext_part}"
            return os.path.join(folder_path, pattern_name)
    return os.path.join(folder_path, files[0])


def _do_import_in_idle(notification, output_dir):
    """Import function executed via flame.schedule_idle_event.

    This runs in Flame's idle loop — the safe moment for Flame API calls.
    Same mechanism used by Flame's own watch_folder.py example.

    Supports both local and remote/pipeline imports:
    - Local: reads files from output_dir/output_folder
    - Pipeline: reads files from notification['pipeline_folder'] (network path)

    Import destination is read from config at call time:
    - "batch"   → Batch Schematic reel "ComfyUI Results" (default)
    - "library" → Library "ComfyUI" / date folder (V2.0 behavior)
    """
    if not flame:
        log("[Watcher] Flame not available for import")
        return

    output_folder = notification.get('output_folder', '')
    clip_name = notification.get('clip_name', output_folder)
    pipeline_folder = notification.get('pipeline_folder', '')

    # Determine source path: pipeline (network) or local
    if pipeline_folder and os.path.exists(pipeline_folder):
        folder_path = pipeline_folder
        log(f"[Watcher] Importing from pipeline: {folder_path}")
    else:
        folder_path = os.path.join(output_dir, output_folder)
        if pipeline_folder:
            log(f"[Watcher] Pipeline path not accessible ({pipeline_folder}), using local")

    if not os.path.exists(folder_path):
        log(f"[Watcher] ERROR: Folder not found: {folder_path}")
        return

    from datetime import datetime
    timestamp = datetime.now().strftime("%H%M%S")
    new_name = f"{clip_name}_comfyui_{timestamp}"

    log(f"[Watcher] Importing in idle: {clip_name}")

    # Read config to determine import destination (read fresh — reflects latest settings)
    cfg = _load_config()
    import_destination = cfg.get('import_destination', 'batch')

    try:
        if import_destination == 'library':
            # ==============================
            # Import into Library (V2.0 behavior)
            # Works regardless of whether a Batch is open
            # ==============================
            workspace = flame.project.current_project.current_workspace

            comfyui_lib = None
            for lib in (workspace.libraries or []):
                if str(lib.name).strip("'\" ") == "ComfyUI":
                    comfyui_lib = lib
                    break

            if comfyui_lib is None:
                comfyui_lib = workspace.create_library("ComfyUI")
                log("[Watcher] Library 'ComfyUI' created")

            today = datetime.now().strftime("%Y-%m-%d")
            date_folder = None
            for folder in comfyui_lib.folders:
                if str(folder.name).strip("'\" ") == today:
                    date_folder = folder
                    break

            if not date_folder:
                date_folder = comfyui_lib.create_folder(today)

            flame.import_clips(folder_path, date_folder)
            log(f"[Watcher] Imported to Library > ComfyUI > {today}: {clip_name}")

        else:
            # ==============================
            # Import into Batch Schematic Reel (default)
            # ==============================
            if not (hasattr(flame, 'batch') and flame.batch):
                log("[Watcher] ComfyUI results ready — open a Batch to auto-import (retrying...)")
                return  # early return: notification kept, watcher retries next tick

            reel_name = "ComfyUI Results"

            # Get or create reel
            target_reel = None
            for reel in flame.batch.reels:
                if str(reel.name) == reel_name:
                    target_reel = reel
                    break

            if not target_reel:
                target_reel = flame.batch.create_reel(reel_name)
                log(f"[Watcher] Created reel: {reel_name}")

            # Build import pattern
            files = sorted([
                f for f in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, f))
            ])

            import_path = _build_import_pattern(folder_path, files)
            if not import_path:
                log("[Watcher] ERROR: No files in result folder")
                return

            log(f"[Watcher] Importing: {import_path}")

            batch_clip = flame.batch.import_clip(import_path, reel_name)

            if batch_clip:
                try:
                    if hasattr(batch_clip, 'name'):
                        if hasattr(batch_clip.name, 'set_value'):
                            batch_clip.name.set_value(new_name)
                        else:
                            batch_clip.name = new_name
                except:
                    pass
                log(f"[Watcher] Imported to Batch Reel: {new_name}")
            else:
                log("[Watcher] Import returned empty — check console")

        # Notify user (shared — only reached if import succeeded)
        try:
            flame.messages.show_in_console(
                f"ComfyUI result imported: {new_name}",
                duration=5
            )
        except:
            pass

        # Clean notification files (shared — only reached if import succeeded)
        for notif_path in [os.path.join(output_dir, 'notification.json')]:
            try:
                if os.path.exists(notif_path):
                    os.remove(notif_path)
            except:
                pass

    except Exception as e:
        log(f"[Watcher] ERROR during idle import: {e}")
        import traceback
        traceback.print_exc()


class ComfyUIWatcher(QtCore.QObject):
    """Watcher using QTimer polling.
    
    SAFE IMPORT: When a notification is detected, the actual import is
    scheduled via flame.schedule_idle_event(), which executes the code
    in Flame's idle loop — the officially safe moment for API calls.
    No Flame API calls are made inside QTimer callbacks.
    
    Monitors two notification paths:
    - Local: ComfyUI output dir (same machine)
    - Pipeline: network share path (remote machines)
    """

    def __init__(self, output_dir, notification_file, check_interval=3000, pipeline_notification_file=None):
        super().__init__()
        self.output_dir = output_dir
        self.notification_file = notification_file
        self.pipeline_notification_file = pipeline_notification_file
        self.check_interval = check_interval
        self.last_notification_time = None
        self.imported_folders = set()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._check_notification)

        paths_info = f"local: {notification_file}"
        if pipeline_notification_file:
            paths_info += f" | pipeline: {pipeline_notification_file}"
        log(f"[Watcher] Initialized - polling every {check_interval/1000}s")
        log(f"[Watcher] Monitoring: {paths_info}")

    def start(self):
        if not self.timer.isActive():
            # Clean stale notification from previous sessions
            # This prevents "Destination is locked" on Flame startup
            self._clean_stale_notification()
            self.timer.start(self.check_interval)
            log("[Watcher] Started")

    def stop(self):
        if self.timer.isActive():
            self.timer.stop()
            log("[Watcher] Stopped")

    def _clean_stale_notification(self):
        """Remove notification.json left over from previous Flame session.
        Without this, the watcher picks up old notifications before the
        project is fully loaded, causing 'Destination is locked' errors."""
        for notif_path in [self.notification_file, self.pipeline_notification_file]:
            if not notif_path or not os.path.exists(notif_path):
                continue
            try:
                with open(notif_path, 'r') as f:
                    data = json.load(f)
                ts = data.get('timestamp', '')
                folder = data.get('output_folder', '')
                # Mark as already handled so it won't be processed
                if folder:
                    self.imported_folders.add(folder)
                    self.last_notification_time = ts
                os.remove(notif_path)
                log(f"[Watcher] Cleaned stale notification: {folder} ({notif_path})")
            except:
                try:
                    os.remove(notif_path)
                except:
                    pass

    def _check_notification(self):
        """Timer callback — reads notification file only. NO Flame API calls.
        Checks both local and pipeline notification paths."""
        
        # Check all notification paths — first match wins
        for notif_path in [self.notification_file, self.pipeline_notification_file]:
            if not notif_path or not os.path.exists(notif_path):
                continue
            
            try:
                with open(notif_path, 'r') as f:
                    notification = json.load(f)

                timestamp = notification.get('timestamp', '')
                output_folder = notification.get('output_folder', '')

                if not output_folder:
                    continue
                if output_folder in self.imported_folders:
                    # Already imported — clean up stale file
                    try:
                        os.remove(notif_path)
                    except:
                        pass
                    continue
                if self.last_notification_time and timestamp <= self.last_notification_time:
                    continue

                source = "pipeline" if notif_path == self.pipeline_notification_file else "local"
                log(f"[Watcher] New notification ({source}): {output_folder}")

                self.last_notification_time = timestamp
                self.imported_folders.add(output_folder)
                
                # Clean the notification file
                try:
                    os.remove(notif_path)
                except:
                    pass

                # Schedule import in Flame's idle loop — safe for API calls
                if flame and hasattr(flame, 'schedule_idle_event'):
                    flame.schedule_idle_event(
                        lambda notif=notification, out_dir=self.output_dir:
                            _do_import_in_idle(notif, out_dir)
                    )
                    log("[Watcher] Import scheduled for Flame idle loop")
                else:
                    log("[Watcher] flame.schedule_idle_event not available — manual import needed")
                
                return  # Process one notification at a time

            except json.JSONDecodeError:
                pass
            except Exception as e:
                log(f"[Watcher] Error: {e}")


# Global instance
_watcher = None

def start_watcher(output_dir, notification_file, pipeline_notification_file=None):
    global _watcher
    if _watcher:
        _watcher.stop()
    _watcher = ComfyUIWatcher(output_dir, notification_file, check_interval=3000,
                               pipeline_notification_file=pipeline_notification_file)
    _watcher.start()
    return _watcher

def stop_watcher():
    global _watcher
    if _watcher:
        _watcher.stop()
        _watcher = None
