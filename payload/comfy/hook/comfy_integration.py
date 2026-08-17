# -*- coding: utf-8 -*-

"""
ComfyUI Integration for Flame
Version: 2.0 - Workflow Integration
Author: Gaspar Matheron
Creation Date: 07.02.2025

Description:
    Export clips to ComfyUI and automatically load them in a selected workflow.
    
Menu:
    Right-click on clip -> ComfyUI -> [List of available workflows]

To install:
    1. Copy comfy_integration.py to: /opt/Autodesk/shared/python/comfy_integration/
    2. Copy EXPORT_PNG_COMFYUI.xml to: /opt/Autodesk/shared/python/comfy_integration/
    3. Save your ComfyUI workflows as JSON in: ~/flame_comfy_workflows/
    4. Restart Flame

Workflow Setup:
    1. In ComfyUI, create your workflow (e.g., with MatAnyone for matting)
    2. Save the workflow as API format: Settings -> Enable Dev Mode Options
    3. Click "Save (API Format)" and save to ~/flame_comfy_workflows/AutoMatte.json
    4. The workflow will appear in the Flame menu automatically
"""

import os
import re
import time
import json
import platform
import urllib.request
import urllib.error
from pathlib import Path
from PySide6 import QtWidgets, QtCore, QtGui

# Import watcher module
try:
    import comfy_watcher
except ImportError:
    comfy_watcher = None
    print("[ComfyUI] Warning: comfy_watcher not available")

# ================== CONFIG ==================
CONFIG_FILE = os.path.expanduser("~/.flame_comfy_config.json")

# Default configuration — dynamic paths based on current user
_HOME = os.path.expanduser("~")
_IS_LINUX = platform.system() == 'Linux'

# Determine default ComfyUI path based on OS
if _IS_LINUX:
    _COMFY_BASE = os.path.join(_HOME, "ComfyUI")
else:
    _COMFY_BASE = os.path.join(_HOME, "Documents", "ComfyUI")

DEFAULT_CONFIG = {
    "comfy_url": "http://127.0.0.1",
    "comfy_port": 8188 if _IS_LINUX else 8000,
    "comfy_input_dir": os.path.join(_COMFY_BASE, "input", "Flame_outputs"),
    "comfy_output_dir": os.path.join(_COMFY_BASE, "output", "flame_returns"),
    "preset_path": "/opt/Autodesk/shared/python/comfy_integration/export_presets/EXPORT_PNG_COMFYUI.xml",
    "export_format": "PNG 8-bit",
    "presets_dir": "/opt/Autodesk/shared/python/comfy_integration/export_presets",
    "workflows_dir": os.path.join(_COMFY_BASE, "flame_comfy_workflows"),
    "pipeline_export_path": "",  # Token-based path for exports (symlinked into ComfyUI input)
    "pipeline_result_path": "",  # Token-based path for results (copied from ComfyUI output)
    "output_format": "png",
    "output_quality": 95,
    "colorspace": "default",
    "timeout": 300,
    "auto_import": True,
    "import_destination": "batch",  # "batch" or "library"
    "open_browser_manual": True,
    "show_notifications": True,
    "favorite_workflows": [],  # List of favorite workflow names
    "connection_mode": "local",  # local, remote_ssh, network_share
    "remote_ssh_host": "user@remote-host",
    "remote_path": "/home/user/ComfyUI/input/Flame_outputs",
}

# Export format presets mapping: display name -> preset filename
EXPORT_PRESETS = {
    "PNG 8-bit": "EXPORT_PNG_COMFYUI.xml",
    "PNG 16-bit": "EXPORT_PNG16_COMFYUI.xml",
    "EXR 16-bit float": "EXPORT_EXR_COMFYUI.xml",
    "EXR 32-bit float": "EXPORT_EXR32_COMFYUI.xml",
    "JPEG 8-bit": "EXPORT_JPEG_COMFYUI.xml",
}

def get_preset_path_for_format(export_format):
    """Resolve export format name to full preset path"""
    presets_dir = CONFIG.get('presets_dir', DEFAULT_CONFIG['presets_dir'])
    preset_file = EXPORT_PRESETS.get(export_format, '')
    if preset_file:
        return os.path.join(presets_dir, preset_file)
    # Fallback: might be a custom preset path
    return CONFIG.get('preset_path', DEFAULT_CONFIG['preset_path'])

# Load config
def load_config():
    """Load configuration from JSON file"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            # Merge with defaults for new parameters
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            return config
        except Exception as e:
            log(f"Config load error: {e}")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to JSON file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        log(f"Configuration saved: {CONFIG_FILE}")
        return True
    except Exception as e:
        log(f"Config save error: {e}")
        return False

# ========== PROFILES MANAGEMENT ==========
PROFILES_DIR = os.path.expanduser("~/.flame_comfy_profiles")

def get_profile_path(profile_name):
    """Return path to a profile file"""
    safe_name = profile_name.replace(" ", "_").lower()
    return os.path.join(PROFILES_DIR, f"{safe_name}.json")

def list_profiles():
    """List all available profiles"""
    if not os.path.exists(PROFILES_DIR):
        return []
    
    profiles = []
    for filename in os.listdir(PROFILES_DIR):
        if filename.endswith('.json'):
            profile_name = filename[:-5].replace("_", " ").title()
            profiles.append(profile_name)
    
    return sorted(profiles)

def save_profile(profile_name, config):
    """Save a configuration profile"""
    try:
        if not os.path.exists(PROFILES_DIR):
            os.makedirs(PROFILES_DIR)
        
        profile_path = get_profile_path(profile_name)
        with open(profile_path, 'w') as f:
            json.dump(config, f, indent=2)
        
        log(f"Profile saved: {profile_name}")
        return True
    except Exception as e:
        log(f"Profile save error: {e}")
        return False

def load_profile(profile_name):
    """Load a configuration profile"""
    try:
        profile_path = get_profile_path(profile_name)
        if os.path.exists(profile_path):
            with open(profile_path, 'r') as f:
                config = json.load(f)
            
            # Merge with defaults
            for key, value in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = value
            
            return config
        return None
    except Exception as e:
        log(f"Profile load error: {e}")
        return None

def delete_profile(profile_name):
    """Delete a profile"""
    try:
        profile_path = get_profile_path(profile_name)
        if os.path.exists(profile_path):
            os.remove(profile_path)
            log(f"Profile deleted: {profile_name}")
            return True
        return False
    except Exception as e:
        log(f"Profile delete error: {e}")
        return False

# Load config at startup
CONFIG = load_config()

# Global variables (for compatibility with existing code)
COMFY_URL = f"{CONFIG['comfy_url']}:{CONFIG['comfy_port']}"
COMFY_INPUT_DIR = CONFIG['comfy_input_dir']
COMFY_OUTPUT_DIR = CONFIG['comfy_output_dir']
PRESET_PATH = get_preset_path_for_format(CONFIG.get('export_format', 'PNG 8-bit'))
WORKFLOWS_DIR = CONFIG['workflows_dir']

FLAME_NOTIFICATION_FILE = os.path.join(COMFY_OUTPUT_DIR, 'notification.json')

FILE_WAIT_TIMEOUT = 60
__version__ = "2.1"
# ============================================


def log(msg):
    """Print with prefix"""
    print(f"[ComfyUI] {msg}")


def sanitize_filename(name):
    """Sanitize filename"""
    return re.sub(r'[<>:"/\\|?*]', "_", name)


# ========== PYFLAME STANDARD COLORS (Flame 2025/2026) ==========
PYFLAME_FONT = 'Discreet'
PYFLAME_FONT_SIZE = 13

# Core palette
FLAME_BG = 'rgb(36, 36, 36)'
FLAME_MID_BG = 'rgb(45, 45, 45)'
FLAME_WIDGET_BG = 'rgb(58, 58, 58)'
FLAME_WIDGET_HOVER = 'rgb(71, 71, 71)'
FLAME_INPUT_BG = 'rgb(55, 65, 75)'
FLAME_INPUT_FOCUS = 'rgb(73, 86, 99)'
FLAME_TEXT = 'rgb(154, 154, 154)'
FLAME_TEXT_BRIGHT = 'rgb(210, 210, 210)'
FLAME_TEXT_DIM = 'rgb(100, 100, 100)'
FLAME_BLUE = 'rgb(0, 110, 175)'
FLAME_HIGHLIGHT = 'rgb(74, 158, 255)'
FLAME_BORDER = 'rgb(90, 90, 90)'
FLAME_RED = 'rgb(200, 29, 29)'
FLAME_GREEN = 'rgb(0, 150, 64)'
FLAME_DISABLED = 'rgb(54, 54, 54)'



# ========== FLAME TOKEN SYSTEM ==========
# Tokens matching Flame WriteFile node (from Flame 2025/2026)
FLAME_TOKENS = {
    'Project': [
        ('<project>', 'Project'),
        ('<project nickname>', 'Project Nickname'),
    ],
    'User': [
        ('<user>', 'User'),
        ('<user nickname>', 'User Nickname'),
        ('<workstation>', 'Workstation'),
    ],
    'Batch': [
        ('<batch name>', 'Batch Name'),
        ('<batch iteration>', 'Batch Iteration'),
        ('<iteration>', 'Iteration'),
    ],
    'Clip': [
        ('<clip name>', 'Clip Name'),
        ('<shot name>', 'Shot Name'),
        ('<tape>', 'Tape/Reel/Source'),
        ('<clip height>', 'Clip Height'),
        ('<clip width>', 'Clip Width'),
        ('<clip resolution>', 'Clip Resolution'),
        ('<colour space>', 'Colour Space'),
        ('<extension>', 'Extension'),
        ('<polarity>', 'Polarity'),
    ],
    'Date/Time': [
        ('<date>', 'Date'),
        ('<time>', 'Time'),
        ('<YYYY>', 'Year (YYYY)'),
        ('<YY>', 'Year (YY)'),
        ('<MM>', 'Month'),
        ('<DD>', 'Day'),
        ('<hh>', 'Hour'),
        ('<mm>', 'Minute'),
        ('<ss>', 'Second'),
    ],
}


def _get_flame_attr_str(attr):
    """Safely extract string from a Flame attribute, stripping quotes"""
    try:
        if hasattr(attr, 'get_value'):
            val = str(attr.get_value())
        else:
            val = str(attr)
        # Strip quotes that Flame PyFlameAttribute may include
        return val.strip("'\"")
    except:
        return ''


def resolve_flame_tokens(path_template):
    """Resolve Flame tokens in a path template using current project context.
    Tokens that cannot be resolved are preserved as-is."""
    from datetime import datetime
    
    result = path_template
    now = datetime.now()
    
    # Date/Time tokens - always available
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
    }
    
    # Flame context tokens - try to resolve, keep as-is if unavailable
    try:
        import flame
        project = flame.project.current_project
        replacements['<project>'] = _get_flame_attr_str(project.name)
        
        try:
            replacements['<project nickname>'] = _get_flame_attr_str(project.nickname)
        except:
            pass
        
        try:
            replacements['<user>'] = _get_flame_attr_str(flame.users.current_user.name)
        except:
            pass
        
        try:
            replacements['<user nickname>'] = _get_flame_attr_str(flame.users.current_user.nickname)
        except:
            pass
        
        try:
            import socket
            replacements['<workstation>'] = socket.gethostname()
        except:
            pass
            
        try:
            if hasattr(flame, 'batch') and flame.batch:
                replacements['<batch name>'] = _get_flame_attr_str(flame.batch.name)
                try:
                    replacements['<batch iteration>'] = _get_flame_attr_str(flame.batch.iteration)
                except:
                    pass
        except:
            pass
            
    except:
        pass
    
    for token, value in replacements.items():
        result = result.replace(token, value)
    
    return result


class FlameTokenButton(QtWidgets.QPushButton):
    """Button that shows a popup menu with Flame tokens to insert into a QLineEdit"""
    
    def __init__(self, target_line_edit, parent=None):
        super().__init__("Add Token ▾", parent)
        self.target = target_line_edit
        self.setFixedWidth(100)
        self.setMinimumHeight(28)
        self.setObjectName("primary")
        self.clicked.connect(self._show_menu)
    
    def _show_menu(self):
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {FLAME_MID_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                padding: 4px;
                font-family: '{PYFLAME_FONT}';
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
            }}
            QMenu::item:selected {{
                background-color: {FLAME_BLUE};
                color: {FLAME_TEXT_BRIGHT};
            }}
            QMenu::separator {{
                height: 1px;
                background: rgb(70, 70, 70);
                margin: 4px 8px;
            }}
        """)
        
        for category, tokens in FLAME_TOKENS.items():
            # Category header (disabled)
            header = menu.addAction(f"── {category} ──")
            header.setEnabled(False)
            
            for token, display_name in tokens:
                action = menu.addAction(f"  {display_name}   →   {token}")
                action.triggered.connect(
                    lambda checked=False, t=token: self._insert_token(t)
                )
            
            menu.addSeparator()
        
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        menu.exec_(pos)
    
    def _insert_token(self, token):
        cursor_pos = self.target.cursorPosition()
        current = self.target.text()
        new_text = current[:cursor_pos] + token + current[cursor_pos:]
        self.target.setText(new_text)
        self.target.setCursorPosition(cursor_pos + len(token))
        self.target.setFocus()


def get_flame_stylesheet():
    """Return the standard PyFlame stylesheet for dialogs"""
    return f"""
        QDialog {{
            background-color: {FLAME_BG};
            color: {FLAME_TEXT};
            font-family: '{PYFLAME_FONT}';
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QLabel {{
            color: {FLAME_TEXT};
            background-color: transparent;
            border: none;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QLabel#header {{
            font-size: 15px;
            color: {FLAME_TEXT_DIM};
            font-weight: 300;
        }}

        QLabel#section {{
            font-size: {PYFLAME_FONT_SIZE}px;
            color: {FLAME_TEXT_DIM};
            padding: 10px 0px 6px 0px;
        }}

        QLineEdit {{
            color: {FLAME_TEXT};
            background-color: {FLAME_INPUT_BG};
            border: 1px solid {FLAME_INPUT_BG};
            selection-color: rgb(38, 38, 38);
            selection-background-color: rgb(184, 177, 167);
            padding: 6px 8px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QLineEdit:focus {{
            background-color: {FLAME_INPUT_FOCUS};
        }}

        QLineEdit:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QPlainTextEdit {{
            color: {FLAME_TEXT};
            background-color: {FLAME_INPUT_BG};
            border: 1px solid {FLAME_INPUT_BG};
            selection-color: rgb(38, 38, 38);
            selection-background-color: rgb(184, 177, 167);
            padding: 6px 8px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QPlainTextEdit:focus {{
            background-color: {FLAME_INPUT_FOCUS};
        }}

        QPlainTextEdit:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QComboBox {{
            background-color: {FLAME_WIDGET_BG};
            color: {FLAME_TEXT};
            border: none;
            padding: 6px 12px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QComboBox:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QComboBox::drop-down {{
            border: none;
            width: 20px;
        }}

        QComboBox QAbstractItemView {{
            background-color: {FLAME_WIDGET_BG};
            color: {FLAME_TEXT};
            selection-background-color: {FLAME_BLUE};
            selection-color: {FLAME_TEXT_BRIGHT};
            border: none;
        }}

        QSpinBox {{
            background-color: {FLAME_INPUT_BG};
            color: {FLAME_TEXT};
            border: 1px solid {FLAME_INPUT_BG};
            padding: 6px 8px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QSpinBox:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QSpinBox::up-button, QSpinBox::down-button {{
            background-color: transparent;
            border: none;
            width: 16px;
        }}

        QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
            background-color: {FLAME_WIDGET_HOVER};
        }}

        QPushButton {{
            background-color: {FLAME_WIDGET_BG};
            color: rgb(165, 165, 165);
            border: none;
            padding: 8px 20px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QPushButton:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QPushButton:pressed {{
            color: {FLAME_TEXT_BRIGHT};
            background-color: {FLAME_WIDGET_HOVER};
        }}

        QPushButton:focus {{
            outline: none;
            border: none;
        }}

        QPushButton#primary {{
            background-color: {FLAME_BLUE};
            color: rgb(185, 185, 185);
        }}

        QPushButton#primary:hover {{
            border: 1px solid {FLAME_BORDER};
        }}

        QPushButton#primary:pressed {{
            color: {FLAME_TEXT_BRIGHT};
        }}

        QPushButton:disabled {{
            color: {FLAME_TEXT_DIM};
            background-color: {FLAME_DISABLED};
        }}

        QCheckBox {{
            color: {FLAME_TEXT};
            spacing: 8px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            background-color: {FLAME_WIDGET_BG};
            border: none;
        }}

        QCheckBox::indicator:hover {{
            background-color: {FLAME_WIDGET_HOVER};
        }}

        QCheckBox::indicator:checked {{
            background-color: {FLAME_BLUE};
        }}

        QGroupBox {{
            color: {FLAME_TEXT_DIM};
            border: 1px solid rgb(50, 50, 50);
            border-radius: 0px;
            margin-top: 12px;
            padding-top: 16px;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
        }}

        QTabWidget::pane {{
            border: none;
            background-color: {FLAME_BG};
        }}

        QTabBar::tab {{
            background-color: transparent;
            color: {FLAME_TEXT_DIM};
            padding: 10px 20px;
            border: none;
            border-bottom: 2px solid transparent;
            font-size: {PYFLAME_FONT_SIZE}px;
        }}

        QTabBar::tab:hover {{
            color: {FLAME_TEXT};
        }}

        QTabBar::tab:selected {{
            color: {FLAME_TEXT};
            border-bottom: 2px solid {FLAME_BLUE};
        }}

        QScrollArea {{
            background-color: transparent;
            border: none;
        }}

        QScrollBar:vertical {{
            background: {FLAME_BG};
            width: 12px;
            margin: 0;
        }}

        QScrollBar::handle:vertical {{
            background: {FLAME_BORDER};
            min-height: 20px;
            border-radius: 3px;
            margin: 2px;
        }}

        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
    """


