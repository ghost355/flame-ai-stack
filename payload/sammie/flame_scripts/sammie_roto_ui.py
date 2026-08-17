"""
SammieRoto RoundTrip - User Interface Module
Version: 2.0.0

This module contains all UI components for the SammieRoto RoundTrip script,
styled according to the PyFlame Library design standards.

New in v2.0:
- Token Picker button for Export Path Template (Flame 2025/2026 tokens)
- Robust Import Dialog with file scanning, multi-select, rescan
- Path preview with live token resolution
- Status bar feedback
"""

import os
import re
import time
from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog

from pyflame_lib_sammie_roto import (
    PyFlameWindow,
    PyFlameDialog,
    PyFlameLabel,
    PyFlameLineEdit,
    PyFlameButton,
    PyFlameTokenPushButton,
    PyFlameListWidget,
    PyFlameStatusBar,
    Color,
    PYFLAME_FONT,
    PYFLAME_FONT_SIZE,
    pyflame
)


# ============================================
# Helper: Sequence Detection
# ============================================

def detect_sequences_in_directory(directory):
    """
    Scan a directory and detect image sequences, video files, and single files.
    
    - Image sequences are grouped by base name + extension + padding
    - Video files are listed individually
    - Single images (not part of a sequence) are listed individually
    - ANY file type is shown so nothing is hidden from the user
    
    Returns a list of dicts:
    [
        {
            'name': 'matte_body',
            'pattern': 'matte_body.####.exr',
            'first_file': 'matte_body.0001.exr',
            'start_frame': 1,
            'end_frame': 100,
            'frame_count': 100,
            'extension': '.exr',
            'directory': '/path/to/dir',
            'import_pattern': '/path/to/dir/matte_body.[0001-0100].exr',
            'is_sequence': True,
            'file_type': 'sequence'  # 'sequence', 'video', 'single_image', 'other'
        },
        ...
    ]
    """
    if not os.path.exists(directory):
        return []

    # --- Classify all files in the directory ---
    image_extensions = (
        '.jpg', '.jpeg', '.tif', '.tiff', '.exr', '.png', '.dpx',
        '.bmp', '.sgi', '.rgb', '.psd', '.hdr', '.pic', '.ppm',
        '.tga', '.cin', '.als',
    )
    video_extensions = (
        '.mov', '.mp4', '.mkv', '.avi', '.mxf', '.webm', '.wmv',
        '.m4v', '.mpg', '.mpeg', '.ts', '.flv', '.ogv',
    )

    all_files = sorted([
        f for f in os.listdir(directory)
        if os.path.isfile(os.path.join(directory, f))
        and not f.startswith('.')  # skip hidden files
    ])

    if not all_files:
        return []

    # --- Regex to detect frame numbers ---
    # Matches: base_name.0001.ext  OR  base_name0001.ext  OR  base_name_0001.ext
    # Minimum 2 digits to avoid false positives on things like "v2.exr"
    frame_regex = re.compile(
        r'^(.+?)'            # base name (non-greedy)
        r'[._]?'             # optional separator (dot, underscore, or nothing)
        r'(\d{2,})'          # frame number (2+ digits)
        r'(\.[^.]+)$'        # extension
    )

    image_files = []
    video_files = []
    other_files = []

    for f in all_files:
        ext = os.path.splitext(f)[1].lower()
        if ext in image_extensions:
            image_files.append(f)
        elif ext in video_extensions:
            video_files.append(f)
        else:
            other_files.append(f)

    # --- Group image files into sequences ---
    sequences = {}
    orphan_images = []  # images that don't match the frame regex

    for filename in image_files:
        match = frame_regex.match(filename)
        if match:
            base_name = match.group(1)
            frame_num = int(match.group(2))
            padding = len(match.group(2))
            extension = match.group(3)

            # Normalize base: strip trailing separators for grouping
            base_clean = base_name.rstrip('._')
            key = (base_clean, extension.lower(), padding)

            if key not in sequences:
                sequences[key] = {
                    'name': base_clean,
                    'base_raw': base_name,   # preserve original for pattern
                    'extension': extension,
                    'padding': padding,
                    'frames': [],
                    'files': []
                }
            sequences[key]['frames'].append(frame_num)
            sequences[key]['files'].append(filename)
        else:
            # Image file without detectable frame number → single image
            orphan_images.append(filename)

    # --- Build results ---
    results = []

    # 1. Image sequences (2+ frames grouped together)
    for key, seq_data in sequences.items():
        if len(seq_data['frames']) >= 2:
            frames = sorted(seq_data['frames'])
            start_frame = min(frames)
            end_frame = max(frames)
            padding = seq_data['padding']

            start_str = str(start_frame).zfill(padding)
            end_str = str(end_frame).zfill(padding)

            # Build display pattern and Flame import pattern
            # Detect separator used in first file
            first_file = sorted(seq_data['files'])[0]
            sep_match = re.match(
                re.escape(seq_data['name']) + r'([._]?)\d', first_file
            )
            separator = sep_match.group(1) if sep_match else '.'

            display_pattern = (
                f"{seq_data['name']}{separator}"
                f"{'#' * padding}{seq_data['extension']}"
            )
            import_pattern = os.path.join(
                directory,
                f"{seq_data['name']}{separator}"
                f"[{start_str}-{end_str}]{seq_data['extension']}"
            )

            results.append({
                'name': seq_data['name'],
                'pattern': display_pattern,
                'first_file': sorted(seq_data['files'])[0],
                'start_frame': start_frame,
                'end_frame': end_frame,
                'frame_count': len(frames),
                'extension': seq_data['extension'],
                'padding': padding,
                'directory': directory,
                'import_pattern': import_pattern,
                'is_sequence': True,
                'file_type': 'sequence'
            })
        else:
            # Only 1 frame → treat as single image
            orphan_images.extend(seq_data['files'])

    # 2. Video files
    for filename in sorted(video_files):
        filepath = os.path.join(directory, filename)
        results.append({
            'name': filename,
            'pattern': filename,
            'first_file': filename,
            'start_frame': 0,
            'end_frame': 0,
            'frame_count': 1,
            'extension': os.path.splitext(filename)[1],
            'padding': 0,
            'directory': directory,
            'import_pattern': filepath,
            'is_sequence': False,
            'file_type': 'video'
        })

    # 3. Single image files (orphans or single-frame "sequences")
    for filename in sorted(set(orphan_images)):
        filepath = os.path.join(directory, filename)
        results.append({
            'name': filename,
            'pattern': filename,
            'first_file': filename,
            'start_frame': 0,
            'end_frame': 0,
            'frame_count': 1,
            'extension': os.path.splitext(filename)[1],
            'padding': 0,
            'directory': directory,
            'import_pattern': filepath,
            'is_sequence': False,
            'file_type': 'single_image'
        })

    # 4. Other files (any type not recognized above)
    for filename in sorted(other_files):
        filepath = os.path.join(directory, filename)
        results.append({
            'name': filename,
            'pattern': filename,
            'first_file': filename,
            'start_frame': 0,
            'end_frame': 0,
            'frame_count': 1,
            'extension': os.path.splitext(filename)[1],
            'padding': 0,
            'directory': directory,
            'import_pattern': filepath,
            'is_sequence': False,
            'file_type': 'other'
        })

    return results


