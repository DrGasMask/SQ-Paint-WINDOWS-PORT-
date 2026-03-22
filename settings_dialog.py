from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox,
    QSlider, QSpinBox, QComboBox, QPushButton, QFrame, QWidget, QButtonGroup, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont


class SectionLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        f = self.font(); f.setBold(True); f.setPointSize(f.pointSize() + 1)
        self.setFont(f)
        self.setStyleSheet("color: #e0e0e0; padding-top: 10px; padding-bottom: 2px;")


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet("color: #444;")


class SettingsDialog(QDialog):
    # Emitted whenever a setting changes so the app can react immediately
    theme_changed        = pyqtSignal(str)    # "dark" | "light"
    aa_changed           = pyqtSignal(bool)
    smooth_changed       = pyqtSignal(bool)
    brush_cursor_changed = pyqtSignal(bool)
    tolerance_changed    = pyqtSignal(int)
    max_undo_changed     = pyqtSignal(int)
    confirm_clear_changed= pyqtSignal(bool)
    round_lines_changed  = pyqtSignal(bool)
    experimental_changed = pyqtSignal(bool)

    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings (expiremental)")
        self.setMinimumWidth(420)
        self.setModal(True)
        self._s = dict(settings)   # local working copy

        self._apply_theme(self._s.get("theme", "dark"))

        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(20, 16, 20, 16)

        # ── Appearance ────────────────────────────────────────────────────────
        root.addWidget(SectionLabel("🎨  Appearance"))
        root.addWidget(Divider())

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Theme:"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Dark", "Light"])
        self.theme_combo.setCurrentText(self._s.get("theme", "dark").capitalize())
        self.theme_combo.currentTextChanged.connect(self._on_theme)
        theme_row.addWidget(self.theme_combo); theme_row.addStretch()
        root.addLayout(theme_row)

        # ── Experimental ──────────────────────────────────────────────────────
        root.addWidget(SectionLabel("🧪  Experimental Features"))
        root.addWidget(Divider())

        self.experimental_cb = QCheckBox("Enable experimental features")
        self.experimental_cb.setChecked(self._s.get("experimental", False))
        self.experimental_cb.toggled.connect(lambda v: (self._set("experimental", v), self.experimental_changed.emit(v)))
        root.addWidget(self.experimental_cb)

        exp_note = QLabel("  Controls upcoming tabs like Animation and Photo Editing.")
        exp_note.setStyleSheet("color:#888; font-size:11px;")
        root.addWidget(exp_note)

        # ── Canvas / Drawing ──────────────────────────────────────────────────
        root.addWidget(SectionLabel("🖱️  Canvas / Drawing"))
        root.addWidget(Divider())

        self.brush_cursor_cb = QCheckBox("Show brush cursor outline")
        self.brush_cursor_cb.setChecked(self._s.get("brush_cursor", True))
        self.brush_cursor_cb.toggled.connect(lambda v: (self._set("brush_cursor", v), self.brush_cursor_changed.emit(v)))
        root.addWidget(self.brush_cursor_cb)

        self.aa_cb = QCheckBox("Enable anti-aliasing")
        self.aa_cb.setChecked(self._s.get("antialiasing", True))
        self.aa_cb.toggled.connect(lambda v: (self._set("antialiasing", v), self.aa_changed.emit(v)))
        root.addWidget(self.aa_cb)

        self.smooth_cb = QCheckBox("Smooth drawing (stabilization)")
        self.smooth_cb.setChecked(self._s.get("smooth_drawing", False))
        self.smooth_cb.toggled.connect(lambda v: (self._set("smooth_drawing", v), self.smooth_changed.emit(v)))
        root.addWidget(self.smooth_cb)

        # ── Lines / Shapes ────────────────────────────────────────────────────
        root.addWidget(SectionLabel("📐  Lines / Shapes"))
        root.addWidget(Divider())

        self.round_lines_cb = QCheckBox("Rounded line & shape ends (uncheck for squared)")
        self.round_lines_cb.setChecked(self._s.get("round_lines", True))
        self.round_lines_cb.toggled.connect(lambda v: (self._set("round_lines", v), self.round_lines_changed.emit(v)))
        root.addWidget(self.round_lines_cb)

        # ── Fill Tool ─────────────────────────────────────────────────────────
        root.addWidget(SectionLabel("🪣  Fill Tool"))
        root.addWidget(Divider())

        tol_row = QHBoxLayout()
        tol_row.addWidget(QLabel("Default fill tolerance:"))
        self.tol_slider = QSlider(Qt.Orientation.Horizontal)
        self.tol_slider.setRange(0, 100)
        self.tol_slider.setValue(self._s.get("fill_tolerance", 30))
        self.tol_lbl = QLabel(str(self.tol_slider.value()))
        self.tol_lbl.setFixedWidth(28)
        self.tol_slider.valueChanged.connect(self._on_tolerance)
        tol_row.addWidget(self.tol_slider); tol_row.addWidget(self.tol_lbl)
        root.addLayout(tol_row)

        # ── Undo / History ────────────────────────────────────────────────────
        root.addWidget(SectionLabel("🧾  Undo / History"))
        root.addWidget(Divider())

        undo_row = QHBoxLayout()
        undo_row.addWidget(QLabel("Max undo steps:"))
        self.undo_spin = QSpinBox()
        self.undo_spin.setRange(10, 100)
        self.undo_spin.setValue(self._s.get("max_undo", 30))
        self.undo_spin.valueChanged.connect(lambda v: (self._set("max_undo", v), self.max_undo_changed.emit(v)))
        undo_row.addWidget(self.undo_spin); undo_row.addStretch()
        root.addLayout(undo_row)

        # ── General ───────────────────────────────────────────────────────────
        root.addWidget(SectionLabel("💾  General"))
        root.addWidget(Divider())

        self.confirm_clear_cb = QCheckBox("Confirm before clearing canvas")
        self.confirm_clear_cb.setChecked(self._s.get("confirm_clear", True))
        self.confirm_clear_cb.toggled.connect(lambda v: (self._set("confirm_clear", v), self.confirm_clear_changed.emit(v)))
        root.addWidget(self.confirm_clear_cb)

        # ── Close button ──────────────────────────────────────────────────────
        root.addSpacing(10)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet("padding: 6px 24px;")
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _set(self, key, value):
        self._s[key] = value

    def get_settings(self) -> dict:
        return dict(self._s)

    def _on_theme(self, text):
        theme = text.lower()
        self._set("theme", theme)
        self._apply_theme(theme)
        self.theme_changed.emit(theme)

    def _on_tolerance(self, val):
        self.tol_lbl.setText(str(val))
        self._set("fill_tolerance", val)
        self.tolerance_changed.emit(val)

    def _apply_theme(self, theme):
        if theme == "light":
            self.setStyleSheet("""
                QDialog { background: #f5f5f5; color: #111; }
                QLabel  { color: #111; }
                QCheckBox { color: #111; }
                QComboBox { background: #fff; color: #111; border: 1px solid #bbb; border-radius:4px; padding:2px 6px; }
                QSpinBox  { background: #fff; color: #111; border: 1px solid #bbb; border-radius:4px; padding:2px; }
                QPushButton { background:#0078d4; color:white; border-radius:4px; padding:5px 16px; }
                QPushButton:hover { background:#005fa3; }
                QSlider::groove:horizontal { background:#ccc; height:4px; border-radius:2px; }
                QSlider::handle:horizontal { background:#0078d4; width:14px; height:14px; border-radius:7px; margin:-5px 0; }
            """)
        else:
            self.setStyleSheet("""
                QDialog { background: #1e1e1e; color: #ddd; }
                QLabel  { color: #ddd; }
                QCheckBox { color: #ddd; }
                QComboBox { background: #2e2e2e; color: #ddd; border: 1px solid #555; border-radius:4px; padding:2px 6px; }
                QSpinBox  { background: #2e2e2e; color: #ddd; border: 1px solid #555; border-radius:4px; padding:2px; }
                QPushButton { background:#0078d4; color:white; border-radius:4px; padding:5px 16px; }
                QPushButton:hover { background:#005fa3; }
                QSlider::groove:horizontal { background:#444; height:4px; border-radius:2px; }
                QSlider::handle:horizontal { background:#0078d4; width:14px; height:14px; border-radius:7px; margin:-5px 0; }
            """)