class ComfyUISettingsDialog(QtWidgets.QDialog):
    """ComfyUI Integration Settings Dialog - Flame Style"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ComfyUI Integration - Settings")
        self.setMinimumSize(800, 650)
        self.config = load_config()
        self.setup_ui()
        self.setStyleSheet(get_flame_stylesheet())
    
    def setup_ui(self):
        """Create Logik Portal style interface"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setSpacing(20)
        container_layout.setContentsMargins(30, 30, 30, 30)
        
        # Header
        header_layout = QtWidgets.QVBoxLayout()
        header_layout.setSpacing(4)
        
        title = QtWidgets.QLabel("ComfyUI Integration Settings")
        title.setObjectName("header")
        header_layout.addWidget(title)
        
        version = QtWidgets.QLabel(f"<small>v{__version__}</small>")
        version.setStyleSheet(f"color: {FLAME_TEXT_DIM}; font-size: 11px;")
        header_layout.addWidget(version)
        
        container_layout.addLayout(header_layout)
        
        # Profile Management
        profile_layout = QtWidgets.QHBoxLayout()
        profile_layout.setSpacing(12)
        
        profile_label = QtWidgets.QLabel("Profile:")
        profile_label.setStyleSheet(f"color: {FLAME_TEXT_DIM};")
        profile_layout.addWidget(profile_label)
        
        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.addItem("Current")
        
        # Load available profiles
        profiles = list_profiles()
        for profile in profiles:
            self.profile_combo.addItem(profile)
        
        self.profile_combo.currentTextChanged.connect(self.on_profile_changed)
        profile_layout.addWidget(self.profile_combo)
        
        save_profile_btn = QtWidgets.QPushButton("Save Profile")
        save_profile_btn.clicked.connect(self.save_profile_dialog)
        profile_layout.addWidget(save_profile_btn)
        
        self.delete_profile_btn = QtWidgets.QPushButton("Delete")
        self.delete_profile_btn.clicked.connect(self.delete_profile_dialog)
        self.delete_profile_btn.setEnabled(False)  # Disabled for "Current"
        profile_layout.addWidget(self.delete_profile_btn)
        
        profile_layout.addStretch()
        
        container_layout.addLayout(profile_layout)
        container_layout.addSpacing(10)
        
        # Tabs
        tabs = QtWidgets.QTabWidget()
        
        # TAB 1: CONNECTION
        connection_tab = QtWidgets.QWidget()
        connection_layout = QtWidgets.QVBoxLayout(connection_tab)
        connection_layout.setSpacing(16)
        connection_layout.setContentsMargins(0, 20, 0, 0)
        
        conn_label = QtWidgets.QLabel("ComfyUI Server")
        conn_label.setObjectName("section")
        connection_layout.addWidget(conn_label)
        
        conn_form = QtWidgets.QFormLayout()
        conn_form.setSpacing(12)
        conn_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        conn_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        self.url_input = QtWidgets.QLineEdit(self.config['comfy_url'])
        self.url_input.setPlaceholderText("http://127.0.0.1")
        conn_form.addRow("URL:", self.url_input)
        
        self.port_input = QtWidgets.QSpinBox()
        self.port_input.setRange(1000, 65535)
        self.port_input.setValue(self.config['comfy_port'])
        conn_form.addRow("Port:", self.port_input)
        
        test_btn = QtWidgets.QPushButton("Test Connection")
        test_btn.clicked.connect(self.test_connection)
        test_btn.setFixedWidth(160)
        conn_form.addRow("", test_btn)
        
        connection_layout.addLayout(conn_form)
        connection_layout.addStretch()
        
        tabs.addTab(connection_tab, "Connection")
        
        # TAB 2: PATHS
        paths_tab = QtWidgets.QWidget()
        paths_layout = QtWidgets.QVBoxLayout(paths_tab)
        paths_layout.setSpacing(16)
        paths_layout.setContentsMargins(0, 20, 0, 0)
        
        paths_label = QtWidgets.QLabel("File Paths")
        paths_label.setObjectName("section")
        paths_layout.addWidget(paths_label)
        
        paths_form = QtWidgets.QFormLayout()
        paths_form.setSpacing(12)
        paths_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        paths_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        input_layout = QtWidgets.QHBoxLayout()
        self.input_dir = QtWidgets.QLineEdit(self.config['comfy_input_dir'])
        input_btn = QtWidgets.QPushButton("Browse")
        input_btn.clicked.connect(lambda: self.browse_directory(self.input_dir))
        input_btn.setFixedWidth(100)
        input_layout.addWidget(self.input_dir)
        input_layout.addWidget(input_btn)
        paths_form.addRow("ComfyUI Input:", input_layout)
        
        output_layout = QtWidgets.QHBoxLayout()
        self.output_dir = QtWidgets.QLineEdit(self.config['comfy_output_dir'])
        output_btn = QtWidgets.QPushButton("Browse")
        output_btn.clicked.connect(lambda: self.browse_directory(self.output_dir))
        output_btn.setFixedWidth(100)
        output_layout.addWidget(self.output_dir)
        output_layout.addWidget(output_btn)
        paths_form.addRow("ComfyUI Output:", output_layout)
        
        workflows_layout = QtWidgets.QHBoxLayout()
        self.workflows_dir = QtWidgets.QLineEdit(self.config['workflows_dir'])
        workflows_btn = QtWidgets.QPushButton("Browse")
        workflows_btn.clicked.connect(lambda: self.browse_directory(self.workflows_dir))
        workflows_btn.setFixedWidth(100)
        workflows_layout.addWidget(self.workflows_dir)
        workflows_layout.addWidget(workflows_btn)
        paths_form.addRow("Workflows:", workflows_layout)
        
        paths_layout.addLayout(paths_form)
        
        # Section Pipeline Paths (with tokens)
        paths_layout.addSpacing(20)
        
        pipeline_label = QtWidgets.QLabel("Pipeline Paths (optional — use Flame tokens)")
        pipeline_label.setObjectName("section")
        paths_layout.addWidget(pipeline_label)
        
        pipeline_hint = QtWidgets.QLabel(
            "If set, exports and results will be saved to these paths and symlinked into ComfyUI.\n"
            "Leave empty to use ComfyUI default folders directly."
        )
        pipeline_hint.setWordWrap(True)
        pipeline_hint.setStyleSheet(f"color: {FLAME_TEXT_DIM}; font-size: 11px; padding: 2px 0 6px 0;")
        paths_layout.addWidget(pipeline_hint)
        
        pipeline_form = QtWidgets.QFormLayout()
        pipeline_form.setSpacing(12)
        pipeline_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        pipeline_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        # Pipeline Export Path
        pipe_export_layout = QtWidgets.QHBoxLayout()
        self.pipeline_export = QtWidgets.QLineEdit(self.config.get('pipeline_export_path', ''))
        self.pipeline_export.setPlaceholderText("/mnt/server/<project>/comfyui/exports")
        pipe_export_browse = QtWidgets.QPushButton("Browse")
        pipe_export_browse.clicked.connect(lambda: self.browse_directory(self.pipeline_export))
        pipe_export_browse.setFixedWidth(100)
        pipe_export_token = FlameTokenButton(self.pipeline_export)
        pipe_export_layout.addWidget(self.pipeline_export)
        pipe_export_layout.addWidget(pipe_export_browse)
        pipe_export_layout.addWidget(pipe_export_token)
        pipeline_form.addRow("Export Path:", pipe_export_layout)
        
        # Pipeline Result Path
        pipe_result_layout = QtWidgets.QHBoxLayout()
        self.pipeline_result = QtWidgets.QLineEdit(self.config.get('pipeline_result_path', ''))
        self.pipeline_result.setPlaceholderText("/mnt/server/<project>/comfyui/results")
        pipe_result_browse = QtWidgets.QPushButton("Browse")
        pipe_result_browse.clicked.connect(lambda: self.browse_directory(self.pipeline_result))
        pipe_result_browse.setFixedWidth(100)
        pipe_result_token = FlameTokenButton(self.pipeline_result)
        pipe_result_layout.addWidget(self.pipeline_result)
        pipe_result_layout.addWidget(pipe_result_browse)
        pipe_result_layout.addWidget(pipe_result_token)
        pipeline_form.addRow("Result Path:", pipe_result_layout)
        
        paths_layout.addLayout(pipeline_form)
        
        # Section Connection Mode
        paths_layout.addSpacing(20)
        
        connection_label = QtWidgets.QLabel("Connection Mode")
        connection_label.setObjectName("section")
        paths_layout.addWidget(connection_label)
        
        connection_form = QtWidgets.QFormLayout()
        connection_form.setSpacing(12)
        connection_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        connection_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        self.connection_mode = QtWidgets.QComboBox()
        self.connection_mode.addItem("Local", "local")
        self.connection_mode.addItem("Remote (SSH)", "remote_ssh")
        self.connection_mode.addItem("Network Share", "network_share")
        
        # Select current mode
        current_mode = self.config.get('connection_mode', 'local')
        index = self.connection_mode.findData(current_mode)
        if index >= 0:
            self.connection_mode.setCurrentIndex(index)
        
        self.connection_mode.currentIndexChanged.connect(self.on_connection_mode_changed)
        connection_form.addRow("Mode:", self.connection_mode)
        
        # SSH fields (visible only in remote_ssh mode)
        self.remote_ssh_host = QtWidgets.QLineEdit(self.config.get('remote_ssh_host', ''))
        self.remote_ssh_host.setPlaceholderText("user@host or IP")
        self.ssh_host_row = connection_form.addRow("SSH Host:", self.remote_ssh_host)
        
        self.remote_path = QtWidgets.QLineEdit(self.config.get('remote_path', ''))
        self.remote_path.setPlaceholderText("/path/on/remote/server")
        self.remote_path_row = connection_form.addRow("Remote Path:", self.remote_path)
        
        paths_layout.addLayout(connection_form)
        
        # Update field visibility based on mode
        self.on_connection_mode_changed()
        
        paths_layout.addStretch()
        
        tabs.addTab(paths_tab, "Paths")
        
        # TAB 3: EXPORT
        export_tab = QtWidgets.QWidget()
        export_layout = QtWidgets.QVBoxLayout(export_tab)
        export_layout.setSpacing(16)
        export_layout.setContentsMargins(0, 20, 0, 0)
        
        export_label = QtWidgets.QLabel("Flame Export Format")
        export_label.setObjectName("section")
        export_layout.addWidget(export_label)
        
        export_hint = QtWidgets.QLabel(
            "Select the format used when exporting clips from Flame to ComfyUI.\n"
            "This can also be changed per-export in the Frame Range dialog."
        )
        export_hint.setWordWrap(True)
        export_hint.setStyleSheet(f"color: {FLAME_TEXT_DIM}; font-size: 11px; padding: 2px 0 6px 0;")
        export_layout.addWidget(export_hint)
        
        export_form = QtWidgets.QFormLayout()
        export_form.setSpacing(12)
        export_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        export_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        # Export Format dropdown
        self.export_format = QtWidgets.QComboBox()
        for fmt_name in EXPORT_PRESETS.keys():
            self.export_format.addItem(fmt_name)
        self.export_format.addItem("Custom preset...")
        
        current_format = self.config.get('export_format', 'PNG 8-bit')
        idx = self.export_format.findText(current_format)
        if idx >= 0:
            self.export_format.setCurrentIndex(idx)
        
        self.export_format.setMinimumHeight(28)
        self.export_format.setStyleSheet(f"""
            QComboBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {FLAME_BG};
                color: {FLAME_TEXT};
                selection-background-color: {FLAME_BLUE};
            }}
        """)
        export_form.addRow("Format:", self.export_format)
        
        # Custom preset path (hidden unless "Custom preset..." selected)
        self.custom_preset_layout = QtWidgets.QHBoxLayout()
        self.preset_path = QtWidgets.QLineEdit(self.config.get('preset_path', ''))
        self.preset_path.setPlaceholderText("Path to custom export preset XML")
        preset_btn = QtWidgets.QPushButton("Browse")
        preset_btn.clicked.connect(lambda: self.browse_file(self.preset_path, "XML Files (*.xml)"))
        preset_btn.setFixedWidth(100)
        self.custom_preset_layout.addWidget(self.preset_path)
        self.custom_preset_layout.addWidget(preset_btn)
        
        self.custom_preset_widget = QtWidgets.QWidget()
        self.custom_preset_widget.setLayout(self.custom_preset_layout)
        self.custom_preset_widget.setVisible(current_format not in EXPORT_PRESETS)
        
        self.export_format.currentTextChanged.connect(self._on_export_format_changed)
        export_form.addRow("", self.custom_preset_widget)
        
        export_layout.addLayout(export_form)
        export_layout.addStretch()
        
        tabs.addTab(export_tab, "Export")
        
        # TAB 4: BEHAVIOR
        behavior_tab = QtWidgets.QWidget()
        behavior_layout = QtWidgets.QVBoxLayout(behavior_tab)
        behavior_layout.setSpacing(16)
        behavior_layout.setContentsMargins(0, 20, 0, 0)
        
        behavior_label = QtWidgets.QLabel("Workflow Behavior")
        behavior_label.setObjectName("section")
        behavior_layout.addWidget(behavior_label)
        
        behavior_form = QtWidgets.QFormLayout()
        behavior_form.setSpacing(12)
        behavior_form.setLabelAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        behavior_form.setFormAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        self.timeout_spin = QtWidgets.QSpinBox()
        self.timeout_spin.setRange(30, 3600)
        self.timeout_spin.setValue(self.config['timeout'])
        self.timeout_spin.setSuffix(" seconds")
        behavior_form.addRow("Timeout:", self.timeout_spin)
        
        self.auto_import_check = QtWidgets.QCheckBox("Auto-import results into Flame")
        self.auto_import_check.setChecked(self.config['auto_import'])
        behavior_form.addRow("", self.auto_import_check)

        self.import_dest_combo = QtWidgets.QComboBox()
        self.import_dest_combo.addItems([
            'Batch Schematic  (reel "ComfyUI Results")',
            'Library  ("ComfyUI" / date folder)',
        ])
        idx = 0 if self.config.get('import_destination', 'batch') == 'batch' else 1
        self.import_dest_combo.setCurrentIndex(idx)
        behavior_form.addRow("Import to:", self.import_dest_combo)

        self.open_browser_check = QtWidgets.QCheckBox("Open browser in manual mode")
        self.open_browser_check.setChecked(self.config['open_browser_manual'])
        behavior_form.addRow("", self.open_browser_check)
        
        self.notifications_check = QtWidgets.QCheckBox("Show Flame notifications")
        self.notifications_check.setChecked(self.config['show_notifications'])
        behavior_form.addRow("", self.notifications_check)
        
        behavior_layout.addLayout(behavior_form)
        behavior_layout.addStretch()
        
        tabs.addTab(behavior_tab, "Behavior")
        
        container_layout.addWidget(tabs)
        
        # Bottom buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(12)
        
        reset_btn = QtWidgets.QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_defaults)
        reset_btn.setFixedWidth(160)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setFixedWidth(120)
        button_layout.addWidget(cancel_btn)
        
        save_btn = QtWidgets.QPushButton("Save")
        save_btn.clicked.connect(self.save_and_accept)
        save_btn.setObjectName("primary")
        save_btn.setFixedWidth(120)
        button_layout.addWidget(save_btn)
        
        container_layout.addLayout(button_layout)
        
        main_layout.addWidget(container)
    
    def browse_directory(self, line_edit):
        """Open folder chooser dialog"""
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select Directory", line_edit.text()
        )
        if directory:
            line_edit.setText(directory)
    
    def _on_export_format_changed(self, text):
        """Show/hide custom preset path based on selection"""
        self.custom_preset_widget.setVisible(text == "Custom preset...")
    
    def browse_file(self, line_edit, file_filter):
        """Open file chooser dialog"""
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select File", line_edit.text(), file_filter
        )
        if filename:
            line_edit.setText(filename)
    
    def test_connection(self):
        """Test connection to ComfyUI"""
        url = f"{self.url_input.text()}:{self.port_input.value()}"
        try:
            import urllib.request
            response = urllib.request.urlopen(f"{url}/system_stats", timeout=5)
            if response.status == 200:
                msg = QtWidgets.QMessageBox(self)
                msg.setWindowTitle("Connection Test")
                msg.setText("✓ Connection successful!")
                msg.setInformativeText(f"ComfyUI is running at:\n{url}")
                msg.setIcon(QtWidgets.QMessageBox.Information)
                msg.exec_()
            else:
                msg = QtWidgets.QMessageBox(self)
                msg.setWindowTitle("Connection Test")
                msg.setText(f"✗ Unexpected response code: {response.status}")
                msg.setIcon(QtWidgets.QMessageBox.Warning)
                msg.exec_()
        except Exception as e:
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("Connection Test")
            msg.setText("✗ Connection failed")
            msg.setInformativeText(f"{str(e)}\n\nMake sure ComfyUI is running.")
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.exec_()
    
    def on_profile_changed(self, profile_name):
        """When profile selection changes in dropdown"""
        if profile_name == "Current":
            self.delete_profile_btn.setEnabled(False)
            return
        
        self.delete_profile_btn.setEnabled(True)
        
        # Load profile
        config = load_profile(profile_name)
        if config:
            self.config = config
            self.load_config_to_ui()
    
    def load_config_to_ui(self):
        """Load config into UI fields"""
        self.url_input.setText(self.config['comfy_url'])
        self.port_input.setValue(self.config['comfy_port'])
        self.input_dir.setText(self.config['comfy_input_dir'])
        self.output_dir.setText(self.config['comfy_output_dir'])
        self.workflows_dir.setText(self.config['workflows_dir'])
        
        # Export format
        current_format = self.config.get('export_format', 'PNG 8-bit')
        idx = self.export_format.findText(current_format)
        if idx >= 0:
            self.export_format.setCurrentIndex(idx)
        self.preset_path.setText(self.config.get('preset_path', ''))
        
        self.timeout_spin.setValue(self.config['timeout'])
        self.auto_import_check.setChecked(self.config['auto_import'])
        self.import_dest_combo.setCurrentIndex(
            0 if self.config.get('import_destination', 'batch') == 'batch' else 1
        )
        self.open_browser_check.setChecked(self.config['open_browser_manual'])
        self.notifications_check.setChecked(self.config['show_notifications'])
        
        # Connection mode
        current_mode = self.config.get('connection_mode', 'local')
        index = self.connection_mode.findData(current_mode)
        if index >= 0:
            self.connection_mode.setCurrentIndex(index)
        
        self.remote_ssh_host.setText(self.config.get('remote_ssh_host', ''))
        self.remote_path.setText(self.config.get('remote_path', ''))
    
    def on_connection_mode_changed(self):
        """Affiche/masque les champs selon le mode de connexion"""
        mode = self.connection_mode.currentData()
        
        # SSH fields visible only in remote_ssh mode
        is_remote_ssh = (mode == 'remote_ssh')
        self.remote_ssh_host.setVisible(is_remote_ssh)
        self.remote_path.setVisible(is_remote_ssh)
        
        # Masquer aussi les labels (rows)
        # Note: Les labels sont dans le FormLayout, on ne peut pas les masquer facilement
        # Solution: enable/disable instead of hiding
        self.remote_ssh_host.setEnabled(is_remote_ssh)
        self.remote_path.setEnabled(is_remote_ssh)
    
    def save_profile_dialog(self):
        """Dialog to save a profile"""
        current_profile = self.profile_combo.currentText()
        
        # Ask for profile name
        profile_name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Profile",
            "Enter profile name:",
            QtWidgets.QLineEdit.Normal,
            current_profile if current_profile != "Current" else ""
        )
        
        if ok and profile_name:
            # Save current UI config
            config = {
                'comfy_url': self.url_input.text(),
                'comfy_port': self.port_input.value(),
                'comfy_input_dir': self.input_dir.text(),
                'comfy_output_dir': self.output_dir.text(),
                'workflows_dir': self.workflows_dir.text(),
                'export_format': self.export_format.currentText(),
                'preset_path': self.preset_path.text() if self.export_format.currentText() == "Custom preset..." else get_preset_path_for_format(self.export_format.currentText()),
                'presets_dir': self.config.get('presets_dir', DEFAULT_CONFIG['presets_dir']),
                'timeout': self.timeout_spin.value(),
                'auto_import': self.auto_import_check.isChecked(),
                'open_browser_manual': self.open_browser_check.isChecked(),
                'show_notifications': self.notifications_check.isChecked(),
                'connection_mode': self.connection_mode.currentData(),
                'remote_ssh_host': self.remote_ssh_host.text(),
                'remote_path': self.remote_path.text(),
                'favorite_workflows': self.config.get('favorite_workflows', []),
            }
            
            if save_profile(profile_name, config):
                # Refresh dropdown
                self.profile_combo.blockSignals(True)
                self.profile_combo.clear()
                self.profile_combo.addItem("Current")
                
                profiles = list_profiles()
                for profile in profiles:
                    self.profile_combo.addItem(profile)
                
                # Select saved profile
                index = self.profile_combo.findText(profile_name)
                if index >= 0:
                    self.profile_combo.setCurrentIndex(index)
                
                self.profile_combo.blockSignals(False)
                
                msg = QtWidgets.QMessageBox(self)
                msg.setWindowTitle("Profile Saved")
                msg.setText(f"Profile '{profile_name}' saved successfully!")
                msg.setIcon(QtWidgets.QMessageBox.Information)
                msg.exec_()
    
    def delete_profile_dialog(self):
        """Dialog to delete a profile"""
        profile_name = self.profile_combo.currentText()
        
        if profile_name == "Current":
            return
        
        reply = QtWidgets.QMessageBox.question(
            self, "Delete Profile",
            f"Are you sure you want to delete profile '{profile_name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            if delete_profile(profile_name):
                # Refresh dropdown
                self.profile_combo.blockSignals(True)
                self.profile_combo.clear()
                self.profile_combo.addItem("Current")
                
                profiles = list_profiles()
                for profile in profiles:
                    self.profile_combo.addItem(profile)
                
                self.profile_combo.setCurrentIndex(0)  # Return to "Current"
                self.profile_combo.blockSignals(False)
                self.delete_profile_btn.setEnabled(False)
                
                msg = QtWidgets.QMessageBox(self)
                msg.setWindowTitle("Profile Deleted")
                msg.setText(f"Profile '{profile_name}' deleted successfully!")
                msg.setIcon(QtWidgets.QMessageBox.Information)
                msg.exec_()
    
    def reset_defaults(self):
        """Restore les valeurs par defaut"""
        reply = QtWidgets.QMessageBox.question(
            self, "Reset to Defaults",
            "Are you sure you want to reset all settings to default values?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.config = DEFAULT_CONFIG.copy()
            self.load_config_to_ui()
    
    def save_and_accept(self):
        """Save config and close dialog"""
        self.config['comfy_url'] = self.url_input.text()
        self.config['comfy_port'] = self.port_input.value()
        self.config['comfy_input_dir'] = self.input_dir.text()
        self.config['comfy_output_dir'] = self.output_dir.text()
        self.config['workflows_dir'] = self.workflows_dir.text()
        self.config['export_format'] = self.export_format.currentText()
        self.config['preset_path'] = self.preset_path.text() if self.export_format.currentText() == "Custom preset..." else get_preset_path_for_format(self.export_format.currentText())
        self.config['timeout'] = self.timeout_spin.value()
        self.config['auto_import'] = self.auto_import_check.isChecked()
        self.config['import_destination'] = 'batch' if self.import_dest_combo.currentIndex() == 0 else 'library'
        self.config['open_browser_manual'] = self.open_browser_check.isChecked()
        self.config['show_notifications'] = self.notifications_check.isChecked()
        self.config['connection_mode'] = self.connection_mode.currentData()
        self.config['remote_ssh_host'] = self.remote_ssh_host.text()
        self.config['remote_path'] = self.remote_path.text()
        self.config['pipeline_export_path'] = self.pipeline_export.text().strip()
        self.config['pipeline_result_path'] = self.pipeline_result.text().strip()
        
        if save_config(self.config):
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("Settings Saved")
            msg.setText("Settings saved successfully!")
            msg.setInformativeText("Restart Flame for all changes to take effect.")
            msg.setIcon(QtWidgets.QMessageBox.Information)
            msg.exec_()
            self.accept()
        else:
            msg = QtWidgets.QMessageBox(self)
            msg.setWindowTitle("Save Error")
            msg.setText("Failed to save settings.")
            msg.setIcon(QtWidgets.QMessageBox.Warning)
            msg.exec_()


def show_settings_dialog():
    """Show settings dialog"""
    dialog = ComfyUISettingsDialog()
    result = dialog.exec_()
    
    if result == QtWidgets.QDialog.Accepted:
        # Reload global config
        global CONFIG, COMFY_URL, COMFY_INPUT_DIR, COMFY_OUTPUT_DIR, PRESET_PATH, WORKFLOWS_DIR, FLAME_NOTIFICATION_FILE
        CONFIG = load_config()
        COMFY_URL = f"{CONFIG['comfy_url']}:{CONFIG['comfy_port']}"
        COMFY_INPUT_DIR = CONFIG['comfy_input_dir']
        COMFY_OUTPUT_DIR = CONFIG['comfy_output_dir']
        PRESET_PATH = get_preset_path_for_format(CONFIG.get('export_format', 'PNG 8-bit'))
        WORKFLOWS_DIR = CONFIG['workflows_dir']
        
        # Recalculate notification file
        FLAME_NOTIFICATION_FILE = os.path.join(COMFY_OUTPUT_DIR, 'notification.json')
        
        log("Configuration reloaded")
        log(f"  Input Dir: {COMFY_INPUT_DIR}")
        log(f"  Output Dir: {COMFY_OUTPUT_DIR}")
        return True
    
    return False


# WorkflowManagerDialog - Logik Portal Style

class WorkflowManagerDialog(QtWidgets.QDialog):
    """Workflow Manager - Flame Style"""
    
    def __init__(self, selection=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("")
        self.setMinimumSize(1100, 700)
        self.config = load_config()
        self.workflows = get_available_workflows()
        self.selection = selection
        self.selected_workflow = None
        self.setup_ui()
        self._apply_style()
        self.populate_table()
    
    def _apply_style(self):
        """Apply Flame style with table-specific additions"""
        table_extra = f"""
            QTableWidget {{
                background-color: {FLAME_BG};
                color: {FLAME_TEXT};
                border: none;
                gridline-color: rgb(50, 50, 50);
                selection-background-color: {FLAME_MID_BG};
                selection-color: {FLAME_TEXT};
                outline: none;
            }}
            QTableWidget::item {{
                padding: 8px;
                border-bottom: 1px solid rgb(50, 50, 50);
                outline: none;
            }}
            QTableWidget::item:hover {{
                background-color: {FLAME_MID_BG};
            }}
            QTableWidget::item:selected {{
                background-color: {FLAME_MID_BG};
                outline: none;
                border: none;
            }}
            QTableWidget::item:focus {{
                outline: none;
                border-bottom: 1px solid rgb(50, 50, 50);
            }}
            QHeaderView::section {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT_DIM};
                padding: 10px 8px;
                border: none;
                border-right: 1px solid rgb(50, 50, 50);
                border-bottom: 1px solid rgb(50, 50, 50);
                font-weight: 500;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QHeaderView::section:hover {{
                background-color: {FLAME_WIDGET_HOVER};
                color: {FLAME_TEXT};
            }}
            QTextEdit {{
                background-color: {FLAME_INPUT_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_INPUT_BG};
                padding: 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QPushButton#favorite {{
                color: #ffd700;
            }}
        """
        self.setStyleSheet(get_flame_stylesheet() + table_extra)
    
    def setup_ui(self):
        """Interface style Logik Portal"""
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title = QtWidgets.QLabel(f"ComfyUI Workflow Manager v{__version__}")
        title.setObjectName("title")
        main_layout.addWidget(title)
        
        main_layout.addSpacing(20)
        
        # Section label
        section_label = QtWidgets.QLabel("Available Workflows")
        section_label.setObjectName("section")
        main_layout.addWidget(section_label)
        
        # Table
        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Name", "Format", "Modified", "Favorite"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QtWidgets.QHeaderView.Fixed)
        self.table.setColumnWidth(3, 80)
        self.table.setSelectionBehavior(QtWidgets.QTableWidget.SelectRows)
        self.table.setSelectionMode(QtWidgets.QTableWidget.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        main_layout.addWidget(self.table)
        
        main_layout.addSpacing(12)
        
        # Buttons row
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.setSpacing(12)
        
        refresh_btn = QtWidgets.QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_workflows)
        button_layout.addWidget(refresh_btn)
        
        self.favorite_btn = QtWidgets.QPushButton("★ Toggle Favorite")
        self.favorite_btn.setObjectName("favorite")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        self.favorite_btn.setEnabled(False)
        button_layout.addWidget(self.favorite_btn)
        
        button_layout.addStretch()
        
        self.load_btn = QtWidgets.QPushButton("Load Workflow")
        self.load_btn.setObjectName("primary")
        self.load_btn.clicked.connect(self.load_workflow)
        self.load_btn.setEnabled(False)
        button_layout.addWidget(self.load_btn)
        
        main_layout.addLayout(button_layout)
        
        main_layout.addSpacing(12)
        
        # Search
        search_layout = QtWidgets.QHBoxLayout()
        search_label = QtWidgets.QLabel("Search")
        search_label.setStyleSheet(f"color: {FLAME_TEXT_DIM};")
        self.search_input = QtWidgets.QLineEdit()
        self.search_input.textChanged.connect(self.filter_table)
        search_layout.addWidget(search_label)
        search_layout.addWidget(self.search_input)
        main_layout.addLayout(search_layout)
        
        main_layout.addSpacing(20)
        
        # Description section
        desc_label = QtWidgets.QLabel("Workflow Description")
        desc_label.setObjectName("section")
        main_layout.addWidget(desc_label)
        
        self.description_text = QtWidgets.QTextEdit()
        self.description_text.setReadOnly(True)
        self.description_text.setMaximumHeight(150)
        main_layout.addWidget(self.description_text)
        
        main_layout.addSpacing(20)
        
        # Done button
        done_layout = QtWidgets.QHBoxLayout()
        done_layout.addStretch()
        done_btn = QtWidgets.QPushButton("Done")
        done_btn.clicked.connect(self.close)
        done_layout.addWidget(done_btn)
        main_layout.addLayout(done_layout)
    
    def populate_table(self):
        """Remplit la table"""
        self.table.setRowCount(0)
        favorites = self.config.get('favorite_workflows', [])
        
        for workflow_name, workflow_path in self.workflows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Name
            name_item = QtWidgets.QTableWidgetItem(workflow_name)
            name_item.setData(QtCore.Qt.UserRole, (workflow_name, workflow_path))
            if workflow_name in favorites:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
            self.table.setItem(row, 0, name_item)
            
            # Format
            try:
                _, is_api = load_workflow_json(workflow_path)
                format_str = "API (Auto)" if is_api else "Normal (Manual)"
            except:
                format_str = "Unknown"
            format_item = QtWidgets.QTableWidgetItem(format_str)
            self.table.setItem(row, 1, format_item)
            
            # Modified
            try:
                import datetime
                mtime = os.path.getmtime(workflow_path)
                modified = datetime.datetime.fromtimestamp(mtime).strftime("%Y.%m.%d")
            except:
                modified = "Unknown"
            modified_item = QtWidgets.QTableWidgetItem(modified)
            self.table.setItem(row, 2, modified_item)
            
            # Favorite indicator
            fav_item = QtWidgets.QTableWidgetItem("★" if workflow_name in favorites else "")
            fav_item.setTextAlignment(QtCore.Qt.AlignCenter)
            self.table.setItem(row, 3, fav_item)
    
    def filter_table(self, text):
        """Filtre la table"""
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            if text.lower() in name_item.text().lower():
                self.table.setRowHidden(row, False)
            else:
                self.table.setRowHidden(row, True)
    
    def on_selection_changed(self):
        """Selection changée"""
        selected = self.table.selectedItems()
        if not selected:
            self.load_btn.setEnabled(False)
            self.favorite_btn.setEnabled(False)
            self.description_text.clear()
            self.selected_workflow = None
            return
        
        name_item = self.table.item(selected[0].row(), 0)
        workflow_name, workflow_path = name_item.data(QtCore.Qt.UserRole)
        self.selected_workflow = (workflow_name, workflow_path)
        
        self.load_btn.setEnabled(True)
        self.favorite_btn.setEnabled(True)
        
        # Description
        desc = f"Workflow: {workflow_name}\n"
        desc += f"Path: {workflow_path}\n\n"
        desc += "ComfyUI workflow for AI-powered image processing."
        self.description_text.setPlainText(desc)
    
    def toggle_favorite(self):
        """Toggle favori"""
        if not self.selected_workflow:
            return
        
        workflow_name, _ = self.selected_workflow
        favorites = self.config.get('favorite_workflows', [])
        
        if workflow_name in favorites:
            favorites.remove(workflow_name)
        else:
            favorites.append(workflow_name)
        
        self.config['favorite_workflows'] = favorites
        save_config(self.config)
        
        # Reload global config
        global CONFIG
        CONFIG = load_config()
        
        # Refresh table
        self.populate_table()
    
    def refresh_workflows(self):
        """Refresh workflows"""
        self.workflows = get_available_workflows()
        self.populate_table()
        log("Workflows refreshed")
    
    def load_workflow(self):
        """Load workflow"""
        if not self.selected_workflow:
            return
        
        workflow_name, workflow_path = self.selected_workflow
        
        if self.selection:
            workflow, is_api = load_workflow_json(workflow_path)
            mode = "auto" if is_api else "manual"
            self.close()
            export_and_load_workflow(self.selection, workflow_name, workflow_path, mode=mode)
        else:
            self.accept()


def show_workflow_manager(selection=None):
    """Show workflow manager dialog"""
    dialog = WorkflowManagerDialog(selection=selection)
    result = dialog.exec_()
    
    if not selection and result == QtWidgets.QDialog.Accepted and dialog.selected_workflow:
        return dialog.selected_workflow
    
    return None, None


def get_available_workflows():
    """
    Scan workflows folder and return list of available workflows
    
    Returns:
        list: List of tuples (display_name, file_path)
    """
    workflows = []
    
    if not os.path.exists(WORKFLOWS_DIR):
        os.makedirs(WORKFLOWS_DIR)
        log(f"Workflows folder created: {WORKFLOWS_DIR}")
        return workflows
    
    # Scan all JSON files
    for filename in os.listdir(WORKFLOWS_DIR):
        if filename.endswith('.json'):
            workflow_path = os.path.join(WORKFLOWS_DIR, filename)
            
            # Display name = filename without extension
            display_name = filename.replace('.json', '')
            
            workflows.append((display_name, workflow_path))
    
    workflows.sort()  # Alphabetical sort
    return workflows


def load_workflow_json(workflow_path):
    """
    Load a workflow JSON and auto-detect its format
    
    Returns:
        tuple: (workflow_dict, is_api_format)
    """
    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        
        # Detect format
        # API format: structure plate avec des IDs numeriques comme cles
        # Normal format: contains "nodes", "links", "groups", etc.
        
        is_api_format = False
        
        if isinstance(workflow, dict):
            # If we find "nodes" it's the normal format
            if "nodes" in workflow:
                log("Format detected: Normal (interface)")
                is_api_format = False
            else:
                # Sinon c'est probablement le format API
                log("Format detected: API")
                is_api_format = True
        
        return workflow, is_api_format
        
    except Exception as e:
        log(f"Error loading workflow: {e}")
        return None, False


def convert_normal_to_api_format(workflow):
    """
    Convertit un workflow format normal en format API
    
    Returns:
        dict: Workflow au format API
    """
    log("Converting normal workflow to API format...")
    
    api_workflow = {}
    
    if "nodes" not in workflow:
        log("ERROR: Unrecognized workflow format")
        return None
    
    # Iterate all nodes
    for node in workflow["nodes"]:
        node_id = str(node["id"])
        
        # Create API entry for this node
        api_workflow[node_id] = {
            "class_type": node["type"],
            "inputs": {}
        }
        
        # Copy widget inputs from node
        if "widgets_values" in node and node["widgets_values"]:
            # Widgets are the input values
            # We need to map widgets to input names
            # This is complex as it depends on node type
            
            # For LoadImage specifically
            if node["type"] == "LoadImage" and len(node["widgets_values"]) > 0:
                api_workflow[node_id]["inputs"]["image"] = node["widgets_values"][0]
    
    # Parse links to connect nodes
    if "links" in workflow:
        for link in workflow["links"]:
            # Link format: [id, source_node, source_slot, target_node, target_slot, type]
            if len(link) >= 5:
                target_node = str(link[3])
                target_slot = link[4]
                source_node = str(link[1])
                source_slot = link[2]
                
                # Add connection
                if target_node in api_workflow:
                    # Slot name depends on node type - using index
                    slot_name = f"input_{target_slot}"
                    api_workflow[target_node]["inputs"][slot_name] = [source_node, source_slot]
    
    log(f"Workflow converted: {len(api_workflow)} nodes")
    return api_workflow


def count_flameload_nodes(workflow, is_api_format):
    """
    Count FlameLoad nodes in a workflow.
    Returns list of (node_id, title) tuples.
    """
    flame_loads = []
    
    if is_api_format:
        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict) and node_data.get('class_type') == 'FlameLoad':
                title = node_data.get('_meta', {}).get('title', 'FlameLoad')
                flame_loads.append((node_id, title))
    else:
        if "nodes" in workflow:
            for node in workflow["nodes"]:
                if node.get("type") == "FlameLoad":
                    title = node.get("title", node.get("properties", {}).get("title", "FlameLoad"))
                    flame_loads.append((str(node["id"]), title))
    
    return flame_loads


def get_text_nodes(workflow, is_api_format):
    """
    Find text/prompt nodes in workflow (CLIPTextEncode, etc.)
    Returns list of (node_id, title, current_text) tuples.
    """
    text_nodes = []
    text_types = ['CLIPTextEncode', 'CLIPTextEncodeFlux', 'easy positive', 'easy negative']
    
    if is_api_format:
        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict) and node_data.get('class_type') in text_types:
                title = node_data.get('_meta', {}).get('title', node_data.get('class_type', 'Prompt'))
                current_text = node_data.get('inputs', {}).get('text', '')
                # Skip nodes where text input is a link (list), not a string
                if isinstance(current_text, str):
                    text_nodes.append((node_id, title, current_text))
    else:
        if "nodes" in workflow:
            for node in workflow["nodes"]:
                if node.get("type") in text_types:
                    title = node.get("title", node.get("type", "Prompt"))
                    widgets = node.get("widgets_values", [])
                    current_text = widgets[0] if widgets and isinstance(widgets[0], str) else ""
                    text_nodes.append((str(node["id"]), title, current_text))
    
    return text_nodes


class MultiClipAssignDialog(QtWidgets.QDialog):
    """Dialog to assign multiple clips to FlameLoad nodes — Flame Style"""
    
    def __init__(self, clip_names, flameload_nodes, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assign Clips to Workflow Inputs")
        self.setMinimumWidth(550)
        self.assignments = {}
        self.setStyleSheet(get_flame_stylesheet())
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        
        # Header
        header = QtWidgets.QLabel(f"Workflow has {len(flameload_nodes)} input(s). Assign each clip:")
        header.setObjectName("header")
        layout.addWidget(header)
        
        layout.addSpacing(8)
        
        # Assignment combos
        self.combos = {}
        for i, (node_id, title) in enumerate(flameload_nodes):
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(12)
            
            label = QtWidgets.QLabel(f"{title}:")
            label.setMinimumWidth(180)
            row.addWidget(label)
            
            combo = QtWidgets.QComboBox()
            combo.setMinimumWidth(280)
            combo.setMinimumHeight(28)
            for name in clip_names:
                combo.addItem(name)
            if i < len(clip_names):
                combo.setCurrentIndex(i)
            self.combos[node_id] = combo
            row.addWidget(combo)
            
            layout.addLayout(row)
        
        layout.addStretch()
        layout.addSpacing(8)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setMinimumSize(110, 28)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QtWidgets.QPushButton("OK")
        ok_btn.setObjectName("primary")
        ok_btn.setMinimumSize(110, 28)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def get_assignments(self):
        """Returns dict: node_id -> clip_index"""
        result = {}
        for node_id, combo in self.combos.items():
            result[node_id] = combo.currentIndex()
        return result


class PromptDialog(QtWidgets.QDialog):
    """Dialog to edit prompts before sending workflow to ComfyUI — Flame Style"""
    
    def __init__(self, text_nodes, workflow_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Edit Prompts — {workflow_name}")
        self.setMinimumWidth(620)
        self.setMinimumHeight(400)
        self.text_edits = {}
        self.setStyleSheet(get_flame_stylesheet())
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        
        # Header
        header = QtWidgets.QLabel("Edit prompt text before executing workflow:")
        header.setObjectName("header")
        layout.addWidget(header)
        
        layout.addSpacing(4)
        
        # Output mode selection
        mode_label = QtWidgets.QLabel("Output Mode:")
        mode_label.setObjectName("section")
        layout.addWidget(mode_label)
        
        self.output_mode = QtWidgets.QComboBox()
        self.output_mode.addItem("Matte (grayscale)", "matte")
        self.output_mode.addItem("Video with Alpha (RGBA)", "alpha")
        self.output_mode.setMinimumHeight(28)
        self.output_mode.setStyleSheet(f"""
            QComboBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                selection-background-color: {FLAME_BLUE};
                border: 1px solid {FLAME_BORDER};
            }}
        """)
        layout.addWidget(self.output_mode)
        
        layout.addSpacing(8)
        
        # Key frame selection (which frame SAM3 uses to generate the mask)
        frame_label = QtWidgets.QLabel("Key Frame (for mask generation):")
        frame_label.setObjectName("section")
        layout.addWidget(frame_label)
        
        self.key_frame = QtWidgets.QSpinBox()
        self.key_frame.setRange(0, 100000)
        self.key_frame.setValue(0)
        self.key_frame.setMinimumHeight(28)
        self.key_frame.setToolTip(
            "Frame index used by SAM3 to generate the mask and by MatAnyone as the reference. "
            "Use a frame where the object is clearly visible (e.g. not motion-blurred)."
        )
        self.key_frame.setStyleSheet(f"""
            QSpinBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {FLAME_WIDGET_BG};
                border: none;
                width: 20px;
            }}
        """)
        layout.addWidget(self.key_frame)
        
        layout.addSpacing(8)
        
        # Colour space selection (written into ProRes output metadata for alpha video)
        cs_label = QtWidgets.QLabel("Colour Space (alpha output):")
        cs_label.setObjectName("section")
        layout.addWidget(cs_label)
        
        self.colour_space = QtWidgets.QComboBox()
        self.colour_space.addItem("Rec.709", "bt709")
        self.colour_space.addItem("sRGB", "srgb")
        self.colour_space.addItem("P3-D65", "p3")
        self.colour_space.setMinimumHeight(28)
        self.colour_space.setStyleSheet(f"""
            QComboBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                selection-background-color: {FLAME_BLUE};
                border: 1px solid {FLAME_BORDER};
            }}
        """)
        self.colour_space.setToolTip(
            "Colour space written into ProRes 4444 metadata. Must match the source clip "
            "so Flame imports the alpha video with correct colours."
        )
        layout.addWidget(self.colour_space)
        
        layout.addSpacing(8)
        
        # Mask quality parameters (SAM3_Detect threshold/refine + MatAnyone2 edge dilation/erosion)
        quality_label = QtWidgets.QLabel("Mask Quality:")
        quality_label.setObjectName("section")
        layout.addWidget(quality_label)
        
        # threshold — SAM3_Detect confidence cutoff
        thr_label = QtWidgets.QLabel("SAM3 Threshold (0.1-1.0):")
        thr_label.setObjectName("hint")
        layout.addWidget(thr_label)
        self.sam3_threshold = QtWidgets.QDoubleSpinBox()
        self.sam3_threshold.setRange(0.05, 1.0)
        self.sam3_threshold.setSingleStep(0.05)
        self.sam3_threshold.setValue(0.5)
        self.sam3_threshold.setMinimumHeight(28)
        self.sam3_threshold.setToolTip(
            "SAM3 confidence cutoff. Higher (0.6-0.7) = mask takes less junk/background, "
            "but may lose parts of the object. Lower (0.3-0.4) = catches more, "
            "but riskier edges."
        )
        self.sam3_threshold.setStyleSheet(f"""
            QDoubleSpinBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
                background-color: {FLAME_WIDGET_BG};
                border: none;
                width: 20px;
            }}
        """)
        layout.addWidget(self.sam3_threshold)
        
        # refine_iterations — SAM3_Detect edge refinement passes
        ref_label = QtWidgets.QLabel("SAM3 Edge Refine (iterations):")
        ref_label.setObjectName("hint")
        layout.addWidget(ref_label)
        self.sam3_refine = QtWidgets.QSpinBox()
        self.sam3_refine.setRange(0, 10)
        self.sam3_refine.setValue(2)
        self.sam3_refine.setMinimumHeight(28)
        self.sam3_refine.setToolTip(
            "Edge refinement passes. 0 = fast/coarse, 3-4 = cleaner edges "
            "(important for hair/fur). Too many can over-smooth thin details."
        )
        self.sam3_refine.setStyleSheet(f"""
            QSpinBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {FLAME_WIDGET_BG};
                border: none;
                width: 20px;
            }}
        """)
        layout.addWidget(self.sam3_refine)
        
        # r_dilate — MatAnyone2 mask dilation (px)
        dil_label = QtWidgets.QLabel("MatAnyone Edge Dilate (px):")
        dil_label.setObjectName("hint")
        layout.addWidget(dil_label)
        self.mat_dilate = QtWidgets.QSpinBox()
        self.mat_dilate.setRange(-50, 50)
        self.mat_dilate.setValue(3)
        self.mat_dilate.setMinimumHeight(28)
        self.mat_dilate.setToolTip(
            "Expand the mask edge. 2-3 recovers fluffy edges (hair) that SAM3 clips. "
            "Negative = shrink the mask."
        )
        self.mat_dilate.setStyleSheet(f"""
            QSpinBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {FLAME_WIDGET_BG};
                border: none;
                width: 20px;
            }}
        """)
        layout.addWidget(self.mat_dilate)
        
        # r_erode — MatAnyone2 mask erosion (px)
        ero_label = QtWidgets.QLabel("MatAnyone Edge Erode (px):")
        ero_label.setObjectName("hint")
        layout.addWidget(ero_label)
        self.mat_erode = QtWidgets.QSpinBox()
        self.mat_erode.setRange(-50, 50)
        self.mat_erode.setValue(0)
        self.mat_erode.setMinimumHeight(28)
        self.mat_erode.setToolTip(
            "Shrink the mask edge. Positive values tighten a mask that spills "
            "into the background. 0 = no erosion."
        )
        self.mat_erode.setStyleSheet(f"""
            QSpinBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background-color: {FLAME_WIDGET_BG};
                border: none;
                width: 20px;
            }}
        """)
        layout.addWidget(self.mat_erode)
        
        layout.addSpacing(8)
        
        # Scroll area for multiple prompts
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QtWidgets.QWidget()
        scroll_widget.setStyleSheet(f"background-color: {FLAME_BG};")
        scroll_layout = QtWidgets.QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(10)
        
        for node_id, title, current_text in text_nodes:
            group = QtWidgets.QGroupBox(title)
            group_layout = QtWidgets.QVBoxLayout(group)
            group_layout.setContentsMargins(10, 18, 10, 10)
            
            text_edit = QtWidgets.QPlainTextEdit()
            text_edit.setPlainText(current_text)
            text_edit.setMinimumHeight(80)
            group_layout.addWidget(text_edit)
            
            self.text_edits[node_id] = text_edit
            scroll_layout.addWidget(group)
        
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)
        
        layout.addSpacing(8)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setMinimumSize(110, 28)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        skip_btn = QtWidgets.QPushButton("Skip (use defaults)")
        skip_btn.setMinimumSize(140, 28)
        skip_btn.clicked.connect(lambda: self.done(2))
        btn_layout.addWidget(skip_btn)
        
        ok_btn = QtWidgets.QPushButton("Execute")
        ok_btn.setObjectName("primary")
        ok_btn.setMinimumSize(110, 28)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def get_prompts(self):
        """Returns dict: node_id -> new_text"""
        result = {}
        for node_id, edit in self.text_edits.items():
            result[node_id] = edit.toPlainText()
        return result

    def get_output_mode(self):
        """Returns 'matte' or 'alpha' depending on the selected output mode"""
        return self.output_mode.currentData()

    def get_key_frame(self):
        """Returns the selected key frame index (which frame feeds the mask generation)"""
        return self.key_frame.value()

    def get_colour_space(self):
        """Returns the selected colour space tag ('bt709', 'srgb' or 'p3') for ProRes metadata"""
        return self.colour_space.currentData()

    def get_mask_quality(self):
        """Returns (threshold, refine_iterations, r_dilate, r_erode) for mask tuning.

        Maps to SAM3_Detect threshold/refine_iterations and MatAnyone/MatAnyone2
        r_dilate/r_erode in the workflow.
        """
        return (
            round(self.sam3_threshold.value(), 2),
            self.sam3_refine.value(),
            self.mat_dilate.value(),
            self.mat_erode.value(),
        )


class FrameRangeDialog(QtWidgets.QDialog):
    """Dialog to select frame range before exporting to ComfyUI — Flame Style"""
    
    def __init__(self, clip_name, total_frames, current_frame=1, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Export Range — {clip_name}")
        self.setMinimumWidth(420)
        self.setStyleSheet(get_flame_stylesheet())
        self.total_frames = total_frames
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        
        # Header
        header = QtWidgets.QLabel(f"Select frame range to export ({total_frames} frames total):")
        header.setObjectName("header")
        layout.addWidget(header)
        
        layout.addSpacing(8)
        
        # Mode selection
        self.mode_current = QtWidgets.QRadioButton("Current frame only")
        self.mode_custom = QtWidgets.QRadioButton("Custom range")
        self.mode_all = QtWidgets.QRadioButton("All frames")
        self.mode_all.setChecked(True)
        
        for rb in [self.mode_current, self.mode_custom, self.mode_all]:
            rb.setStyleSheet(f"""
                QRadioButton {{
                    color: {FLAME_TEXT};
                    spacing: 8px;
                    font-size: {PYFLAME_FONT_SIZE}px;
                }}
                QRadioButton::indicator {{
                    width: 14px;
                    height: 14px;
                }}
                QRadioButton::indicator:checked {{
                    background-color: {FLAME_BLUE};
                    border-radius: 7px;
                }}
                QRadioButton::indicator:unchecked {{
                    background-color: {FLAME_WIDGET_BG};
                    border-radius: 7px;
                }}
            """)
            layout.addWidget(rb)
        
        # Custom range inputs
        self.range_widget = QtWidgets.QWidget()
        range_layout = QtWidgets.QHBoxLayout(self.range_widget)
        range_layout.setContentsMargins(24, 4, 0, 4)
        range_layout.setSpacing(12)
        
        range_layout.addWidget(QtWidgets.QLabel("Start:"))
        self.start_spin = QtWidgets.QSpinBox()
        self.start_spin.setMinimum(1)
        self.start_spin.setMaximum(total_frames)
        self.start_spin.setValue(1)
        self.start_spin.setMinimumSize(80, 28)
        range_layout.addWidget(self.start_spin)
        
        range_layout.addWidget(QtWidgets.QLabel("End:"))
        self.end_spin = QtWidgets.QSpinBox()
        self.end_spin.setMinimum(1)
        self.end_spin.setMaximum(total_frames)
        self.end_spin.setValue(total_frames)
        self.end_spin.setMinimumSize(80, 28)
        range_layout.addWidget(self.end_spin)
        
        range_layout.addStretch()
        layout.addWidget(self.range_widget)
        self.range_widget.setEnabled(False)
        
        # Connect radio buttons
        self.mode_custom.toggled.connect(self.range_widget.setEnabled)
        
        # Info about current frame
        if current_frame > 0:
            info = QtWidgets.QLabel(f"Current frame: {current_frame}")
            info.setObjectName("section")
            layout.addWidget(info)
        
        # Export format selection
        layout.addSpacing(12)
        format_label = QtWidgets.QLabel("Export Format:")
        format_label.setObjectName("section")
        layout.addWidget(format_label)
        
        self.format_combo = QtWidgets.QComboBox()
        for fmt_name in EXPORT_PRESETS.keys():
            self.format_combo.addItem(fmt_name)
        
        current_format = CONFIG.get('export_format', 'PNG 8-bit')
        idx = self.format_combo.findText(current_format)
        if idx >= 0:
            self.format_combo.setCurrentIndex(idx)
        
        self.format_combo.setMinimumHeight(28)
        self.format_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {FLAME_WIDGET_BG};
                color: {FLAME_TEXT};
                border: 1px solid {FLAME_BORDER};
                padding: 4px 8px;
                font-size: {PYFLAME_FONT_SIZE}px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {FLAME_BG};
                color: {FLAME_TEXT};
                selection-background-color: {FLAME_BLUE};
            }}
        """)
        layout.addWidget(self.format_combo)
        
        layout.addStretch()
        layout.addSpacing(8)
        
        # Buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()
        
        cancel_btn = QtWidgets.QPushButton("Cancel")
        cancel_btn.setMinimumSize(110, 28)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        ok_btn = QtWidgets.QPushButton("Export")
        ok_btn.setObjectName("primary")
        ok_btn.setMinimumSize(110, 28)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        
        layout.addLayout(btn_layout)
    
    def get_range(self):
        """Returns (start_frame, end_frame) — 1-indexed, or None for all"""
        if self.mode_all.isChecked():
            return None  # All frames
        elif self.mode_current.isChecked():
            return (0, 0)  # Signal for current frame only
        else:
            return (self.start_spin.value(), self.end_spin.value())
    
    def get_export_format(self):
        """Returns selected export format name"""
        return self.format_combo.currentText()


def inject_prompts_in_workflow(workflow, prompts, is_api_format):
    """
    Inject user-edited prompts into text nodes.
    prompts: dict of node_id -> text
    """
    if is_api_format:
        for node_id, text in prompts.items():
            if node_id in workflow and isinstance(workflow[node_id], dict):
                if 'inputs' in workflow[node_id]:
                    workflow[node_id]['inputs']['text'] = text
                    title = workflow[node_id].get('_meta', {}).get('title', node_id)
                    log(f"Prompt injected into '{title}': {text[:50]}...")
    else:
        node_map = {str(n['id']): n for n in workflow.get('nodes', [])}
        for node_id, text in prompts.items():
            if node_id in node_map:
                node = node_map[node_id]
                if 'widgets_values' in node and len(node['widgets_values']) > 0:
                    node['widgets_values'][0] = text
                else:
                    node['widgets_values'] = [text]
                log(f"Prompt injected into node {node_id}: {text[:50]}...")
    
    return workflow


def inject_multi_clip_in_workflow(workflow, clip_folders, assignments, is_api_format):
    """
    Inject multiple clip folders into multiple FlameLoad nodes.
    clip_folders: list of folder names (one per exported clip)
    assignments: dict of node_id -> clip_index
    """
    if is_api_format:
        for node_id, clip_idx in assignments.items():
            if node_id in workflow and isinstance(workflow[node_id], dict):
                if clip_idx < len(clip_folders):
                    folder_name = clip_folders[clip_idx]
                    workflow[node_id]['inputs']['folder'] = folder_name
                    workflow[node_id]['inputs']['auto_load_latest'] = False
                    title = workflow[node_id].get('_meta', {}).get('title', node_id)
                    log(f"FlameLoad '{title}' (ID: {node_id}) -> folder: {folder_name}")
    else:
        node_map = {str(n['id']): n for n in workflow.get('nodes', [])}
        for node_id, clip_idx in assignments.items():
            if node_id in node_map and clip_idx < len(clip_folders):
                node = node_map[node_id]
                folder_name = clip_folders[clip_idx]
                if 'widgets_values' in node and len(node['widgets_values']) >= 2:
                    node['widgets_values'][0] = False
                    node['widgets_values'][1] = folder_name
                else:
                    node['widgets_values'] = [False, folder_name, 0, -1]
                log(f"FlameLoad node {node_id} -> folder: {folder_name}")
    
    return workflow


def inject_image_path_in_workflow(workflow, image_path, is_api_format):
    """
    Inject image path into workflow.
    Handles both LoadImage nodes (needs Flame_outputs/clip/file.png) 
    and FlameLoad nodes (needs just the folder name).
    """
    # Determine folder name and file path
    if os.path.isdir(image_path):
        files = sorted([f for f in os.listdir(image_path) if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))])
        if files:
            folder_name = os.path.basename(image_path)
            # LoadImage expects path relative to ComfyUI input/ folder
            comfy_path = f"Flame_outputs/{folder_name}/{files[0]}"
        else:
            log("ERROR: No PNG files found in folder")
            return workflow
    else:
        # image_path is like "clip_name/clip_name00000001.png"
        parts = image_path.replace('\\', '/').split('/')
        if len(parts) >= 2:
            folder_name = parts[0]
            comfy_path = f"Flame_outputs/{image_path}"
        else:
            folder_name = ""
            comfy_path = f"Flame_outputs/{image_path}"
    
    log(f"Injecting image path into workflow: {comfy_path}")
    
    modified_load = False
    modified_flame = False
    
    if is_api_format:
        # API format
        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict):
                class_type = node_data.get('class_type', '')
                
                # Inject into LoadImage nodes
                if class_type == 'LoadImage':
                    if 'inputs' in node_data:
                        node_data['inputs']['image'] = comfy_path
                        log(f"LoadImage node found (ID: {node_id}) - image: {comfy_path}")
                        modified_load = True
                
                # Inject into FlameLoad nodes
                elif class_type == 'FlameLoad':
                    if 'inputs' in node_data:
                        node_data['inputs']['folder'] = folder_name
                        node_data['inputs']['auto_load_latest'] = False
                        log(f"FlameLoad node found (ID: {node_id}) - folder: {folder_name}")
                        modified_flame = True
    else:
        # Normal format
        if "nodes" in workflow:
            for node in workflow["nodes"]:
                node_type = node.get("type", "")
                
                if node_type == "LoadImage":
                    if "widgets_values" not in node:
                        node["widgets_values"] = []
                    if len(node["widgets_values"]) > 0:
                        node["widgets_values"][0] = comfy_path
                    else:
                        node["widgets_values"].append(comfy_path)
                    log(f"LoadImage node found (ID: {node['id']}) - image: {comfy_path}")
                    modified_load = True
                
                elif node_type == "FlameLoad":
                    if "widgets_values" not in node:
                        node["widgets_values"] = [False, folder_name, 0, -1]
                    else:
                        if len(node["widgets_values"]) >= 2:
                            node["widgets_values"][0] = False  # Disable auto
                            node["widgets_values"][1] = folder_name
                    log(f"FlameLoad node found (ID: {node['id']}) - folder: {folder_name}")
                    modified_flame = True
    
    if not modified_load and not modified_flame:
        log("WARNING: No LoadImage or FlameLoad node found in workflow")
    
    # Inject pipeline_result_path into FlameSend nodes (for remote/network import)
    pipeline_result = CONFIG.get('pipeline_result_path', '').strip()
    if pipeline_result and is_api_format:
        resolved_pipeline = resolve_flame_tokens(pipeline_result)
        # Also resolve clip name
        if folder_name:
            resolved_pipeline = resolved_pipeline.replace('<clip name>', folder_name)
        
        for node_id, node_data in workflow.items():
            if isinstance(node_data, dict):
                class_type = node_data.get('class_type', '')
                if class_type in ('FlameSend', 'SendToFlame'):
                    if 'inputs' not in node_data:
                        node_data['inputs'] = {}
                    node_data['inputs']['pipeline_result_path'] = resolved_pipeline
                    log(f"Injected pipeline_result_path into FlameSend: {resolved_pipeline}")
    
    return workflow


def inject_alpha_composite_in_workflow(workflow, is_api_format):
    """Rewire a matte-producing workflow to output RGBA video with alpha.

    Finds the FlameSend/MatAnyone producer chain and inserts
    ImageToMask (matte -> MASK) + InvertMask + JoinImageWithAlpha (original + MASK -> RGBA),
    then points FlameSend at the composited RGBA output.
    InvertMask compensates JoinImageWithAlpha's built-in alpha inversion (alpha = 1 - mask).
    Only API-format workflows are supported (auto mode).
    """
    if not is_api_format:
        log("WARNING: Alpha composite injection requires API format workflow")
        return workflow

    flame_send_id = None
    flame_load_id = None
    matte_source = None

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        if class_type == 'FlameSend':
            flame_send_id = node_id
            img_ref = inputs.get('images')
            if isinstance(img_ref, list) and len(img_ref) == 2:
                matte_source = (str(img_ref[0]), img_ref[1])
        elif class_type == 'FlameLoad':
            if flame_load_id is None:
                flame_load_id = node_id

    if flame_send_id is None or matte_source is None:
        log("WARNING: Cannot inject alpha composite - no FlameSend/matte source found")
        return workflow
    if flame_load_id is None:
        log("WARNING: Cannot inject alpha composite - no FlameLoad found")
        return workflow

    max_id = max((int(nid) for nid in workflow.keys() if str(nid).isdigit()), default=0)

    to_mask_id = str(max_id + 1)
    invert_id = str(max_id + 2)
    join_id = str(max_id + 3)

    workflow[to_mask_id] = {
        "class_type": "ImageToMask",
        "inputs": {
            "image": [matte_source[0], matte_source[1]],
            "channel": "red",
        },
    }

    workflow[invert_id] = {
        "class_type": "InvertMask",
        "inputs": {
            "mask": [to_mask_id, 0],
        },
    }

    workflow[join_id] = {
        "class_type": "JoinImageWithAlpha",
        "inputs": {
            "image": [flame_load_id, 0],
            "alpha": [invert_id, 0],
        },
    }

    workflow[flame_send_id]["inputs"]["images"] = [join_id, 0]
    # Switch output to ProRes 4444 (.mov): Flame imports its alpha natively,
    # unlike EXR sequences where alpha must be explicitly enabled at import.
    workflow[flame_send_id]["inputs"]["file_type"] = "mov"
    log(f"Alpha composite injected: ImageToMask={to_mask_id}, InvertMask={invert_id}, JoinImageWithAlpha={join_id}, FlameSend={flame_send_id}")
    return workflow


def inject_key_frame_in_workflow(workflow, key_frame, is_api_format):
    """Set the reference frame used for mask generation and matting.

    Updates ImageFromBatch.batch_index (SAM3 mask source frame) and
    MatAnyone/MatAnyone2 mask_frame (which frame the mask applies to).
    """
    if not is_api_format:
        log("WARNING: Key frame injection requires API format workflow")
        return workflow

    batch_found = False
    matte_found = False

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        if class_type == 'ImageFromBatch':
            inputs['batch_index'] = key_frame
            batch_found = True
        elif class_type in ('MatAnyone', 'MatAnyone2'):
            inputs['mask_frame'] = key_frame
            matte_found = True

    if batch_found or matte_found:
        log(f"Key frame injected: batch_index/mask_frame = {key_frame} (ImageFromBatch={batch_found}, MatAnyone={matte_found})")
    else:
        log(f"WARNING: No ImageFromBatch/MatAnyone nodes found - key frame {key_frame} not applied")
    return workflow


def inject_mask_quality_in_workflow(workflow, threshold, refine, r_dilate, r_erode, is_api_format):
    """Apply mask-quality tuning to SAM3_Detect and MatAnyone/MatAnyone2.

    threshold/refine_iterations live on SAM3_Detect; r_dilate/r_erode live on
    MatAnyone/MatAnyone2. Each is only applied if its target node exists.
    """
    if not is_api_format:
        log("WARNING: Mask quality injection requires API format workflow")
        return workflow

    sam3_found = False
    matte_found = False

    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        class_type = node_data.get('class_type', '')
        inputs = node_data.get('inputs', {})
        if class_type == 'SAM3_Detect':
            inputs['threshold'] = threshold
            inputs['refine_iterations'] = refine
            sam3_found = True
        elif class_type in ('MatAnyone', 'MatAnyone2'):
            inputs['r_dilate'] = r_dilate
            inputs['r_erode'] = r_erode
            matte_found = True

    if sam3_found or matte_found:
        log(f"Mask quality injected: threshold={threshold}, refine={refine}, "
            f"r_dilate={r_dilate}, r_erode={r_erode} (SAM3={sam3_found}, MatAnyone={matte_found})")
    else:
        log(f"WARNING: No SAM3_Detect/MatAnyone nodes found - mask quality not applied")
    return workflow


def inject_colour_space_in_workflow(workflow, colour_space, is_api_format):
    """Tag the ProRes output with the colour space of the source clip.

    Writes the colour space (bt709/srgb/p3) into the FlameSend node so the
    .mov metadata matches the source. Only meaningful for 'Video with Alpha'
    output (file_type=mov); for matte EXR output the tag is irrelevant.
    """
    if not is_api_format:
        log("WARNING: Colour space injection requires API format workflow")
        return workflow

    found = False
    for node_id, node_data in workflow.items():
        if not isinstance(node_data, dict):
            continue
        if node_data.get('class_type') == 'FlameSend':
            node_data['inputs']['colour_space'] = colour_space
            found = True

    if found:
        log(f"Colour space injected: FlameSend colour_space = {colour_space}")
    else:
        log("WARNING: No FlameSend node found - colour space not applied")
    return workflow


def watch_flame_notification_and_import(workflow_name, clip_name, timeout=300):
    """
    Watch notification file and auto-import into Flame
    
    Args:
        workflow_name: Name of executed workflow
        clip_name: Original clip name
        timeout: Max wait time in seconds (5 min default)
        
    Returns:
        bool: True if import successful
    """
    import flame
    
    notification_file = FLAME_NOTIFICATION_FILE
    
    log(f"\nWaiting for ComfyUI result...")
    log(f"Watching file: {notification_file}")
    log(f"Timeout: {timeout} secondes")
    
    # Delete old notification file if it exists
    if os.path.exists(notification_file):
        os.remove(notification_file)
        log("Old notification file deleted")
    
    start_time = time.time()
    last_mtime = 0
    
    while time.time() - start_time < timeout:
        # Check if file exists
        if os.path.exists(notification_file):
            # Check if file was modified
            current_mtime = os.path.getmtime(notification_file)
            
            if current_mtime > last_mtime:
                last_mtime = current_mtime
                
                # Wait a bit to ensure file is complete
                time.sleep(1)
                
                try:
                    # Read notification file
                    with open(notification_file, 'r') as f:
                        notification = json.load(f)
                    
                    # Verify it's ready
                    if notification.get('status') == 'ready':
                        files = notification.get('files', [])
                        
                        if not files:
                            log("ERROR: No files in notification")
                            continue
                        
                        log(f"Notification received! {len(files)} file(s)")
                        
                        # Determine what to import
                        if len(files) == 1:
                            import_path = files[0]
                            log(f"Single image: {import_path}")
                        else:
                            # Multiple files - importing folder
                            import_path = os.path.dirname(files[0])
                            log(f"Sequence: {len(files)} files in {import_path}")
                        
                        # Verify file exists
                        if not os.path.exists(import_path):
                            log(f"ERROR: File not found: {import_path}")
                            continue
                        
                        # Import into Flame
                        log(f"Importing into Flame...")
                        
                        try:
                            # ==========================================
                            # 1. Import into Library (original behavior)
                            # ==========================================
                            workspace = flame.project.current_project.current_workspace
                            
                            comfy_library = None

                            # Find or create "ComfyUI" library
                            all_libs = list(workspace.libraries)
                            log(f"DEBUG: {len(all_libs)} libraries found")
                            for library in all_libs:
                                lib_name = str(library.name).strip("'\" ")
                                log(f"DEBUG: checking '{lib_name}' == 'ComfyUI' → {lib_name == 'ComfyUI'}")
                                if lib_name == "ComfyUI":
                                    comfy_library = library
                                    log("Library 'ComfyUI' found")
                                    break

                            log(f"DEBUG: comfy_library is None: {comfy_library is None}")
                            if comfy_library is None:
                                log("Creating library 'ComfyUI'...")
                                comfy_library = workspace.create_library("ComfyUI")
                                log("Library 'ComfyUI' created!")

                            # Get or create a date-based folder (YYYY-MM-DD)
                            from datetime import datetime
                            date_str = datetime.now().strftime("%Y-%m-%d")
                            date_folder = None
                            for folder in comfy_library.folders:
                                folder_name = str(folder.name).strip("'\" ")
                                if folder_name == date_str:
                                    date_folder = folder
                                    break
                            if not date_folder:
                                log(f"Creating folder '{date_str}'...")
                                date_folder = comfy_library.create_folder(date_str)

                            workflow_folder = date_folder
                            log(f"Importing to: Library ComfyUI / {date_str}")
                            
                            # Import with flame.import_clips()
                            imported = flame.import_clips(import_path, workflow_folder)
                            
                            if imported:
                                log(f"Import successful! Clip imported to Library ComfyUI/{workflow_name}")
                                
                                # Rename the clip with timestamp to avoid overwrites
                                from datetime import datetime
                                timestamp = datetime.now().strftime("%H%M%S")
                                
                                if isinstance(imported, list) and len(imported) > 0:
                                    clip = imported[0]
                                else:
                                    clip = imported
                                
                                new_name = f"{clip_name}_comfyui_{timestamp}"
                                
                                if hasattr(clip, 'name'):
                                    if hasattr(clip.name, 'set_value'):
                                        clip.name.set_value(new_name)
                                    else:
                                        clip.name = new_name
                                
                                log(f"Clip renamed: {new_name}")
                                
                                # ==========================================
                                # 2. Import into Batch Schematic Reel (deferred)
                                # ==========================================
                                try:
                                    if hasattr(flame, 'batch') and flame.batch:
                                        reel_name = "ComfyUI Results"
                                        _import_path = import_path
                                        _new_name = new_name
                                        
                                        def _deferred_batch_import():
                                            try:
                                                target_reel = None
                                                for reel in flame.batch.reels:
                                                    if str(reel.name) == reel_name:
                                                        target_reel = reel
                                                        break
                                                
                                                if not target_reel:
                                                    target_reel = flame.batch.create_reel(reel_name)
                                                    log(f"Created schematic reel: {reel_name}")
                                                
                                                batch_imported = flame.batch.import_clip(_import_path, reel_name)
                                                
                                                if batch_imported:
                                                    batch_clip = batch_imported
                                                    if isinstance(batch_imported, list) and len(batch_imported) > 0:
                                                        batch_clip = batch_imported[0]
                                                    
                                                    if hasattr(batch_clip, 'name'):
                                                        if hasattr(batch_clip.name, 'set_value'):
                                                            batch_clip.name.set_value(_new_name)
                                                        else:
                                                            batch_clip.name = _new_name
                                                    
                                                    log(f"Also imported to Batch Schematic Reel: {reel_name}")
                                            except Exception as e:
                                                log(f"Batch reel import error: {e}")
                                        
                                        # Defer by 500ms to avoid Flame timer conflicts
                                        QtCore.QTimer.singleShot(500, _deferred_batch_import)
                                        
                                except Exception as batch_err:
                                    log(f"Note: Batch reel import skipped ({batch_err})")
                                
                                # ==========================================
                                # 3. Copy result to pipeline path if configured
                                # ==========================================
                                try:
                                    config = load_config()
                                    pipeline_result = config.get('pipeline_result_path', '').strip()
                                    
                                    if pipeline_result:
                                        import shutil
                                        
                                        resolved_result = resolve_flame_tokens(pipeline_result)
                                        resolved_result = resolved_result.replace('<clip name>', clip_name)
                                        
                                        try:
                                            if hasattr(flame, 'batch') and flame.batch:
                                                resolved_result = resolved_result.replace('<batch name>', _get_flame_attr_str(flame.batch.name))
                                        except:
                                            pass
                                        
                                        # Create timestamped folder to avoid overwrites
                                        from datetime import datetime
                                        result_folder_name = f"{clip_name}_comfyui_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                                        dest_dir = os.path.join(resolved_result, result_folder_name)
                                        
                                        os.makedirs(dest_dir, exist_ok=True)
                                        
                                        # Copy all result files
                                        src_folder = notification.get('output_folder', '')
                                        src_dir = os.path.join(COMFY_OUTPUT_DIR, src_folder) if src_folder else os.path.dirname(import_path)
                                        
                                        if os.path.isdir(src_dir):
                                            for f in os.listdir(src_dir):
                                                src_file = os.path.join(src_dir, f)
                                                if os.path.isfile(src_file):
                                                    shutil.copy2(src_file, dest_dir)
                                            log(f"Results copied to pipeline: {dest_dir}")
                                        else:
                                            # Single file
                                            shutil.copy2(import_path, dest_dir)
                                            log(f"Result copied to pipeline: {dest_dir}")
                                except Exception as pipe_err:
                                    log(f"Note: Pipeline copy skipped ({pipe_err})")
                                
                                flame.messages.show_in_console(
                                    f"Result in Library ComfyUI/{workflow_name}",
                                    duration=5
                                )
                                
                                # Clean up notification file
                                os.remove(notification_file)
                                
                                return True
                            else:
                                log("ERROR: import_clips returned None")
                                
                        except Exception as e:
                            log(f"ERROR during import Flame: {e}")
                            import traceback
                            traceback.print_exc()
                            
                            flame.messages.show_in_console(
                                "Import error - check console",
                                duration=5
                            )
                            return False
                
                except json.JSONDecodeError as e:
                    log(f"Error reading notification (incomplete file?): {e}")
                    # Continue waiting
                
                except Exception as e:
                    log(f"Error processing notification: {e}")
                    import traceback
                    traceback.print_exc()
        
        time.sleep(1)
    
    log(f"Timeout: aucune notification recue apres {timeout}s")
    log("Verifiez que votre workflow ComfyUI contient un node 'Send to Flame'")
    
    flame.messages.show_in_console(
        "Timeout - ajoutez node 'Send to Flame' au workflow",
        duration=7
    )
    
    return False


def inject_workflow_safari_macos(workflow, comfy_search_url, workflow_json_escaped):
    """
    Injecte le workflow dans Safari sur macOS via AppleScript
    
    Returns:
        bool: True if successful
    """
    import subprocess
    import time
    
    log("Waiting for ComfyUI to load in Safari...")
    max_attempts = 15
    success = False
    
    for attempt in range(max_attempts):
        time.sleep(2)
        
        # Step 1: check if tab exists
        tab_check_script = f'''
tell application "Safari"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{comfy_search_url}" then
                return "TAB_FOUND"
            end if
        end repeat
    end repeat
    return "NO_TAB"
end tell
'''
        tab_result = subprocess.run(
            ['osascript', '-e', tab_check_script],
            capture_output=True, text=True, timeout=5
        )
        tab_status = tab_result.stdout.strip()
        
        if tab_status != "TAB_FOUND":
            log(f"⏳ Attempt {attempt + 1}/{max_attempts}: Safari tab not yet open...")
            continue
        
        # Step 2: tab found, check if ComfyUI app is ready
        js_check_script = f'''
tell application "Safari"
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{comfy_search_url}" then
                try
                    set result to do JavaScript "typeof app !== 'undefined' && typeof app.loadGraphData === 'function' ? 'READY' : 'NOT_READY'" in t
                    return result
                on error errMsg
                    return "JS_BLOCKED: " & errMsg
                end try
            end if
        end repeat
    end repeat
    return "NO_TAB"
end tell
'''
        js_result = subprocess.run(
            ['osascript', '-e', js_check_script],
            capture_output=True, text=True, timeout=5
        )
        status = js_result.stdout.strip()
        
        if status == "READY":
            log(f"✅ ComfyUI ready (after {(attempt + 1) * 2} seconds)")
            success = True
            break
        elif status == "NOT_READY":
            log(f"⏳ Attempt {attempt + 1}/{max_attempts}: ComfyUI loaded but app not ready...")
        elif status.startswith("JS_BLOCKED"):
            log(f"⚠️  JavaScript blocked by Safari: enable Develop > Allow JavaScript from Apple Events")
            log(f"   Workflow is available manually in ComfyUI > Load")
            return False
        else:
            log(f"⏳ Attempt {attempt + 1}/{max_attempts}: Unknown status: {status}")
    
    if not success:
        log("❌ Timeout: ComfyUI not ready after 30 seconds")
        return False
    
    # Inject workflow
    applescript = f'''
tell application "Safari"
    set found to false
    repeat with w in windows
        repeat with t in tabs of w
            if URL of t contains "{comfy_search_url}" then
                set current tab of w to t
                set index of w to 1
                do JavaScript "(function() {{ if (typeof app !== 'undefined' && app.loadGraphData) {{ app.loadGraphData({workflow_json_escaped}); return 'SUCCESS'; }} else {{ return 'APP_NOT_READY'; }} }})();" in t
                set found to true
                exit repeat
            end if
        end repeat
        if found then exit repeat
    end repeat
end tell
'''
    
    result = subprocess.run(
        ['osascript', '-e', applescript],
        capture_output=True, text=True, timeout=10
    )
    
    if result.returncode == 0:
        output = result.stdout.strip()
        if "SUCCESS" in output:
            log("✅ Workflow loaded automatically in ComfyUI!")
            return True
        elif "APP_NOT_READY" in output:
            log("⚠️ ComfyUI not ready after verification")
            return False
        else:
            log(f"Response AppleScript: {output}")
            return False
    else:
        log(f"❌ Auto-load failed: {result.stderr}")
        return False


def _ensure_chrome_with_debug(comfy_url, cdp_port=9222):
    """
    Ensure Chrome is running with remote debugging enabled.
    If not found, launch a new instance automatically.
    
    Returns:
        bool: True if Chrome with debug port is accessible
    """
    import subprocess
    
    CDP_URL = f"http://localhost:{cdp_port}"
    
    # Check if Chrome debug port is already accessible
    try:
        req = urllib.request.Request(f"{CDP_URL}/json/version")
        with urllib.request.urlopen(req, timeout=2) as resp:
            info = json.loads(resp.read().decode('utf-8'))
            log(f"Chrome already running with debug port {cdp_port}")
            return True
    except Exception:
        pass
    
    # Not running — try to launch Chrome with debug port
    log(f"Launching Chrome with remote debugging on port {cdp_port}...")
    
    # Find Chrome binary
    chrome_paths = [
        'google-chrome',
        'google-chrome-stable',
        'chromium-browser',
        'chromium',
        '/opt/google/chrome/google-chrome',
        '/usr/bin/google-chrome',
    ]
    
    chrome_bin = None
    for path in chrome_paths:
        try:
            result = subprocess.run(['which', path], capture_output=True, text=True, timeout=3)
            if result.returncode == 0:
                chrome_bin = result.stdout.strip()
                break
        except Exception:
            continue
    
    if not chrome_bin:
        log("ERROR: Chrome/Chromium not found in PATH")
        return False
    
    # Launch Chrome with debug port and ComfyUI URL
    try:
        subprocess.Popen(
            [
                chrome_bin,
                f'--remote-debugging-port={cdp_port}',
                '--no-first-run',
                '--no-default-browser-check',
                comfy_url
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        log(f"Chrome launched: {chrome_bin}")
    except Exception as e:
        log(f"ERROR: Failed to launch Chrome: {e}")
        return False
    
    # Wait for Chrome to become accessible
    import time
    for i in range(10):
        time.sleep(1)
        try:
            req = urllib.request.Request(f"{CDP_URL}/json/version")
            with urllib.request.urlopen(req, timeout=2) as resp:
                log(f"Chrome ready on port {cdp_port}")
                return True
        except Exception:
            pass
    
    log(f"WARNING: Chrome launched but debug port {cdp_port} not responding")
    return False


def inject_workflow_chrome_linux(workflow, comfy_url):
    """
    Inject workflow into Chrome/Chromium on Linux via CDP (Chrome DevTools Protocol)
    Uses only urllib (stdlib) - ZERO external dependencies.
    Auto-launches Chrome with --remote-debugging-port=9222 if not already running.
    
    Returns:
        bool: True if successful
    """
    import time
    
    CDP_PORT = 9222
    CDP_URL = f"http://localhost:{CDP_PORT}"
    
    # Auto-launch Chrome if needed
    if not _ensure_chrome_with_debug(comfy_url, CDP_PORT):
        log("Cannot access Chrome with debug port — workflow injection failed")
        log("You can load the workflow manually from ComfyUI > Load")
        return False
    
    log("Waiting for ComfyUI to load in Chrome (via CDP)...")
    max_attempts = 15
    
    for attempt in range(max_attempts):
        time.sleep(2)
        
        try:
            # 1. List tabs via CDP /json
            try:
                req = urllib.request.Request(f"{CDP_URL}/json")
                with urllib.request.urlopen(req, timeout=3) as resp:
                    tabs = json.loads(resp.read().decode('utf-8'))
            except Exception:
                log(f"Attempt {attempt + 1}/{max_attempts}: Chrome not yet responding...")
                continue
            
            # 2. Find ComfyUI tab
            comfy_tab = None
            for tab in tabs:
                tab_url = tab.get('url', '')
                if comfy_url.replace('http://', '') in tab_url.replace('http://', ''):
                    comfy_tab = tab
                    break
            
            if not comfy_tab:
                log(f"Attempt {attempt + 1}/{max_attempts}: ComfyUI tab not yet open...")
                continue
            
            ws_url = comfy_tab.get('webSocketDebuggerUrl', '')
            if not ws_url:
                log(f"Attempt {attempt + 1}/{max_attempts}: No WebSocket for this tab...")
                continue
            
            # 3. Evaluate JavaScript via CDP WebSocket
            # Using a minimal WebSocket client (no external lib)
            success = _cdp_evaluate_js(ws_url, workflow)
            if success:
                return True
            else:
                log(f"Attempt {attempt + 1}/{max_attempts}: ComfyUI loaded but app not ready...")
                continue
                
        except Exception as e:
            if attempt == max_attempts - 1:
                log(f"CDP error: {e}")
                return False
            continue
    
    log("Timeout: ComfyUI not ready after 30 seconds")
    return False


def _cdp_evaluate_js(ws_url, workflow):
    """
    Execute du JavaScript dans Chrome via CDP WebSocket.
    Mini-client WebSocket minimaliste utilisant uniquement la stdlib.
    
    Returns:
        bool: True si le workflow a ete charge avec succes
    """
    import socket
    import struct
    import hashlib
    import base64
    
    # Parser l'URL WebSocket
    # ws://localhost:9222/devtools/page/XXXX
    ws_url_clean = ws_url.replace('ws://', '')
    host_port, path = ws_url_clean.split('/', 1)
    host, port = host_port.split(':')
    port = int(port)
    path = '/' + path
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    
    try:
        sock.connect((host, port))
        
        # WebSocket handshake
        ws_key = base64.b64encode(os.urandom(16)).decode('utf-8')
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        )
        sock.sendall(handshake.encode('utf-8'))
        
        # Lire la reponse du handshake
        response = b''
        while b'\r\n\r\n' not in response:
            chunk = sock.recv(4096)
            if not chunk:
                return False
            response += chunk
        
        if b'101' not in response:
            log("Error: WebSocket handshake echoue")
            return False
        
        # Fonction pour envoyer un message WebSocket (masque client)
        def ws_send(data):
            payload = data.encode('utf-8')
            frame = bytearray()
            frame.append(0x81)  # FIN + TEXT
            mask_key = os.urandom(4)
            length = len(payload)
            if length < 126:
                frame.append(0x80 | length)  # MASK bit + length
            elif length < 65536:
                frame.append(0x80 | 126)
                frame.extend(struct.pack('>H', length))
            else:
                frame.append(0x80 | 127)
                frame.extend(struct.pack('>Q', length))
            frame.extend(mask_key)
            masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            frame.extend(masked)
            sock.sendall(bytes(frame))
        
        # Fonction pour recevoir un message WebSocket
        def ws_recv(timeout=10):
            sock.settimeout(timeout)
            try:
                header = _recv_exactly(sock, 2)
                if not header:
                    return None
                
                payload_len = header[1] & 0x7F
                if payload_len == 126:
                    ext = _recv_exactly(sock, 2)
                    payload_len = struct.unpack('>H', ext)[0]
                elif payload_len == 127:
                    ext = _recv_exactly(sock, 8)
                    payload_len = struct.unpack('>Q', ext)[0]
                
                data = _recv_exactly(sock, payload_len)
                if data:
                    return data.decode('utf-8', errors='replace')
                return None
            except socket.timeout:
                return None
        
        # Etape 1: Verifier si app.loadGraphData existe
        check_msg = json.dumps({
            "id": 1,
            "method": "Runtime.evaluate",
            "params": {
                "expression": "typeof app !== 'undefined' && typeof app.loadGraphData === 'function'",
                "returnByValue": True
            }
        })
        ws_send(check_msg)
        
        check_response = ws_recv(timeout=5)
        if not check_response:
            return False
        
        try:
            check_result = json.loads(check_response)
            value = check_result.get('result', {}).get('result', {}).get('value', False)
            if not value:
                return False
        except (json.JSONDecodeError, KeyError):
            return False
        
        log("ComfyUI ready! Injecting workflow...")
        
        # Etape 2: Injecter le workflow
        workflow_json_str = json.dumps(workflow)
        # Double-escape pour injecter dans le JS
        js_safe = workflow_json_str.replace('\\', '\\\\').replace("'", "\\'")
        
        inject_msg = json.dumps({
            "id": 2,
            "method": "Runtime.evaluate",
            "params": {
                "expression": f"(function() {{ try {{ app.loadGraphData(JSON.parse('{js_safe}')); return 'SUCCESS'; }} catch(e) {{ return 'ERROR: ' + e.message; }} }})()",
                "returnByValue": True
            }
        })
        ws_send(inject_msg)
        
        inject_response = ws_recv(timeout=10)
        if not inject_response:
            log("No response after injection")
            return False
        
        try:
            inject_result = json.loads(inject_response)
            result_value = inject_result.get('result', {}).get('result', {}).get('value', '')
            if 'SUCCESS' in str(result_value):
                log("Workflow loaded automatically in ComfyUI!")
                return True
            else:
                log(f"Injection result: {result_value}")
                return False
        except (json.JSONDecodeError, KeyError):
            return False
        
    except Exception as e:
        log(f"WebSocket CDP error: {e}")
        return False
    finally:
        try:
            sock.close()
        except:
            pass


def _recv_exactly(sock, n):
    """Recoit exactement n bytes depuis le socket"""
    data = b''
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            return None
        data += chunk
    return data


def load_workflow_in_comfyui_interface(workflow_path, workflow_name, clip_folder_name):
    """
    Prepare workflow for manual mode by injecting the exact path
    AND auto-load into ComfyUI via JavaScript injection
    
    Args:
        workflow_path: Path to workflow .json file
        workflow_name: Workflow name for logging
        clip_folder_name: Name of folder containing exported images
        
    Returns:
        str: Workflow filename or None on error
    """
    try:
        # Read original workflow
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        
        # Inject specific folder into FlameLoad nodes
        if 'nodes' in workflow:
            # Normal format (interface)
            for node in workflow.get('nodes', []):
                if node.get('type') == 'FlameLoad':
                    # Disable auto_load_latest and force manual folder
                    if 'widgets_values' in node:
                        # widgets_values = [auto_load_latest, manual_folder, start_frame, max_frames]
                        node['widgets_values'][0] = False  # Disable auto
                        node['widgets_values'][1] = clip_folder_name  # Forcer ce dossier
                        log(f"FlameLoad configured to load: {clip_folder_name}")
        
        # Temp folder in ComfyUI user workflows (accessible via SSHFS or local)
        # Derive path from comfy_input_dir
        comfy_base = COMFY_INPUT_DIR.rsplit('/input', 1)[0] if '/input' in COMFY_INPUT_DIR else COMFY_INPUT_DIR
        comfy_workflows_dir = os.path.join(comfy_base, 'user', 'default', 'workflows')
        temp_dir = os.path.join(comfy_workflows_dir, 'flame_temp')
        
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            log(f"Temp folder created: {temp_dir}")
        
        # Temp file name
        temp_name = f"{clip_folder_name}.json"
        temp_path = os.path.join(temp_dir, temp_name)
        
        # Save modified workflow
        with open(temp_path, 'w') as f:
            json.dump(workflow, f, indent=2)
        
        log(f"Temp workflow saved: user/default/workflows/flame_temp/{temp_name}")
        log(f"Available in ComfyUI: Load > user/default/workflows/flame_temp/")
        
        # Auto-inject workflow based on OS
        try:
            # Build expected URL
            comfy_host = CONFIG['comfy_url'].replace('http://', '').replace('https://', '')
            comfy_search_url = f"{comfy_host}:{CONFIG['comfy_port']}"
            comfy_full_url = f"{CONFIG['comfy_url']}:{CONFIG['comfy_port']}"
            
            # Escape JSON for JavaScript
            workflow_json_escaped = json.dumps(workflow).replace('\\', '\\\\').replace('"', '\\"')
            
            # Detect OS and call appropriate function
            current_os = platform.system()
            
            if current_os == 'Darwin':  # macOS
                log(f"Searching Safari tab with URL containing: {comfy_search_url}")
                success = inject_workflow_safari_macos(workflow, comfy_search_url, workflow_json_escaped)
            elif current_os == 'Linux':
                log(f"Connecting to Chrome via CDP to inject workflow...")
                success = inject_workflow_chrome_linux(workflow, comfy_full_url)
            else:
                log(f"⚠️  OS not supported for auto-injection: {current_os}")
                log(f"   Workflow available in ComfyUI > Load > user/default/workflows/flame_temp/{temp_name}")
                return temp_name
            
            if not success:
                log(f"Workflow available in ComfyUI > Load > user/default/workflows/flame_temp/{temp_name}")
                
        except Exception as e:
            log(f"❌ Auto-load failed: {e}")
            import traceback
            traceback.print_exc()
            log(f"Workflow available in ComfyUI > Load > user/default/workflows/flame_temp/{temp_name}")
        
        return temp_name
            
    except Exception as e:
        log(f"Error preparing workflow: {e}")
        import traceback
        traceback.print_exc()
        return None


def send_workflow_to_comfyui(workflow, workflow_name):
    """
    Save workflow and execute it automatically in ComfyUI
    
    Returns:
        bool: True if successful
    """
    import webbrowser
    import shutil
    
    current_config = load_config()
    current_url = f"{current_config['comfy_url']}:{current_config['comfy_port']}"
    
    try:
        # ComfyUI workflows folder path (dynamic)
        comfy_workflows_dir = current_config['comfy_input_dir'].replace('/input/Flame_outputs', '/user/default/workflows')
        comfy_temp_dir = os.path.join(comfy_workflows_dir, 'flame_temp')
        
        # Create folder if it doesn't exist
        if not os.path.exists(comfy_temp_dir):
            os.makedirs(comfy_temp_dir)
            log(f"Temp folder created: {comfy_temp_dir}")
        
        # Temp workflow name
        temp_workflow_name = f"flame_temp_{workflow_name}"
        workflow_file = os.path.join(comfy_temp_dir, f"{temp_workflow_name}.json")
        
        # Save workflow
        log(f"Saving workflow: {workflow_file}")
        with open(workflow_file, 'w') as f:
            json.dump(workflow, f, indent=2)
        
        log("Workflow saved!")
        
        # Execute workflow via API
        log("Executing workflow in ComfyUI...")
        
        payload = json.dumps({"prompt": workflow}).encode('utf-8')
        req = urllib.request.Request(
            f"{current_url}/prompt",
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        prompt_id = result.get('prompt_id', 'N/A')
        log(f"Workflow executed! Prompt ID: {prompt_id}")
        webbrowser.open(current_url)
        log("ComfyUI opened - check Queue for progress")
        return True
            
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False



    """
    Watch ComfyUI output folder and auto-import new files into Flame
    
    Args:
        workflow_name: Name of executed workflow
        clip_name: Original clip name
        timeout: Max wait time in seconds (5 min default)
        
    Returns:
        bool: True if import successful
    """
    import flame
    import glob
    
    log(f"\nWatching ComfyUI output folder...")
    log(f"Timeout: {timeout} secondes")
    
    # List existing files before
    existing_files = set(glob.glob(os.path.join(COMFY_OUTPUT_DIR, "**/*"), recursive=True))
    
    start_time = time.time()
    last_file_count = len(existing_files)
    stable_count = 0
    
    while time.time() - start_time < timeout:
        # List current files
        current_files = set(glob.glob(os.path.join(COMFY_OUTPUT_DIR, "**/*"), recursive=True))
        
        # New files
        new_files = current_files - existing_files
        
        if new_files:
            # Filtrer pour ne garder que les images
            image_files = [f for f in new_files if f.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff'))]
            
            if image_files:
                # Attendre que le nombre de fichiers se stabilise (export termine)
                current_count = len(current_files)
                
                if current_count == last_file_count:
                    stable_count += 1
                else:
                    stable_count = 0
                    last_file_count = current_count
                
                # Si stable pendant 3 secondes, c'est probablement fini
                if stable_count >= 3:
                    log(f"ComfyUI export complete! {len(image_files)} new file(s)")
                    
                    # Sort by modification date (most recent)
                    image_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    
                    # Take most recent file (or all if sequence)
                    file_to_import = image_files[0]
                    
                    # If in a folder, it might be a sequence
                    parent_dir = os.path.dirname(file_to_import)
                    files_in_dir = [f for f in image_files if os.path.dirname(f) == parent_dir]
                    
                    if len(files_in_dir) > 1:
                        # Sequence
                        log(f"Sequence detected: {len(files_in_dir)} files")
                        import_path = parent_dir
                    else:
                        # Single image
                        import_path = file_to_import
                    
                    # Importer dans Flame
                    log(f"Importing into Flame: {import_path}")
                    
                    try:
                        # Get current desktop
                        desktop = flame.project.current_project.current_workspace.desktop
                        
                        # Import media
                        imported_clip = flame.import_clip(import_path)
                        
                        if imported_clip:
                            # Rename with suffix
                            new_name = f"{clip_name}_comfy_{workflow_name}"
                            imported_clip.name = new_name
                            
                            log(f"Import successful: {new_name}")
                            
                            flame.messages.show_in_console(
                                f"Result imported: {new_name}",
                                duration=5
                            )
                            
                            return True
                        else:
                            log("ERROR: Import failed")
                            
                    except Exception as e:
                        log(f"ERROR during import: {e}")
                        import traceback
                        traceback.print_exc()
                        
                        flame.messages.show_in_console(
                            "Import error - file in output",
                            duration=5
                        )
                        return False
        
        time.sleep(1)
    
    log(f"Timeout: no new files detected after {timeout}s")
    log("Result can be manually imported from:")
    log(f"   {COMFY_OUTPUT_DIR}")
    
    flame.messages.show_in_console(
        "Timeout - check ComfyUI output",
        duration=5
    )
    
    return False
    """
    Save workflow and execute it automatically in ComfyUI
    
    Returns:
        bool: True if successful
    """
    import webbrowser
    import shutil
    
    current_config = load_config()
    current_url = f"{current_config['comfy_url']}:{current_config['comfy_port']}"
    
    try:
        # ComfyUI workflows folder path (dynamic)
        comfy_workflows_dir = current_config['comfy_input_dir'].replace('/input/Flame_outputs', '/user/default/workflows')
        comfy_temp_dir = os.path.join(comfy_workflows_dir, 'flame_temp')
        
        # Create folder if it doesn't exist
        if not os.path.exists(comfy_temp_dir):
            os.makedirs(comfy_temp_dir)
            log(f"Temp folder created: {comfy_temp_dir}")
        
        # Temp workflow name
        temp_workflow_name = f"flame_temp_{workflow_name}"
        workflow_file = os.path.join(comfy_temp_dir, f"{temp_workflow_name}.json")
        
        # Save workflow
        log(f"Saving workflow: {workflow_file}")
        with open(workflow_file, 'w') as f:
            json.dump(workflow, f, indent=2)
        
        log("Workflow saved!")
        
        # Execute workflow via API
        log("Executing workflow in ComfyUI...")
        
        payload = json.dumps({"prompt": workflow}).encode('utf-8')
        req = urllib.request.Request(
            f"{current_url}/prompt",
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
        
        if result:
            prompt_id = result.get('prompt_id', 'N/A')
            log(f"Workflow executed! Prompt ID: {prompt_id}")
            
            webbrowser.open(current_url)
            log("ComfyUI opened - check Queue for progress")
            
            return True
        else:
            log("Workflow execution error")
            return False
            
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def get_clip_from_item(item):
    """Extract PyClip from different Flame object types"""
    import flame
    
    if isinstance(item, (flame.PyClip, flame.PySequence)):
        return item
    
    if isinstance(item, flame.PyClipNode):
        for attr in ['clip', 'source', 'media', 'sequence', 'input']:
            if hasattr(item, attr):
                val = getattr(item, attr)
                if isinstance(val, (flame.PyClip, flame.PySequence)):
                    return val
    
    return None


def export_clip_for_comfyui(clip, preset_path, export_folder, frame_range=None):
    """Export clip via flame.PyExporter using the selected format preset.
    
    Supports PNG, EXR, MP4, and any format defined by the export preset XML.
    If pipeline_export_path is configured, exports to that path (with tokens resolved)
    and creates a symlink inside ComfyUI input/Flame_outputs/ so FlameLoad can read it.
    
    Args:
        clip: Flame clip object
        preset_path: Path to export preset XML (PNG, EXR, MP4, etc.)
        export_folder: ComfyUI input/Flame_outputs/ folder
        frame_range: None=all, (0,0)=current frame, (start,end)=custom range (1-indexed)
    """
    import flame
    
    clip_name = sanitize_filename(clip.name.get_value())
    
    # Check if pipeline export path is configured
    config = load_config()
    pipeline_export = config.get('pipeline_export_path', '').strip()
    
    if pipeline_export:
        # Resolve tokens in pipeline path
        resolved_path = resolve_flame_tokens(pipeline_export)
        
        # Try to resolve clip-specific tokens
        resolved_path = resolved_path.replace('<clip name>', clip_name)
        try:
            if hasattr(flame, 'batch') and flame.batch:
                resolved_path = resolved_path.replace('<batch name>', _get_flame_attr_str(flame.batch.name))
        except:
            pass
        
        actual_export_dir = os.path.join(resolved_path, clip_name)
        
        if not os.path.exists(actual_export_dir):
            os.makedirs(actual_export_dir, exist_ok=True)
        
        log(f"Pipeline export path: {actual_export_dir}")
        
        # Create symlink inside ComfyUI input
        comfy_link = os.path.join(export_folder, clip_name)
        
        # Remove existing symlink or directory
        if os.path.islink(comfy_link):
            os.unlink(comfy_link)
        elif os.path.exists(comfy_link):
            import shutil
            shutil.rmtree(comfy_link)
        
        os.symlink(actual_export_dir, comfy_link)
        log(f"Symlink created: {comfy_link} -> {actual_export_dir}")
        
        sequence_dir = actual_export_dir
    else:
        # Default: export directly to ComfyUI input
        sequence_dir = os.path.join(export_folder, clip_name)
    
    log(f"Exporting clip: {clip_name}")
    
    if not os.path.exists(sequence_dir):
        os.makedirs(sequence_dir)
    else:
        # Remove stale frames from previous exports (mixed formats/paddings
        # would corrupt the sequence when read back by FlameLoad).
        import glob as _glob
        for stale in _glob.glob(os.path.join(sequence_dir, "*")):
            if stale.lower().endswith(('.png', '.jpg', '.jpeg', '.exr', '.tif', '.tiff')):
                try:
                    os.remove(stale)
                except OSError:
                    pass
    
    if not os.path.exists(preset_path):
        log(f"ERROR: Preset not found at: {preset_path}")
        return None
    
    exporter = flame.PyExporter()
    exporter.foreground = True
    
    # Frame range handling using flame.duplicate() technique
    # Based on Autodesk's official export_current_frame.py example.
    # Duplicate the clip, set marks on the duplicate, export, then delete.
    # This works reliably for all clip types including BFX/cached clips.
    
    if frame_range is not None:
        try:
            exporter.export_between_marks = True
            
            # Duplicate clip to avoid modifying the original
            duplicate_clip = flame.duplicate(clip)
            
            try:
                # Preserve original name for file naming
                duplicate_clip.name = clip.name
                
                if frame_range == (0, 0):
                    # Current frame only
                    # out_mark = current_time + 1 because export_between_marks
                    # excludes the out_mark frame
                    ct = clip.current_time
                    if hasattr(ct, 'get_value'):
                        ct_val = ct.get_value()
                    elif hasattr(ct, 'frame'):
                        ct_val = ct.frame
                    else:
                        ct_val = ct
                    
                    duplicate_clip.in_mark = ct_val
                    duplicate_clip.out_mark = ct_val + 1
                    log(f"Exporting current frame: {ct_val} (duplicate + marks)")
                else:
                    # Custom range
                    start, end = frame_range
                    duplicate_clip.in_mark = start
                    duplicate_clip.out_mark = end + 1
                    log(f"Exporting range: {start}-{end} (duplicate + marks)")
                
                exporter.export(duplicate_clip, preset_path, sequence_dir)
                log("Export started (from duplicate)")
                
            finally:
                # Always clean up the duplicate
                try:
                    flame.delete(duplicate_clip)
                except:
                    pass
            
            return sequence_dir
            
        except Exception as e:
            log(f"Warning: Duplicate+marks export failed ({e}), falling back to full export")
            import traceback
            traceback.print_exc()
            # Fall through to full export below
    
    # Full export (all frames, or fallback)
    try:
        exporter.export(clip, preset_path, sequence_dir)
        log("Export started")
        return sequence_dir
    except Exception as e:
        log(f"Error during export: {e}")
        return None


def wait_for_sequence(sequence_dir, timeout=FILE_WAIT_TIMEOUT):
    """Wait for exported files to appear and stabilize.
    Uses folder-level size check instead of per-file polling."""
    log(f"Waiting for exported files...")
    
    start = time.time()
    
    while time.time() - start < timeout:
        if os.path.exists(sequence_dir):
            files = os.listdir(sequence_dir)
            image_files = [f for f in files if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))]
            
            if image_files:
                # Quick check: first file has content
                first_frame = os.path.join(sequence_dir, sorted(image_files)[0])
                if os.path.getsize(first_frame) > 0:
                    # Wait for folder size to stabilize (all files done writing)
                    total_size = sum(os.path.getsize(os.path.join(sequence_dir, f)) for f in image_files)
                    time.sleep(0.5)
                    # Re-check: count and total size must be stable
                    files2 = [f for f in os.listdir(sequence_dir) if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))]
                    total_size2 = sum(os.path.getsize(os.path.join(sequence_dir, f)) for f in files2)
                    
                    if len(files2) == len(image_files) and total_size == total_size2:
                        elapsed = time.time() - start
                        log(f"Export complete: {len(image_files)} files ({total_size / (1024*1024):.1f} MB) in {elapsed:.1f}s")
                        return sequence_dir
        
        time.sleep(0.3)
    
    log(f"Timeout: no exported files after {timeout}s")
    return None


# File magic headers for validation
_FILE_HEADERS = {
    '.png':  b'\x89PNG',
    '.exr':  b'\x76\x2f\x31\x01',
    '.tif':  (b'\x49\x49', b'\x4d\x4d'),  # Little-endian or Big-endian TIFF
    '.tiff': (b'\x49\x49', b'\x4d\x4d'),
    '.jpg':  b'\xff\xd8\xff',
    '.jpeg': b'\xff\xd8\xff',
}


def _validate_file_header(filepath):
    """Quick file header validation for any supported format."""
    ext = os.path.splitext(filepath)[1].lower()
    expected = _FILE_HEADERS.get(ext)
    if not expected:
        return True  # Unknown format, skip validation
    
    try:
        with open(filepath, 'rb') as f:
            header = f.read(8)
        
        if isinstance(expected, tuple):
            return any(header[:len(h)] == h for h in expected)
        return header[:len(expected)] == expected
    except:
        return False


def copy_to_comfyui(sequence_dir):
    """Copy/verify sequence for ComfyUI input.
    
    Optimized: in local mode, skips per-file verification entirely
    since Flame's PyExporter guarantees files are complete on return.
    In remote modes, uses folder-level size check instead of per-file sleep loops.
    """
    import shutil
    import glob as glob_module
    
    folder_name = os.path.basename(sequence_dir)
    comfy_dest = os.path.join(COMFY_INPUT_DIR, folder_name)
    
    # Count files (any supported format)
    all_images = [f for f in os.listdir(sequence_dir) 
                  if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))]
    file_count = len(all_images)
    
    # Detect if already exporting directly to input (no copy needed)
    if os.path.abspath(sequence_dir) == os.path.abspath(comfy_dest):
        log(f"Direct export to ComfyUI input - no copy needed")
        log(f"Ready: {file_count} files")
        return sequence_dir
    
    # Determine connection mode
    connection_mode = CONFIG.get('connection_mode', 'local')
    
    # MODE 1: LOCAL - Files already in place via symlink or direct export
    if connection_mode == 'local':
        # Quick header validation on first and last file only (spot check)
        if all_images:
            for check_file in [all_images[0], all_images[-1]]:
                fpath = os.path.join(sequence_dir, check_file)
                if not _validate_file_header(fpath):
                    log(f"Warning: {check_file} has invalid header")
        
        log(f"Local mode: files ready")
        log(f"Ready: {file_count} files")
        return sequence_dir
    
    # MODE 2: REMOTE SSH - Copy via SCP
    elif connection_mode == 'remote_ssh':
        import subprocess
        
        ssh_host = CONFIG.get('remote_ssh_host', '')
        remote_path = CONFIG.get('remote_path', '')
        
        if not ssh_host or not remote_path:
            log("ERROR: SSH mode active but host or path not configured")
            return None
        
        log(f"SSH mode: copying {file_count} files via SCP to {ssh_host}:{remote_path}")
        
        try:
            cmd = [
                'scp', '-r', '-q',
                sequence_dir,
                f"{ssh_host}:{remote_path}/"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode == 0:
                log(f"✓ SCP copy complete: {file_count} files")
                return sequence_dir
            else:
                log(f"SCP ERROR: {result.stderr}")
                return None
                
        except subprocess.TimeoutExpired:
            log("ERROR: SCP timeout (>120s)")
            return None
        except Exception as e:
            log(f"SCP ERROR: {e}")
            return None
    
    # MODE 3: NETWORK SHARE - Files already on shared mount
    elif connection_mode == 'network_share':
        # Verify files are accessible over the share
        if all_images:
            test_file = os.path.join(sequence_dir, all_images[0])
            if os.path.getsize(test_file) == 0:
                log("Warning: First file is empty, waiting for network sync...")
                time.sleep(2)
        
        log(f"Network share mode: files ready")
        log(f"Ready: {file_count} files")
        return sequence_dir
    
    else:
        log(f"ERROR: Unknown connection mode: {connection_mode}")
        return None


def export_and_load_workflow(selection, workflow_name, workflow_path, mode="auto"):
    """
    Fonction principale: exporte le clip et charge le workflow dans ComfyUI
    
    Args:
        selection: Selected clips in Flame
        workflow_name: Workflow name (for display)
        workflow_path: Path to workflow .json file
        mode: "auto" = immediate execution, "manual" = opens for review
    """
    import flame
    
    log("="*70)
    log(f"EXPORT TO COMFYUI - WORKFLOW: {workflow_name}")
    log(f"Mode: {mode.upper()}")
    log("="*70)
    
    # Check preset
    if not os.path.exists(PRESET_PATH):
        log(f"ERROR: Export preset not found: {PRESET_PATH}")
        flame.messages.show_in_console(f"Export preset missing: {os.path.basename(PRESET_PATH)}", duration=5)
        return
    
    # Check ComfyUI connection
    try:
        current_config = load_config()
        current_url = f"{current_config['comfy_url']}:{current_config['comfy_port']}"
        response = urllib.request.urlopen(f"{current_url}/system_stats", timeout=5)
        if response.status != 200:
            log("ComfyUI not accessible")
            flame.messages.show_in_console("ComfyUI not accessible", duration=5)
            return
    except Exception as e:
        log(f"ComfyUI not accessible at {current_url}: {e}")
        flame.messages.show_in_console(f"ComfyUI not accessible ({current_url})", duration=5)
        return
    
    # Load workflow
    log(f"\nLoading workflow: {workflow_name}")
    workflow, is_api_format = load_workflow_json(workflow_path)
    
    if not workflow:
        log("ERROR: Unable to load workflow")
        flame.messages.show_in_console("Invalid workflow", duration=5)
        return
    
    # In manual mode, we do NOT convert and do NOT execute
    if mode == "manual":
        log("Manual mode: no conversion needed")
        log("User will load workflow manually in ComfyUI")
    else:
        # Auto mode: convert if needed
        if not is_api_format:
            workflow = convert_normal_to_api_format(workflow)
            if not workflow:
                log("ERROR: Unable to convert workflow")
                flame.messages.show_in_console("Workflow conversion error", duration=5)
                return
    
    # =========================================================================
    # MULTI-CLIP DETECTION
    # =========================================================================
    flameload_nodes = count_flameload_nodes(workflow, is_api_format)
    num_flame_loads = len(flameload_nodes)
    num_clips = len(selection)
    
    # Extract all valid clips from selection
    clips = []
    for item in selection:
        clip = get_clip_from_item(item)
        if clip:
            clips.append(clip)
    
    if not clips:
        log("ERROR: No valid clips found in selection")
        return
    
    log(f"\nClips selected: {len(clips)}")
    log(f"FlameLoad nodes in workflow: {num_flame_loads}")
    
    # =========================================================================
    # FRAME RANGE + EXPORT FORMAT DIALOG
    # =========================================================================
    frame_range = None  # Default: all frames
    export_preset = PRESET_PATH  # Default from settings
    
    # Use first clip as reference for frame range
    ref_clip = clips[0]
    try:
        # Flame 2025: duration can be PyTime object or attribute with get_value()
        duration = ref_clip.duration
        if hasattr(duration, 'get_value'):
            total_frames = int(duration.get_value())
        elif hasattr(duration, 'frame'):
            total_frames = int(duration.frame)
        else:
            total_frames = int(duration)
        
        current_frame = 1
        try:
            ct = ref_clip.current_time
            if hasattr(ct, 'get_value'):
                current_frame = int(ct.get_value())
            elif hasattr(ct, 'frame'):
                current_frame = int(ct.frame)
            else:
                current_frame = int(ct)
        except:
            pass
        
        if total_frames > 1:
            # Get clip name safely
            cname = ref_clip.name
            if hasattr(cname, 'get_value'):
                cname = cname.get_value()
            
            range_dialog = FrameRangeDialog(
                str(cname),
                total_frames,
                current_frame
            )
            if range_dialog.exec_() != QtWidgets.QDialog.Accepted:
                log("User cancelled export")
                return
            frame_range = range_dialog.get_range()
            
            # Check if user selected a different export format
            if hasattr(range_dialog, 'get_export_format'):
                selected_format = range_dialog.get_export_format()
                if selected_format and selected_format != CONFIG.get('export_format', ''):
                    export_preset = get_preset_path_for_format(selected_format)
                    log(f"Export format override: {selected_format}")
            
            if frame_range is None:
                log(f"Exporting all {total_frames} frames")
            elif frame_range == (0, 0):
                log(f"Exporting current frame only")
            else:
                log(f"Exporting frames {frame_range[0]}-{frame_range[1]}")
    except Exception as e:
        log(f"Could not determine frame count: {e}")
        import traceback
        traceback.print_exc()
    
    # Determine mode: batch vs multi-input
    if num_flame_loads <= 1:
        # =====================================================================
        # BATCH MODE: 1 FlameLoad, run workflow once per clip
        # =====================================================================
        if len(clips) > 1:
            log(f"BATCH MODE: Running workflow {len(clips)} times")
        
        _cached_prompts = None
        _cached_output_mode = "matte"
        _cached_key_frame = 0
        _cached_colour_space = "bt709"
        _cached_mask_quality = (0.5, 2, 3, 0)
        
        for clip_idx, clip in enumerate(clips):
            clip_name = clip.name.get_value()
            log(f"\n--- Processing clip {clip_idx + 1}/{len(clips)}: {clip_name} ---")
            
            # Check if export already exists
            sanitized = sanitize_filename(clip_name)
            existing_dir = os.path.join(COMFY_INPUT_DIR, sanitized)
            skip_export = False
            
            if os.path.exists(existing_dir):
                existing_files = [f for f in os.listdir(existing_dir) if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))]
                if existing_files:
                    dlg = QtWidgets.QDialog()
                    dlg.setWindowTitle("Existing Export Found")
                    dlg.setMinimumWidth(480)
                    dlg.setStyleSheet(get_flame_stylesheet())
                    layout = QtWidgets.QVBoxLayout(dlg)
                    layout.setContentsMargins(24, 24, 24, 24)
                    layout.setSpacing(12)
                    lbl = QtWidgets.QLabel(
                        f"Clip <b>{clip_name}</b> already has {len(existing_files)} "
                        f"exported frame(s).<br><br><small>{existing_dir}</small>"
                    )
                    lbl.setWordWrap(True)
                    layout.addWidget(lbl)
                    layout.addSpacing(8)
                    btn_layout = QtWidgets.QHBoxLayout()
                    btn_layout.addStretch()
                    cancel_btn = QtWidgets.QPushButton("Cancel")
                    cancel_btn.setMinimumSize(100, 28)
                    cancel_btn.clicked.connect(lambda: dlg.done(0))
                    reexport_btn = QtWidgets.QPushButton("Re-export")
                    reexport_btn.setMinimumSize(100, 28)
                    reexport_btn.clicked.connect(lambda: dlg.done(2))
                    use_btn = QtWidgets.QPushButton("Use Existing")
                    use_btn.setObjectName("primary")
                    use_btn.setMinimumSize(120, 28)
                    use_btn.setDefault(True)
                    use_btn.clicked.connect(lambda: dlg.done(1))
                    btn_layout.addWidget(cancel_btn)
                    btn_layout.addWidget(reexport_btn)
                    btn_layout.addWidget(use_btn)
                    layout.addLayout(btn_layout)
                    choice = dlg.exec_()
                    if choice == 0:
                        log("User cancelled")
                        return
                    elif choice == 1:
                        skip_export = True
                        log(f"Using existing export: {len(existing_files)} files")
            
            # 1. Export (or skip)
            if skip_export:
                sequence_dir = existing_dir
            else:
                sequence_dir = export_clip_for_comfyui(clip, export_preset, COMFY_INPUT_DIR, frame_range)
                if not sequence_dir:
                    log(f"ERROR: Export failed for {clip_name}")
                    continue
                
                # 2. Wait for export
                exported_dir = wait_for_sequence(sequence_dir)
                if not exported_dir:
                    log(f"ERROR: Export timeout for {clip_name}")
                    continue
            
            # 3. Copy to ComfyUI (or use existing)
            if skip_export:
                comfy_path = sequence_dir
            else:
                comfy_path = copy_to_comfyui(exported_dir)
            clip_folder_name = os.path.basename(comfy_path)
            exported_files = sorted([f for f in os.listdir(comfy_path) if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))])
            
            if not exported_files:
                log(f"ERROR: No PNG files found for {clip_name}")
                continue
            
            first_file_relative = os.path.join(clip_folder_name, exported_files[0])
            
            if mode == "auto":
                if not is_api_format:
                    log("WARNING: Workflow is not in API format")
                    flame.messages.show_in_console("Workflow must be in API format for Auto mode", duration=7)
                    return
                
                # Make a fresh copy of workflow for each clip
                import copy
                clip_workflow = copy.deepcopy(workflow)
                
                # Inject image path
                log(f"Injecting image path: {first_file_relative}")
                clip_workflow = inject_image_path_in_workflow(clip_workflow, first_file_relative, is_api_format)
                
                # Show prompt dialog (only for first clip, or if single clip)
                if clip_idx == 0:
                    text_nodes = get_text_nodes(clip_workflow, is_api_format)
                    if text_nodes:
                        prompt_dialog = PromptDialog(text_nodes, workflow_name)
                        result = prompt_dialog.exec_()
                        
                        if result == QtWidgets.QDialog.Rejected:
                            log("User cancelled")
                            return
                        elif result == QtWidgets.QDialog.Accepted:
                            # User edited prompts
                            user_prompts = prompt_dialog.get_prompts()
                            clip_workflow = inject_prompts_in_workflow(clip_workflow, user_prompts, is_api_format)
                            # Apply alpha composite if requested
                            if prompt_dialog.get_output_mode() == "alpha":
                                clip_workflow = inject_alpha_composite_in_workflow(clip_workflow, is_api_format)
                            # Apply key frame if non-zero
                            key_frame = prompt_dialog.get_key_frame()
                            if key_frame != 0:
                                clip_workflow = inject_key_frame_in_workflow(clip_workflow, key_frame, is_api_format)
                            # Apply colour space tag (ProRes metadata)
                            colour_space = prompt_dialog.get_colour_space()
                            clip_workflow = inject_colour_space_in_workflow(clip_workflow, colour_space, is_api_format)
                            # Apply mask quality (SAM3 threshold/refine + MatAnyone dilate/erode)
                            threshold, refine, r_dilate, r_erode = prompt_dialog.get_mask_quality()
                            clip_workflow = inject_mask_quality_in_workflow(clip_workflow, threshold, refine, r_dilate, r_erode, is_api_format)
                            # Store for subsequent clips in batch
                            _cached_prompts = user_prompts
                            _cached_output_mode = prompt_dialog.get_output_mode()
                            _cached_key_frame = key_frame
                            _cached_colour_space = colour_space
                            _cached_mask_quality = prompt_dialog.get_mask_quality()
                        # result == 2 means "Skip" - use defaults
                        else:
                            _cached_prompts = None
                    else:
                        _cached_prompts = None
                elif _cached_prompts:
                    # Reuse prompts from first dialog for batch
                    clip_workflow = inject_prompts_in_workflow(clip_workflow, _cached_prompts, is_api_format)
                    if _cached_output_mode == "alpha":
                        clip_workflow = inject_alpha_composite_in_workflow(clip_workflow, is_api_format)
                    if _cached_key_frame != 0:
                        clip_workflow = inject_key_frame_in_workflow(clip_workflow, _cached_key_frame, is_api_format)
                    clip_workflow = inject_colour_space_in_workflow(clip_workflow, _cached_colour_space, is_api_format)
                    _threshold, _refine, _dilate, _erode = _cached_mask_quality
                    clip_workflow = inject_mask_quality_in_workflow(clip_workflow, _threshold, _refine, _dilate, _erode, is_api_format)
                
                # Send to ComfyUI
                result = send_workflow_to_comfyui(clip_workflow, workflow_name)
                
                if result:
                    log(f"Workflow sent for {clip_name}")
                    if CONFIG['show_notifications']:
                        flame.messages.show_in_console(
                            f"ComfyUI processing '{clip_name}' ({clip_idx + 1}/{len(clips)})",
                            duration=3
                        )
                else:
                    log(f"ERROR: Failed to send workflow for {clip_name}")
            
            else:
                # Manual mode - only first clip
                clip_folder_name = os.path.basename(comfy_path)
                
                if CONFIG['open_browser_manual']:
                    import webbrowser
                    webbrowser.open(COMFY_URL)
                
                import threading
                def inject_workflow_async():
                    workflow_filename = load_workflow_in_comfyui_interface(workflow_path, workflow_name, clip_folder_name)
                    if not workflow_filename:
                        log("ERROR: Unable to prepare workflow")
                
                thread = threading.Thread(target=inject_workflow_async, daemon=True)
                thread.start()
                
                log("Manual mode - work freely in ComfyUI")
                log("Result will be auto-imported via background watcher")
                break  # Only first clip in manual mode
        
        if mode == "auto" and len(clips) > 1:
            log(f"\n{'='*70}")
            log(f"BATCH COMPLETE: {len(clips)} workflows sent")
            log(f"{'='*70}")
            if CONFIG['auto_import']:
                log("Results will be auto-imported via background watcher")
    
    else:
        # =====================================================================
        # MULTI-INPUT MODE: Multiple FlameLoad nodes, single execution
        # =====================================================================
        log(f"MULTI-INPUT MODE: {num_flame_loads} inputs expected")
        
        if len(clips) < num_flame_loads:
            log(f"WARNING: Workflow expects {num_flame_loads} inputs but only {len(clips)} clips selected")
            flame.messages.show_in_console(
                f"Select {num_flame_loads} clips for this workflow ({len(clips)} selected)",
                duration=5
            )
            # Continue anyway - unmatched FlameLoad nodes keep their defaults
        
        # Show assignment dialog if more than 1 FlameLoad
        clip_names = [c.name.get_value() for c in clips]
        
        assign_dialog = MultiClipAssignDialog(clip_names, flameload_nodes)
        if assign_dialog.exec_() != QtWidgets.QDialog.Accepted:
            log("User cancelled assignment")
            return
        
        assignments = assign_dialog.get_assignments()
        log(f"Assignments: {assignments}")
        
        # Export all clips
        clip_folders = []
        for clip in clips:
            clip_name = clip.name.get_value()
            log(f"\nExporting: {clip_name}")
            
            # Check if export already exists
            sanitized = sanitize_filename(clip_name)
            existing_dir = os.path.join(COMFY_INPUT_DIR, sanitized)
            skip_export = False
            
            if os.path.exists(existing_dir):
                existing_files = [f for f in os.listdir(existing_dir) if f.lower().endswith(('.png', '.exr', '.tif', '.tiff', '.jpg', '.jpeg'))]
                if existing_files:
                    msg = QtWidgets.QMessageBox()
                    msg.setWindowTitle("Existing Export Found")
                    msg.setText(
                        f"Clip '{clip_name}' already has {len(existing_files)} "
                        f"exported frame(s)."
                    )
                    msg.setInformativeText("Use existing export or re-export?")
                    msg.setStyleSheet(get_flame_stylesheet())
                    use_btn = msg.addButton("Use Existing", QtWidgets.QMessageBox.AcceptRole)
                    reexport_btn = msg.addButton("Re-export", QtWidgets.QMessageBox.DestructiveRole)
                    msg.exec_()
                    if msg.clickedButton() == use_btn:
                        skip_export = True
                        log(f"Using existing export: {len(existing_files)} files")
            
            if skip_export:
                clip_folders.append(sanitized)
            else:
                sequence_dir = export_clip_for_comfyui(clip, export_preset, COMFY_INPUT_DIR, frame_range)
                if not sequence_dir:
                    log(f"ERROR: Export failed for {clip_name}")
                    clip_folders.append(None)
                    continue
                
                exported_dir = wait_for_sequence(sequence_dir)
                if not exported_dir:
                    log(f"ERROR: Export timeout for {clip_name}")
                    clip_folders.append(None)
                    continue
                
                comfy_path = copy_to_comfyui(exported_dir)
                clip_folders.append(os.path.basename(comfy_path))
        
        # Check we have all needed folders
        valid_folders = [f for f in clip_folders if f is not None]
        if not valid_folders:
            log("ERROR: No clips exported successfully")
            return
        
        if mode == "auto":
            if not is_api_format:
                log("WARNING: Workflow is not in API format")
                flame.messages.show_in_console("Workflow must be in API format for Auto mode", duration=7)
                return
            
            # Inject all clips into their FlameLoad nodes
            workflow = inject_multi_clip_in_workflow(workflow, clip_folders, assignments, is_api_format)
            
            # Show prompt dialog
            text_nodes = get_text_nodes(workflow, is_api_format)
            if text_nodes:
                prompt_dialog = PromptDialog(text_nodes, workflow_name)
                result = prompt_dialog.exec_()
                
                if result == QtWidgets.QDialog.Rejected:
                    log("User cancelled")
                    return
                elif result == QtWidgets.QDialog.Accepted:
                    user_prompts = prompt_dialog.get_prompts()
                    workflow = inject_prompts_in_workflow(workflow, user_prompts, is_api_format)
                    if prompt_dialog.get_output_mode() == "alpha":
                        workflow = inject_alpha_composite_in_workflow(workflow, is_api_format)
                    workflow = inject_colour_space_in_workflow(workflow, prompt_dialog.get_colour_space(), is_api_format)
                    _t, _r, _d, _e = prompt_dialog.get_mask_quality()
                    workflow = inject_mask_quality_in_workflow(workflow, _t, _r, _d, _e, is_api_format)
                # result == 2 means "Skip" - use defaults
            
            # Send to ComfyUI
            result = send_workflow_to_comfyui(workflow, workflow_name)
            
            if result:
                log("\n" + "="*70)
                log("MULTI-INPUT WORKFLOW SENT!")
                log("="*70)
                log(f"Workflow: {workflow_name}")
                log(f"Inputs: {len(valid_folders)} clips")
                log("="*70)
                
                if CONFIG['auto_import']:
                    log("Result will be auto-imported via background watcher")
                    if CONFIG['show_notifications']:
                        flame.messages.show_in_console(
                            f"ComfyUI processing '{workflow_name}' with {len(valid_folders)} inputs",
                            duration=5
                        )
            else:
                log("ERROR: Failed to send workflow")
                flame.messages.show_in_console("Error - check console", duration=5)
        
        else:
            # Manual mode with multi-input
            if CONFIG['open_browser_manual']:
                import webbrowser
                webbrowser.open(COMFY_URL)
            
            # Use first clip folder for manual workflow prep
            first_folder = valid_folders[0] if valid_folders else ""
            
            import threading
            def inject_workflow_async():
                workflow_filename = load_workflow_in_comfyui_interface(workflow_path, workflow_name, first_folder)
                if not workflow_filename:
                    log("ERROR: Unable to prepare workflow")
            
            thread = threading.Thread(target=inject_workflow_async, daemon=True)
            thread.start()
            
            log("Manual mode - assign clips manually in ComfyUI")
            log("Result will be auto-imported via background watcher")


def create_workflow_action(workflow_name, workflow_path):
    """
    Create a menu action for a workflow
    Mode (Auto/Manual) is auto-detected from workflow format:
    - API format -> Auto mode (immediate execution)
    - Normal format -> Manual mode (opens in interface)
    
    Returns:
        dict: Menu action
    """
    def execute_workflow(selection):
        # Load workflow to detect its format
        workflow, is_api_format = load_workflow_json(workflow_path)
        
        if workflow is None:
            log(f"ERROR: Unable to load workflow: {workflow_name}")
            return
        
        # Auto-detect mode from format
        mode = "auto" if is_api_format else "manual"
        log(f"Mode detected for '{workflow_name}': {mode.upper()} (format {'API' if is_api_format else 'Normal'})")
        
        export_and_load_workflow(selection, workflow_name, workflow_path, mode=mode)
    
    # Return a single action
    return {
        'name': workflow_name,
        'execute': execute_workflow,
        'minimumVersion': '2025'
    }


def scope_clip(selection):
    """Determine if menu should be visible"""
    import flame
    return any(isinstance(item, (flame.PyClip, flame.PySequence)) for item in selection)


def get_media_panel_custom_ui_actions():
    """Context menu in Media Panel with favorite workflows and manager"""
    global CONFIG
    CONFIG = load_config()
    
    # Get workflow list
    workflows = get_available_workflows()
    favorites = CONFIG.get('favorite_workflows', [])
    
    actions = []
    
    # Add favorite workflows first
    # Space prefix (ASCII 32) to force ordering avant '---' (ASCII 45)
    if favorites and workflows:
        favorite_workflows = [(name, path) for name, path in workflows if name in favorites]
        for workflow_name, workflow_path in favorite_workflows:
            workflow_action = create_workflow_action(workflow_name, workflow_path)
            workflow_action['name'] = ' ' + workflow_name  # espace force le tri avant ---
            actions.append(workflow_action)
    
    # Separator (--- est apres espace, avant les lettres)
    actions.append({
        'name': '---',
        'isVisible': lambda sel: True,
        'isEnabled': lambda sel: False
    })

    # Action "Workflows..." (W avant ~)
    def open_workflow_manager(selection):
        show_workflow_manager(selection=selection)
    
    actions.append({
        'name': 'Workflows...',
        'execute': open_workflow_manager,
        'minimumVersion': '2025'
    })

    # Settings action — ~ prefix (ASCII 126) to be at bottom
    def open_settings(selection):
        show_settings_dialog()
    
    actions.append({
        'name': '~Settings...',
        'execute': open_settings,
        'minimumVersion': '2025'
    })
    
    return [{
        'name': 'ComfyUI',
        'actions': actions
    }]


def get_batch_custom_ui_actions():
    """Context menu in Batch"""
    return get_media_panel_custom_ui_actions()


def initialize():
    """Initialization"""
    log("\n" + "="*70)
    log(f"ComfyUI Integration v{__version__} - CHARGE")
    log("="*70)
    log(f"   ComfyUI URL: {COMFY_URL}")
    log(f"   Input dir: {COMFY_INPUT_DIR}")
    log(f"   Output dir: {COMFY_OUTPUT_DIR}")
    log(f"   Workflows dir: {WORKFLOWS_DIR}")
    log(f"   Auto-import: {'ON' if CONFIG['auto_import'] else 'OFF'}")
    log(f"   Timeout: {CONFIG['timeout']}s")
    log(f"   Config file: {CONFIG_FILE}")
    
    # Create directories
    for directory in [COMFY_INPUT_DIR, WORKFLOWS_DIR]:
        if not os.path.exists(directory):
            try:
                os.makedirs(directory)
                log(f"   Folder created: {directory}")
            except Exception as e:
                log(f"   Error: {directory}: {e}")
    
    # Check output folder (peut etre monte via SSHFS)
    if os.path.exists(COMFY_OUTPUT_DIR):
        log(f"   Output accessible: OK")
    else:
        log(f"   WARNING: Output dir not accessible (normal if ComfyUI is remote)")
        log(f"   Folder will be created by ComfyUI on first export")
    
    # List available workflows
    workflows = get_available_workflows()
    
    if workflows:
        log(f"\n   Available workflows ({len(workflows)}):")
        for name, path in workflows:
            log(f"      - {name}")
    else:
        log(f"\n   No workflows found in: {WORKFLOWS_DIR}")
        log(f"   Add .json files (ComfyUI workflows)")
    
    log("\n   Context menu: Clip > ComfyUI > [Workflows...]")
    log("   Settings: Clip > ComfyUI > Settings...")
    log("="*70 + "\n")
    
    # Start watcher if auto-import is enabled
    if CONFIG['auto_import'] and comfy_watcher:
        try:
            # Determine pipeline notification path (for remote/network imports)
            pipeline_notif = None
            pipeline_result = CONFIG.get('pipeline_result_path', '').strip()
            if pipeline_result:
                resolved = resolve_flame_tokens(pipeline_result)
                if resolved and os.path.isdir(resolved):
                    pipeline_notif = os.path.join(resolved, 'notification.json')
                    log(f"[ComfyUI] Pipeline notification path: {pipeline_notif}")
            
            comfy_watcher.start_watcher(COMFY_OUTPUT_DIR, FLAME_NOTIFICATION_FILE,
                                         pipeline_notification_file=pipeline_notif)
            log("[ComfyUI] Watcher started (auto-import enabled)")
        except Exception as e:
            log(f"[ComfyUI] Watcher error: {e}")


try:
    initialize()
except Exception as e:
    print(f"[ComfyUI] Initialization ERROR: {e}")
    print("[ComfyUI] Menu will still be available")