# ============================================
# Result Import Dialog (Robust Version)
# ============================================

class SammieImportDialog(QtWidgets.QDialog):
    """
    Robust import dialog for SammieRoto results.
    
    Features:
    - Scans result directory for all matte sequences/files
    - Shows file list with details (name, frame range, format)
    - Select one or multiple files with checkboxes
    - Rescan button to refresh without closing
    - Import button imports selected files (keeps dialog open)
    - Close button when done importing
    """

    # Signal emitted when user wants to import selected sequences
    # Args: (sequence_list: list, group_mattes: bool)
    import_requested = QtCore.Signal(list, bool)

    def __init__(self, result_path, log_func=None, get_existing_groups=None, parent=None):
        super().__init__(parent)

        self.result_path = result_path
        self.log_func = log_func or (lambda msg: print(f"==SammieRoto_UI: {msg}"))
        self.sequences = []
        self._import_count = 0
        self._get_existing_groups = get_existing_groups

        self.setWindowTitle('SammieRoto - Import Results')
        self.setMinimumSize(pyflame.gui_resize(750), pyflame.gui_resize(520))
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.WindowStaysOnTopHint)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Color.DARK_BG};
                color: {Color.TEXT};
            }}
        """)

        self._build_ui()
        self._scan_results()

    def _build_ui(self):
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(main_layout)

        # Title bar
        title_label = QtWidgets.QLabel('SammieRoto - Import Results')
        title_font = QtGui.QFont(PYFLAME_FONT)
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
        main_layout.addWidget(title_label)

        # Content
        content = QtWidgets.QVBoxLayout()
        content.setContentsMargins(20, 15, 20, 15)
        content.setSpacing(10)
        main_layout.addLayout(content)

        # Info message
        info_label = PyFlameLabel(
            text='Sammie Roto 2.0 has launched. Scan for results when ready to import.',
            width=700
        )
        content.addWidget(info_label)

        # Result path row
        path_row = QtWidgets.QHBoxLayout()
        path_row.setSpacing(8)

        path_label = PyFlameLabel(text='Result Path:', width=85)
        path_row.addWidget(path_label)

        self.path_display = PyFlameLineEdit(text=self.result_path, width=480)
        self.path_display.setReadOnly(True)
        path_row.addWidget(self.path_display)

        copy_btn = PyFlameButton(
            text='Copy',
            connect=self._copy_path,
            width=70
        )
        path_row.addWidget(copy_btn)

        content.addLayout(path_row)

        # Separator
        sep = QtWidgets.QFrame()
        sep.setFrameShape(QtWidgets.QFrame.HLine)
        sep.setStyleSheet(f"background-color: {Color.BORDER};")
        sep.setMaximumHeight(1)
        content.addWidget(sep)

        # Toolbar row: Scan + Select All + Select None
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(8)

        self.scan_btn = PyFlameButton(
            text='Scan / Refresh',
            connect=self._scan_results,
            width=120,
            color=Color.BLUE
        )
        toolbar.addWidget(self.scan_btn)

        self.select_all_btn = PyFlameButton(
            text='Select All',
            connect=self._select_all,
            width=90,
            enabled=False
        )
        toolbar.addWidget(self.select_all_btn)

        self.select_none_btn = PyFlameButton(
            text='Select None',
            connect=self._select_none,
            width=100,
            enabled=False
        )
        toolbar.addWidget(self.select_none_btn)

        toolbar.addStretch()

        self.scan_info = PyFlameLabel(text='', width=200)
        self.scan_info.setStyleSheet(f"QLabel {{ color: rgb(120, 120, 120); font-style: italic; }}")
        toolbar.addWidget(self.scan_info)

        content.addLayout(toolbar)

        # File list
        self.file_list = PyFlameListWidget(width=700, height=200)
        content.addWidget(self.file_list)

        # Group Mattes option row (visible when 2+ items checked)
        group_row = QtWidgets.QHBoxLayout()

        self.group_mattes_cb = QtWidgets.QCheckBox('Group Mattes')
        self.group_mattes_cb.setChecked(False)
        self.group_mattes_cb.setToolTip(
            'Import mattes and connect them through Comp nodes in the selected blend mode.\n'
            'Creates a chain: Matte1 → Comp → Matte2 → Comp → ... → Result\n'
            'Useful for combining multiple render passes (back-to-beauty).'
        )
        self.group_mattes_cb.setStyleSheet(f"""
            QCheckBox {{
                color: {Color.TEXT};
                font-size: 13px;
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {Color.TEXT_DISABLED};
                border-radius: 2px;
                background: {Color.INPUT_BG};
            }}
            QCheckBox::indicator:checked {{
                background: {Color.BLUE};
                border-color: {Color.BLUE};
            }}
        """)
        group_row.addWidget(self.group_mattes_cb)

        # Blend mode selector
        self.blend_mode_label = QtWidgets.QLabel('Blend:')
        self.blend_mode_label.setStyleSheet(f"color: {Color.TEXT_DISABLED}; font-size: 12px;")
        group_row.addWidget(self.blend_mode_label)

        self.blend_mode_combo = QtWidgets.QComboBox()
        self.blend_mode_combo.addItems([
            'Screen', 'Add', 'Over', 'Multiply',
            'Subtract', 'Difference', 'Max', 'Min'
        ])
        self.blend_mode_combo.setCurrentText('Screen')
        self.blend_mode_combo.setFixedWidth(pyflame.gui_resize(100))
        self.blend_mode_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Color.INPUT_BG};
                color: {Color.TEXT};
                border: 1px solid {Color.TEXT_DISABLED};
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {Color.MID_BG};
                color: {Color.TEXT};
                selection-background-color: {Color.BLUE};
            }}
        """)
        group_row.addWidget(self.blend_mode_combo)

        # Target selector (New Group vs existing comp chain groups)
        self.target_label = QtWidgets.QLabel('Target:')
        self.target_label.setStyleSheet(f"color: {Color.TEXT_DISABLED}; font-size: 12px;")
        group_row.addWidget(self.target_label)

        self.target_combo = QtWidgets.QComboBox()
        self.target_combo.addItem('New Group')
        self.target_combo.setFixedWidth(pyflame.gui_resize(180))
        self.target_combo.setStyleSheet(f"""
            QComboBox {{
                background: {Color.INPUT_BG};
                color: {Color.TEXT};
                border: 1px solid {Color.TEXT_DISABLED};
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background: {Color.MID_BG};
                color: {Color.TEXT};
                selection-background-color: {Color.BLUE};
            }}
        """)
        group_row.addWidget(self.target_combo)

        group_row.addStretch()

        # Initially hidden — shown based on selection count and checkbox state
        self.group_mattes_cb.setVisible(False)
        self.blend_mode_label.setVisible(False)
        self.blend_mode_combo.setVisible(False)
        self.target_label.setVisible(False)
        self.target_combo.setVisible(False)

        # Connect signals for dynamic UI
        self.group_mattes_cb.toggled.connect(self._on_group_mattes_toggled)
        self.file_list.itemChanged.connect(self._on_item_changed)

        content.addLayout(group_row)

        # Status bar
        self.status_bar = PyFlameStatusBar(text='Click "Scan / Refresh" to search for result files.')
        content.addWidget(self.status_bar)

        # Bottom buttons
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self.close_btn = PyFlameButton(
            text='Close',
            connect=self.reject,
            width=100
        )
        btn_layout.addWidget(self.close_btn)

        btn_layout.addSpacing(10)

        self.import_btn = PyFlameButton(
            text='Import Selected',
            connect=self._do_import,
            width=140,
            color=Color.BLUE,
            enabled=False
        )
        btn_layout.addWidget(self.import_btn)

        content.addLayout(btn_layout)

    def _copy_path(self):
        """Copy result path to clipboard"""
        QApplication.clipboard().setText(self.result_path)
        self.status_bar.set_success('Result path copied to clipboard.')

    def _scan_results(self):
        """Scan the result directory for matte files"""
        self.log_func(f"Scanning result directory: {self.result_path}")
        self.file_list.clear()
        self.sequences = []

        if not os.path.exists(self.result_path):
            self.status_bar.set_warning(
                f'Result directory does not exist yet. '
                f'Export from SammieRoto first, then click Scan.'
            )
            self.scan_info.setText('0 sequences found')
            self._update_button_states()
            return

        self.sequences = detect_sequences_in_directory(self.result_path)

        if not self.sequences:
            self.status_bar.set_warning(
                'No image files found in result directory. '
                'Export from SammieRoto, then click Scan again.'
            )
            self.scan_info.setText('0 sequences found')
            self._update_button_states()
            return

        # Populate list
        for seq in self.sequences:
            if seq['is_sequence']:
                display_text = (
                    f"SEQ  {seq['pattern']}   "
                    f"[{seq['start_frame']}-{seq['end_frame']}]   "
                    f"({seq['frame_count']} frames)"
                )
            else:
                file_path = os.path.join(seq['directory'], seq['first_file'])
                try:
                    file_size = os.path.getsize(file_path)
                    size_mb = file_size / (1024 * 1024)
                    size_str = f"{size_mb:.1f} MB" if size_mb >= 1 else f"{file_size / 1024:.0f} KB"
                except OSError:
                    size_str = "? KB"

                file_type = seq.get('file_type', 'other')
                type_label = {
                    'video': 'VID',
                    'single_image': 'IMG',
                    'other': 'FILE'
                }.get(file_type, 'FILE')

                display_text = (
                    f"{type_label}  {seq['name']}   "
                    f"({size_str})"
                )

            item = QtWidgets.QListWidgetItem(display_text)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            item.setData(QtCore.Qt.UserRole, seq)
            self.file_list.addItem(item)

        count = len(self.sequences)
        seq_count = sum(1 for s in self.sequences if s['is_sequence'])
        file_count = count - seq_count

        # Build info text
        parts = []
        if seq_count:
            parts.append(f"{seq_count} sequence{'s' if seq_count != 1 else ''}")
        if file_count:
            parts.append(f"{file_count} file{'s' if file_count != 1 else ''}")
        info_text = ' + '.join(parts) if parts else '0 items found'
        self.scan_info.setText(info_text)

        self.status_bar.set_success(
            f'Found {count} item{"s" if count != 1 else ""}. '
            f'Select the ones to import and click "Import Selected".'
        )
        self.log_func(f"Scan found: {info_text}")

        self._update_button_states()

    def _select_all(self):
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(QtCore.Qt.Checked)
        self.file_list.blockSignals(False)
        self._update_button_states()

    def _select_none(self):
        self.file_list.blockSignals(True)
        for i in range(self.file_list.count()):
            self.file_list.item(i).setCheckState(QtCore.Qt.Unchecked)
        self.file_list.blockSignals(False)
        self._update_button_states()

    def _count_checked(self):
        """Count how many items are currently checked."""
        count = 0
        for i in range(self.file_list.count()):
            if self.file_list.item(i).checkState() == QtCore.Qt.Checked:
                count += 1
        return count

    def _on_item_changed(self, item):
        """Called when any list item checkbox changes."""
        self._update_button_states()

    def _update_button_states(self):
        has_items = self.file_list.count() > 0
        checked = self._count_checked()
        self.select_all_btn.setEnabled(has_items)
        self.select_none_btn.setEnabled(has_items)
        self.import_btn.setEnabled(checked > 0)

        # Show Group Mattes:
        #   - Always when 2+ items checked (create new chain)
        #   - When 1 item checked AND existing groups exist (add to group)
        has_groups = self._has_existing_groups()
        show_group = checked >= 2 or (checked >= 1 and has_groups)
        self.group_mattes_cb.setVisible(show_group)

        is_checked = show_group and self.group_mattes_cb.isChecked()
        self.blend_mode_label.setVisible(is_checked)
        self.blend_mode_combo.setVisible(is_checked)
        self.target_label.setVisible(is_checked)
        self.target_combo.setVisible(is_checked)

        if not show_group:
            self.group_mattes_cb.setChecked(False)

    def _has_existing_groups(self):
        """Check if there are existing SammieRoto comp chain groups."""
        if self._get_existing_groups:
            try:
                groups = self._get_existing_groups()
                self._cached_groups = groups  # Cache for _refresh_target_groups
                return len(groups) > 0
            except Exception:
                pass
        return False

    def _on_group_mattes_toggled(self, checked):
        """Show/hide blend mode and target selector based on checkbox."""
        self.blend_mode_label.setVisible(checked)
        self.blend_mode_combo.setVisible(checked)
        self.target_label.setVisible(checked)
        self.target_combo.setVisible(checked)
        if checked:
            self._refresh_target_groups()

    def _refresh_target_groups(self):
        """Refresh the list of existing SammieRoto comp chain groups."""
        current = self.target_combo.currentText()
        self.target_combo.clear()

        checked = self._count_checked()

        # "New Group" only available when 2+ items selected
        if checked >= 2:
            self.target_combo.addItem('New Group')

        # Use cached groups from _has_existing_groups if available
        groups = getattr(self, '_cached_groups', None)
        if groups is None and self._get_existing_groups:
            try:
                groups = self._get_existing_groups()
            except Exception as e:
                self.log_func(f"Could not detect existing groups: {e}")
                groups = []

        if groups:
            for name in groups:
                self.target_combo.addItem(f'→ {name}')

        # Restore previous selection if still available
        idx = self.target_combo.findText(current)
        if idx >= 0:
            self.target_combo.setCurrentIndex(idx)

    def _do_import(self):
        """Import selected sequences, optionally grouping with Comp nodes."""
        selected = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                seq_data = item.data(QtCore.Qt.UserRole)
                seq_data = dict(seq_data)  # copy to avoid mutating original
                # Attach group options to each sequence dict
                if self.group_mattes_cb.isChecked():
                    seq_data['_blend_mode'] = self.blend_mode_combo.currentText()
                    target_text = self.target_combo.currentText()
                    if target_text.startswith('→ '):
                        seq_data['_target_group'] = target_text[2:]  # strip "→ "
                    else:
                        seq_data['_target_group'] = ''  # New Group
                selected.append(seq_data)

        if not selected:
            self.status_bar.set_warning('No files selected for import.')
            return

        group_mattes = self.group_mattes_cb.isChecked()

        self._import_count += len(selected)
        self.import_requested.emit(selected, group_mattes)

        # Invalidate group cache — new groups may have been created
        self._cached_groups = None

        # Mark imported items visually
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                item.setForeground(QtGui.QColor(0, 150, 64))
                current_text = item.text()
                if not current_text.startswith('✓ '):
                    item.setText(f'✓ {current_text}')
                item.setCheckState(QtCore.Qt.Unchecked)

        count = len(selected)
        if group_mattes:
            target_text = self.target_combo.currentText()
            blend = self.blend_mode_combo.currentText()
            if target_text.startswith('→ '):
                mode_info = f' [Added to: {target_text[2:]}, {blend}]'
            else:
                mode_info = f' [Grouped: {blend}]'
        else:
            mode_info = ''
        self.status_bar.set_success(
            f'Imported {count} item{"s" if count != 1 else ""} into Flame.{mode_info} '
            f'(Total: {self._import_count}) — You can scan and import more, or close.'
        )

    def get_selected_sequences(self):
        """Get list of checked sequences (for external use)"""
        selected = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == QtCore.Qt.Checked:
                seq_data = item.data(QtCore.Qt.UserRole)
                selected.append(seq_data)
        return selected


