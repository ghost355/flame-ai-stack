"""
PyFlame Library for SammieRoto RoundTrip
Version: 2.0.0
Based on PyFlame Library v4.0.0 by Michael Vaglienty

This is a minimal subset of the PyFlame Library containing only the widgets
needed for the SammieRoto RoundTrip script.
"""

import os
from typing import Optional, Callable, List
from PySide6 import QtCore, QtGui, QtWidgets

# ============================================
# Constants
# ============================================

PYFLAME_FONT = 'Discreet'
PYFLAME_FONT_SIZE = 13

# ============================================
# Color Definitions
# ============================================

class Color:
    BLUE = 'rgb(0, 110, 175)'
    GRAY = 'rgb(58, 58, 58)'
    WHITE = 'rgb(255, 255, 255)'
    TEXT = 'rgb(154, 154, 154)'
    TEXT_SELECTED = 'rgb(210, 210, 210)'
    TEXT_DISABLED = 'rgb(100, 100, 100)'
    BORDER = 'rgb(90, 90, 90)'
    DISABLED_GRAY = 'rgb(54, 54, 54)'
    RED = 'rgb(200, 29, 29)'
    GREEN = 'rgb(0, 150, 64)'
    DARK_BG = 'rgb(36, 36, 36)'
    MID_BG = 'rgb(45, 45, 45)'
    INPUT_BG = 'rgb(55, 65, 75)'
    INPUT_FOCUS = 'rgb(73, 86, 99)'

# ============================================
# Utility Functions
# ============================================

class _PyFlameFunctions:
    """PyFlame utility functions"""

    @staticmethod
    def gui_resize(value: int) -> int:
        """Scale UI elements for different resolutions"""
        return value

    @staticmethod
    def font_resize(value: int) -> int:
        """Scale font size"""
        return value

pyflame = _PyFlameFunctions()

# ============================================
# Widget Classes
# ============================================

class PyFlameLabel(QtWidgets.QLabel):
    """Custom Flame Label Widget"""

    def __init__(self,
                 text: str,
                 width: int = 150,
                 height: int = 28,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE):
        super().__init__()

        label_font = QtGui.QFont(font)
        label_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(label_font)

        self.setText(text)
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))
        self.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)

        self.setStyleSheet(f"""
            QLabel {{
                color: {Color.TEXT};
            }}
        """)


class PyFlameLineEdit(QtWidgets.QLineEdit):
    """Custom Flame Line Edit Widget"""

    def __init__(self,
                 text: str = '',
                 width: int = 150,
                 height: int = 28,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE,
                 placeholder: str = ''):
        super().__init__()

        edit_font = QtGui.QFont(font)
        edit_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(edit_font)

        self.setText(text)
        if placeholder:
            self.setPlaceholderText(placeholder)
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))

        self.setStyleSheet(f"""
            QLineEdit {{
                color: {Color.TEXT};
                background-color: {Color.INPUT_BG};
                border: 1px solid {Color.INPUT_BG};
                selection-color: rgb(38, 38, 38);
                selection-background-color: rgb(184, 177, 167);
                padding-left: 5px;
            }}
            QLineEdit:focus {{
                background-color: {Color.INPUT_FOCUS};
            }}
            QLineEdit:hover {{
                border: 1px solid {Color.BORDER};
            }}
            QLineEdit:read-only {{
                color: {Color.TEXT_SELECTED};
                background-color: {Color.MID_BG};
                border: 1px solid {Color.BORDER};
            }}
        """)


class PyFlameButton(QtWidgets.QPushButton):
    """Custom Flame Button Widget"""

    def __init__(self,
                 text: str,
                 connect: Callable,
                 width: int = 110,
                 height: int = 28,
                 color: str = Color.GRAY,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE,
                 enabled: bool = True):
        super().__init__()

        button_font = QtGui.QFont(font)
        button_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(button_font)

        self.setText(text)
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))
        self.clicked.connect(connect)
        self.setEnabled(enabled)

        if color == Color.BLUE:
            bg_color = Color.BLUE
            text_color = 'rgb(185, 185, 185)'
        elif color == Color.RED:
            bg_color = Color.RED
            text_color = 'rgb(200, 200, 200)'
        else:
            bg_color = Color.GRAY
            text_color = 'rgb(165, 165, 165)'

        self.setStyleSheet(f"""
            QPushButton {{
                color: {text_color};
                background-color: {bg_color};
                border: none;
            }}
            QPushButton:hover {{
                border: 1px solid {Color.BORDER};
            }}
            QPushButton:pressed {{
                color: {Color.TEXT_SELECTED};
                background-color: rgb(71, 71, 71);
            }}
            QPushButton:disabled {{
                color: rgb(100, 100, 100);
                background-color: {Color.DISABLED_GRAY};
            }}
        """)


