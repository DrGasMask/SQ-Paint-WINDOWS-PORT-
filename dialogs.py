from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                             QSpinBox, QCheckBox, QComboBox, QDialogButtonBox,
                             QToolButton, QButtonGroup, QPushButton)
from PyQt6.QtCore import Qt

class ResizeDialog(QDialog):
    def __init__(self, cur_w, cur_h, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Resize Canvas")
        self.cur_w, self.cur_h = cur_w, cur_h
        self.aspect_ratio = cur_w / cur_h
        self._updating = False
        
        layout = QVBoxLayout(self)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Pixels", "Percentage"])
        layout.addWidget(QLabel("Resize by:")); layout.addWidget(self.mode_combo)

        grid = QGridLayout()
        self.w_spin = QSpinBox(); self.h_spin = QSpinBox()
        grid.addWidget(QLabel("Width:"), 0, 0); grid.addWidget(self.w_spin, 0, 1)
        grid.addWidget(QLabel("Height:"), 1, 0); grid.addWidget(self.h_spin, 1, 1)
        layout.addLayout(grid)

        self.lock_ratio = QCheckBox("Lock aspect ratio"); self.lock_ratio.setChecked(True)
        layout.addWidget(self.lock_ratio)

        layout.addWidget(QLabel("Anchor Position:"))
        self.anchor_grid = QGridLayout(); self.anchor_group = QButtonGroup(self)
        self.anchors = []
        icons = ["↖", "↑", "↗", "←", "•", "→", "↙", "↓", "↘"]
        for i in range(9):
            btn = QToolButton(); btn.setCheckable(True); btn.setFixedSize(30, 30); btn.setText(icons[i])
            self.anchor_grid.addWidget(btn, i//3, i%3); self.anchor_group.addButton(btn, i)
            self.anchors.append(((i % 3) * 0.5, (i // 3) * 0.5))
        
        self.anchor_group.button(0).setChecked(True); layout.addLayout(self.anchor_grid)
        self.mode_combo.currentIndexChanged.connect(self.update_limits)
        self.w_spin.valueChanged.connect(self.on_width_changed)
        self.h_spin.valueChanged.connect(self.on_height_changed)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
        self.update_limits()

    def update_limits(self):
        self._updating = True
        if self.mode_combo.currentText() == "Pixels":
            self.w_spin.setRange(1, 9999); self.h_spin.setRange(1, 9999)
            self.w_spin.setValue(self.cur_w); self.h_spin.setValue(self.cur_h)
        else:
            self.w_spin.setRange(1, 500); self.h_spin.setRange(1, 500)
            self.w_spin.setValue(100); self.h_spin.setValue(100)
        self._updating = False

    def on_width_changed(self, val):
        if self._updating or not self.lock_ratio.isChecked(): return
        self._updating = True
        if self.mode_combo.currentText() == "Pixels": self.h_spin.setValue(int(val / self.aspect_ratio))
        else: self.h_spin.setValue(val)
        self._updating = False

    def on_height_changed(self, val):
        if self._updating or not self.lock_ratio.isChecked(): return
        self._updating = True
        if self.mode_combo.currentText() == "Pixels": self.w_spin.setValue(int(val * self.aspect_ratio))
        else: self.w_spin.setValue(val)
        self._updating = False

    def get_values(self):
        ax, ay = self.anchors[self.anchor_group.checkedId()]
        if self.mode_combo.currentText() == "Pixels": return self.w_spin.value(), self.h_spin.value(), ax, ay
        pw, ph = self.w_spin.value() / 100.0, self.h_spin.value() / 100.0
        return int(self.cur_w * pw), int(self.cur_h * ph), ax, ay


class SaveFormatDialog(QDialog):
    """Format picker shown before the file dialog when saving."""
    FORMATS = [
        ("sqish", "SQ Paint Project (.sqish)",
         "Saves all layers, names, and visibility.\nOpen later to resume exactly where you left off."),
        ("png",   "PNG Image (.png)",
         "Lossless quality. Best for pixel art and\nimages with transparency."),
        ("jpg",   "JPEG Image (.jpg)",
         "Smaller file size, no transparency.\nBest for photos."),
        ("bmp",   "Bitmap (.bmp)",
         "Uncompressed. Large file size."),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Save As")
        self.setMinimumWidth(380)
        self._chosen = None
        self.setStyleSheet("""
            QDialog { background: #1e1e1e; color: white; }
            QLabel  { color: white; }
            QPushButton {
                background: #2e2e2e; color: white;
                border: 1px solid #444; border-radius: 6px;
                padding: 10px 16px; text-align: left; font-size: 13px;
            }
            QPushButton:hover  { background: #0078d4; border-color: #0078d4; }
            QPushButton:pressed { background: #005fa3; }
        """)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(QLabel("<b>Choose a format to save as:</b>"))
        layout.addSpacing(4)

        for fmt, title, desc in self.FORMATS:
            btn = QPushButton()
            btn.setText(f"{title}\n{desc}")
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _, f=fmt: self._pick(f))
            layout.addWidget(btn)

        layout.addSpacing(4)
        cancel = QPushButton("Cancel")
        cancel.setStyleSheet("background:#333; color:white; border:1px solid #555;"
                             "border-radius:6px; padding:6px;")
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel)

    def _pick(self, fmt):
        self._chosen = fmt
        self.accept()

    def get_format(self):
        return self._chosen