def prompt_for_result_import(result_path, import_callback=None,
                            get_existing_groups=None, log_func=None):
    """
    Display the robust import dialog.
    
    Args:
        result_path: Path where SammieRoto should save results
        import_callback: Function(sequence_list, group_mattes) called on import.
                         sequence_list: list of sequence dicts
                         group_mattes: bool - True if user wants Comp node chain
        get_existing_groups: Optional callable() → list of comp chain group names
        log_func: Optional logging function
        
    Returns:
        SammieImportDialog instance (stays open until user closes)
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            print(f"==SammieRoto_UI: {msg}")

    try:
        # Copy path to clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(result_path)
        log("Result path copied to clipboard.")

        dialog = SammieImportDialog(
            result_path, log_func=log,
            get_existing_groups=get_existing_groups
        )

        if import_callback:
            dialog.import_requested.connect(import_callback)

        return dialog

    except Exception as e:
        log(f"Error creating import dialog: {e}")
        return None


# ============================================
# Configuration Window (Improved)
# ============================================

def show_setup_window(config, save_config_func, log_func=None):
    """
    Display configuration window for SammieRoto RoundTrip.
    
    Improvements in v2.0:
    - Token Picker button for Export Path Template
    - Path validation indicators
    - Preview of resolved path
    """
    def log(msg):
        if log_func:
            log_func(msg)
        else:
            print(f"==SammieRoto_UI: {msg}")

    window = PyFlameWindow(
        title='SammieRoto RoundTrip - Configuration',
        width=750,
        height=580
    )

    # ---- Sammie Launcher ----
    window.content_layout.addWidget(
        PyFlameLabel(text='Sammie Launcher Path (run_sammie.command):')
    )
    launcher_layout = QtWidgets.QHBoxLayout()
    launcher_layout.setSpacing(8)
    sammie_launcher_entry = PyFlameLineEdit(text=config.get('sammie_launcher', ''), width=540)
    launcher_layout.addWidget(sammie_launcher_entry)

    def browse_launcher():
        start_dir = os.path.dirname(config.get('sammie_launcher', ''))
        if not os.path.exists(start_dir):
            start_dir = os.path.expanduser('~')
        path = QFileDialog.getOpenFileName(
            window,
            "Select Sammie Launcher",
            start_dir,
            "Shell Scripts (*.command *.sh);;All Files (*)"
        )[0]
        if path:
            sammie_launcher_entry.setText(path)

    browse_btn = PyFlameButton(text='Browse...', connect=browse_launcher, width=90)
    launcher_layout.addWidget(browse_btn)
    window.content_layout.addLayout(launcher_layout)

    window.content_layout.addSpacing(8)

    # ---- Preset Path ----
    window.content_layout.addWidget(
        PyFlameLabel(text='JPEG Export Preset (.xml):')
    )
    preset_layout = QtWidgets.QHBoxLayout()
    preset_layout.setSpacing(8)
    preset_entry = PyFlameLineEdit(text=config.get('preset_path', ''), width=540)
    preset_layout.addWidget(preset_entry)

    def browse_preset():
        start_dir = os.path.dirname(config.get('preset_path', ''))
        if not os.path.exists(start_dir):
            start_dir = '/opt/Autodesk'
        path = QFileDialog.getOpenFileName(
            window,
            "Select JPEG Preset",
            start_dir,
            "XML Files (*.xml);;All Files (*)"
        )[0]
        if path:
            preset_entry.setText(path)

    browse_preset_btn = PyFlameButton(text='Browse...', connect=browse_preset, width=90)
    preset_layout.addWidget(browse_preset_btn)
    window.content_layout.addLayout(preset_layout)

    window.content_layout.addSpacing(8)

    # ---- Export Path Template ----
    window.content_layout.addWidget(
        PyFlameLabel(text='Export Path Template:')
    )

    # Path entry + Token button
    export_path_layout = QtWidgets.QHBoxLayout()
    export_path_layout.setSpacing(8)
    export_path_entry = PyFlameLineEdit(
        text=config.get('export_path_template', ''),
        width=530,
        placeholder='/path/to/{project_name_raw}/rotos'
    )
    export_path_layout.addWidget(export_path_entry)

    token_btn = PyFlameTokenPushButton(
        target_line_edit=export_path_entry,
        width=100
    )
    export_path_layout.addWidget(token_btn)
    window.content_layout.addLayout(export_path_layout)

    # Path preview (live resolution)
    preview_label = PyFlameStatusBar(text='')
    window.content_layout.addWidget(preview_label)

    def update_path_preview():
        template = export_path_entry.text()
        try:
            import flame
            project_name_raw = flame.project.current_project.name
            nickname_raw = flame.project.current_project.nickname
        except Exception:
            project_name_raw = '<project>'
            nickname_raw = '<nickname>'

        import datetime
        now = datetime.datetime.now()

        preview_map = {
            'project_name_raw': project_name_raw,
            'nickname_raw': nickname_raw,
            'clip_name': '<clip_name>',
            'shot_name': '<shot_name>',
            'batch_name': '<batch_name>',
            'batch_iteration': '<iter>',
            'user_name': os.environ.get('USER', '<user>'),
            'date_YYYY': now.strftime('%Y'),
            'date_MM': now.strftime('%m'),
            'date_DD': now.strftime('%d'),
            'date_YYYY_MM_DD': now.strftime('%Y-%m-%d'),
            'timestamp': str(int(now.timestamp())),
        }

        try:
            resolved = template.format(**preview_map)
            preview_label.set_info(f'Preview: {resolved}')
        except (KeyError, ValueError) as e:
            preview_label.set_warning(f'Invalid token in template: {e}')

    export_path_entry.textChanged.connect(update_path_preview)
    token_btn.token_selected.connect(lambda _: update_path_preview())

    # Trigger initial preview
    update_path_preview()

    window.content_layout.addSpacing(8)

    # ---- Result Reel and Timeout ----
    row_layout = QtWidgets.QHBoxLayout()
    row_layout.setSpacing(30)

    reel_group = QtWidgets.QVBoxLayout()
    reel_group.addWidget(PyFlameLabel(text='Result Reel Name:'))
    reel_entry = PyFlameLineEdit(text=config.get('result_reel_name', 'SammieRoto Results'), width=250)
    reel_group.addWidget(reel_entry)
    row_layout.addLayout(reel_group)

    timeout_group = QtWidgets.QVBoxLayout()
    timeout_group.addWidget(PyFlameLabel(text='File Wait Timeout (sec):'))
    timeout_entry = PyFlameLineEdit(text=str(config.get('file_wait_timeout', 60)), width=80)
    timeout_group.addWidget(timeout_entry)
    row_layout.addLayout(timeout_group)

    row_layout.addStretch()
    window.content_layout.addLayout(row_layout)

    # ---- Sammie Command (advanced, collapsed) ----
    window.content_layout.addSpacing(5)
    advanced_label = PyFlameLabel(text='Advanced:', width=100)
    advanced_label.setStyleSheet(f"QLabel {{ color: rgb(100, 100, 100); }}")
    window.content_layout.addWidget(advanced_label)

    adv_row = QtWidgets.QHBoxLayout()
    adv_row.setSpacing(8)
    adv_row.addWidget(PyFlameLabel(text='Sammie Command:', width=130))
    sammie_cmd_entry = PyFlameLineEdit(text=config.get('sammie_cmd', '/bin/bash'), width=250)
    adv_row.addWidget(sammie_cmd_entry)
    adv_row.addStretch()
    window.content_layout.addLayout(adv_row)

    # Spacer
    window.content_layout.addStretch()

    # ---- Status ----
    setup_status = PyFlameStatusBar()
    window.content_layout.addWidget(setup_status)

    # ---- Buttons ----
    btn_layout = QtWidgets.QHBoxLayout()
    btn_layout.addStretch()

    def save_and_close():
        try:
            timeout_value = int(timeout_entry.text())
        except ValueError:
            setup_status.set_error('Timeout must be a number.')
            return

        new_config = {
            'sammie_cmd': sammie_cmd_entry.text(),
            'sammie_launcher': sammie_launcher_entry.text(),
            'preset_path': preset_entry.text(),
            'export_path_template': export_path_entry.text(),
            'result_reel_name': reel_entry.text(),
            'file_wait_timeout': timeout_value
        }

        # Validate paths
        if not os.path.exists(new_config['sammie_launcher']):
            setup_status.set_warning('Warning: Sammie launcher path does not exist.')

        if not os.path.exists(new_config['preset_path']):
            setup_status.set_warning('Warning: JPEG preset path does not exist.')

        if save_config_func(new_config):
            setup_status.set_success('Configuration saved successfully!')
            log('Configuration saved.')

            # Close after short delay so user sees the message
            QtCore.QTimer.singleShot(600, window.close)
        else:
            setup_status.set_error('Error saving configuration.')

    cancel_btn = PyFlameButton(text='Cancel', connect=window.close, width=100)
    save_btn = PyFlameButton(text='Save', connect=save_and_close, color=Color.BLUE, width=100)

    btn_layout.addWidget(cancel_btn)
    btn_layout.addSpacing(10)
    btn_layout.addWidget(save_btn)
    window.content_layout.addLayout(btn_layout)

    window.show()

    return window