class PyFlameWindow(QtWidgets.QWidget):
    """Custom Flame Window Widget"""

    def __init__(self,
                 title: str = 'Python Script',
                 width: int = 500,
                 height: int = 400,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE):
        super().__init__()

        window_font = QtGui.QFont(font)
        window_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(window_font)

        self.setWindowTitle(title)
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))
        self.setWindowFlags(QtCore.Qt.Window | QtCore.Qt.WindowStaysOnTopHint)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Color.DARK_BG};
                color: {Color.TEXT};
            }}
        """)

        # Main layout
        self.main_layout = QtWidgets.QVBoxLayout()
        self.setLayout(self.main_layout)

        # Title
        title_label = QtWidgets.QLabel(title)
        title_font = QtGui.QFont(font)
        title_font.setPointSize(pyflame.font_resize(18))
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {Color.TEXT};
                padding: 10px;
                border-bottom: 1px solid {Color.BLUE};
            }}
        """)
        self.main_layout.addWidget(title_label)

        # Content layout
        self.content_layout = QtWidgets.QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(10)
        self.main_layout.addLayout(self.content_layout)

        # Center window on screen
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )


class PyFlameDialog(QtWidgets.QDialog):
    """Custom Flame Dialog Widget"""

    def __init__(self,
                 title: str = 'Dialog',
                 width: int = 500,
                 height: int = 300,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE,
                 parent=None):
        super().__init__(parent)

        dialog_font = QtGui.QFont(font)
        dialog_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(dialog_font)

        self.setWindowTitle(title)
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowStaysOnTopHint)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Color.DARK_BG};
                color: {Color.TEXT};
            }}
        """)

        # Main layout
        self.main_layout = QtWidgets.QVBoxLayout()
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self.main_layout)

        # Title bar
        title_label = QtWidgets.QLabel(title)
        title_font = QtGui.QFont(font)
        title_font.setPointSize(pyflame.font_resize(16))
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {Color.TEXT};
                padding: 10px 15px;
                background-color: {Color.DARK_BG};
                border-bottom: 1px solid {Color.BLUE};
            }}
        """)
        self.main_layout.addWidget(title_label)

        # Content layout
        self.content_layout = QtWidgets.QVBoxLayout()
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(12)
        self.main_layout.addLayout(self.content_layout)

        # Center on screen
        screen = QtWidgets.QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )


class PyFlameTokenPushButton(QtWidgets.QPushButton):
    """
    Custom Flame Token Picker Button.
    Shows a popup menu with all available Flame tokens.
    Inserts the selected token at the cursor position of the target QLineEdit.
    """

    # Flame 2025/2026 compatible tokens
    FLAME_TOKENS = {
        'Project': [
            ('{project_name_raw}', 'Project Name (raw string)'),
            ('{nickname_raw}', 'Project Nickname (raw string)'),
        ],
        'Clip': [
            ('{clip_name}', 'Clip Name'),
            ('{shot_name}', 'Shot Name (from timeline segment)'),
        ],
        'Batch': [
            ('{batch_name}', 'Batch Group Name'),
            ('{batch_iteration}', 'Batch Iteration Number'),
        ],
        'User': [
            ('{user_name}', 'Flame User Name'),
        ],
        'Date / Time': [
            ('{date_YYYY}', 'Year (4 digits)'),
            ('{date_MM}', 'Month (2 digits)'),
            ('{date_DD}', 'Day (2 digits)'),
            ('{date_YYYY_MM_DD}', 'Full Date (YYYY-MM-DD)'),
            ('{timestamp}', 'Unix Timestamp'),
        ],
    }

    token_selected = QtCore.Signal(str)

    def __init__(self,
                 target_line_edit: QtWidgets.QLineEdit = None,
                 width: int = 100,
                 height: int = 28,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE):
        super().__init__()

        self.target_line_edit = target_line_edit

        button_font = QtGui.QFont(font)
        button_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(button_font)

        self.setText('Tokens ▾')
        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))

        self.setStyleSheet(f"""
            QPushButton {{
                color: rgb(185, 185, 185);
                background-color: {Color.BLUE};
                border: none;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                border: 1px solid {Color.BORDER};
            }}
            QPushButton:pressed {{
                color: {Color.TEXT_SELECTED};
                background-color: rgb(71, 71, 71);
            }}
        """)

        # Build menu
        self._menu = QtWidgets.QMenu(self)
        self._menu.setStyleSheet(f"""
            QMenu {{
                background-color: {Color.MID_BG};
                color: {Color.TEXT};
                border: 1px solid {Color.BORDER};
                padding: 4px 0;
            }}
            QMenu::item {{
                padding: 6px 20px 6px 12px;
            }}
            QMenu::item:selected {{
                background-color: {Color.BLUE};
                color: {Color.TEXT_SELECTED};
            }}
            QMenu::separator {{
                height: 1px;
                background: {Color.BORDER};
                margin: 4px 8px;
            }}
            QMenu::item:disabled {{
                color: rgb(120, 120, 120);
                background-color: transparent;
                font-weight: bold;
            }}
        """)

        for category, tokens in self.FLAME_TOKENS.items():
            # Category header (disabled = non-clickable label)
            header_action = self._menu.addAction(f'── {category} ──')
            header_action.setEnabled(False)

            for token_str, description in tokens:
                action = self._menu.addAction(f'  {token_str}    ({description})')
                action.setData(token_str)
                action.triggered.connect(lambda checked=False, t=token_str: self._insert_token(t))

            self._menu.addSeparator()

        self.clicked.connect(self._show_menu)

    def _show_menu(self):
        """Show the token menu below the button"""
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        self._menu.exec(pos)

    def _insert_token(self, token: str):
        """Insert the token at cursor position in target line edit"""
        if self.target_line_edit:
            cursor_pos = self.target_line_edit.cursorPosition()
            current_text = self.target_line_edit.text()
            new_text = current_text[:cursor_pos] + token + current_text[cursor_pos:]
            self.target_line_edit.setText(new_text)
            self.target_line_edit.setCursorPosition(cursor_pos + len(token))
            self.target_line_edit.setFocus()

        self.token_selected.emit(token)


class PyFlameListWidget(QtWidgets.QListWidget):
    """Custom Flame styled list widget with checkboxes"""

    def __init__(self,
                 width: int = 400,
                 height: int = 200,
                 font: str = PYFLAME_FONT,
                 font_size: int = PYFLAME_FONT_SIZE):
        super().__init__()

        list_font = QtGui.QFont(font)
        list_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(list_font)

        self.setMinimumSize(pyflame.gui_resize(width), pyflame.gui_resize(height))
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)

        self.setStyleSheet(f"""
            QListWidget {{
                background-color: {Color.MID_BG};
                color: {Color.TEXT};
                border: 1px solid {Color.BORDER};
                outline: none;
            }}
            QListWidget::item {{
                padding: 4px 8px;
                border-bottom: 1px solid rgb(50, 50, 50);
            }}
            QListWidget::item:selected {{
                background-color: {Color.BLUE};
                color: {Color.TEXT_SELECTED};
            }}
            QListWidget::item:hover {{
                background-color: rgb(55, 55, 55);
            }}
            QListWidget::indicator {{
                width: 14px;
                height: 14px;
            }}
            QListWidget::indicator:unchecked {{
                border: 1px solid {Color.BORDER};
                background-color: {Color.MID_BG};
            }}
            QListWidget::indicator:checked {{
                border: 1px solid {Color.BLUE};
                background-color: {Color.BLUE};
            }}
            QScrollBar:vertical {{
                background: {Color.DARK_BG};
                width: 12px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {Color.BORDER};
                min-height: 20px;
                border-radius: 3px;
                margin: 2px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)


class PyFlameStatusBar(QtWidgets.QLabel):
    """Custom status bar label for feedback messages"""

    def __init__(self,
                 text: str = '',
                 font: str = PYFLAME_FONT,
                 font_size: int = 11):
        super().__init__()

        status_font = QtGui.QFont(font)
        status_font.setPointSize(pyflame.font_resize(font_size))
        self.setFont(status_font)

        self.setText(text)
        self.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        self.setMinimumHeight(pyflame.gui_resize(24))

        self._default_style = f"""
            QLabel {{
                color: rgb(120, 120, 120);
                padding-left: 4px;
                font-style: italic;
            }}
        """
        self.setStyleSheet(self._default_style)

    def set_info(self, text: str):
        self.setText(text)
        self.setStyleSheet(self._default_style)

    def set_success(self, text: str):
        self.setText(text)
        self.setStyleSheet(f"""
            QLabel {{
                color: {Color.GREEN};
                padding-left: 4px;
                font-style: italic;
            }}
        """)

    def set_error(self, text: str):
        self.setText(text)
        self.setStyleSheet(f"""
            QLabel {{
                color: {Color.RED};
                padding-left: 4px;
                font-style: italic;
            }}
        """)

    def set_warning(self, text: str):
        self.setText(text)
        self.setStyleSheet(f"""
            QLabel {{
                color: rgb(200, 160, 0);
                padding-left: 4px;
                font-style: italic;
            }}
        """)
