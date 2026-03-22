# tools.py
# Contains tool-related functionality

from PyQt6.QtWidgets import QToolButton, QSpinBox, QLabel, QHBoxLayout, QComboBox, QFontComboBox, QSlider
from PyQt6.QtGui import QFont
from PyQt6.QtCore import Qt

def _icon(name, size=24):
    """Load an icon from the icons/ folder, scaling to size×size.
    Falls back to None if the file is missing so callers can use setText as fallback."""
    import os
    base = getattr(__import__("sys"), "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "icons", f"{name}.png")
    if not os.path.exists(path):
        return None
    from PyQt6.QtGui import QIcon, QPixmap
    pix = QPixmap(path).scaled(size, size,
        __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.AspectRatioMode.KeepAspectRatio,
        __import__("PyQt6.QtCore", fromlist=["Qt"]).Qt.TransformationMode.SmoothTransformation)
    return QIcon(pix)

def _set_icon_btn(btn, icon_name, fallback_text, size=24):
    """Apply icon to a QToolButton, using text fallback if icon missing."""
    ic = _icon(icon_name, size)
    if ic:
        btn.setIcon(ic)
        btn.setIconSize(__import__("PyQt6.QtCore", fromlist=["QSize"]).QSize(size, size))
        btn.setText("")
    else:
        btn.setText(fallback_text)

def setup_tools_group(layout, app):
    """Setup the tools ribbon group"""
    from ui_components import RibbonGroup

    tools_group = RibbonGroup("Tools")
    app.tools = {}  # Initialize tools dictionary on app
    tools = [
        ("ic_select", "✂️", "select"),
        ("ic_pencil", "✏️", "pencil"),
        ("ic_eraser", "🧽", "eraser"),
        ("ic_fill", "🪣", "fill"),
        ("ic_picker", "💧", "picker"),
        ("ic_text", "📝", "text"),
        ("ic_line", "╱", "line"),
        ("ic_rect", "⬜", "rect"),
        ("ic_ellipse", "⭕", "ellipse"),
        ("ic_rounded_rect", "▢", "rounded_rect"),
        ("ic_triangle", "△", "triangle"),
        ("ic_diamond", "◇", "diamond"),
        ("ic_pentagon", "⬠", "pentagon"),
        ("ic_hexagon", "⬡", "hexagon"),
        ("ic_star", "★", "star"),
        ("ic_arrow", "➤", "arrow"),
    ]

    for i, (ic_name, fallback, tool) in enumerate(tools):
        b = QToolButton()
        b.setCheckable(True)
        _set_icon_btn(b, ic_name, fallback)
        if app.canvas.tool == tool:
            b.setChecked(True)
        b.clicked.connect(lambda ch, t=tool: app.set_tool(t))
        app.tools[tool] = b
        tools_group.grid.addWidget(b, i//8, i%8)

    layout.addWidget(tools_group)

def setup_brush_group(layout, app):
    """Setup the brush settings ribbon group"""
    from ui_components import RibbonGroup

    brush_group = RibbonGroup("Brush")
    
    # Size slider
    size_layout = QHBoxLayout()
    size_layout.addWidget(QLabel("Size:"))
    app.size_slider = QSlider(Qt.Orientation.Horizontal)
    app.size_slider.setRange(1, 100)
    app.size_slider.setValue(app.canvas.pen_width)
    app.size_slider.setFixedWidth(80)
    app.size_slider.valueChanged.connect(app.change_size)
    size_layout.addWidget(app.size_slider)
    brush_group.grid.addLayout(size_layout, 0, 0)

    # Tolerance slider for fill tool
    tol_layout = QHBoxLayout()
    tol_layout.addWidget(QLabel("Tol:"))
    app.tol_slider = QSlider(Qt.Orientation.Horizontal)
    app.tol_slider.setRange(0, 255)
    app.tol_slider.setValue(getattr(app.canvas, 'fill_tolerance', 32))
    app.tol_slider.setFixedWidth(80)
    app.tol_slider.valueChanged.connect(app._on_tolerance_changed)
    tol_layout.addWidget(app.tol_slider)
    app.tol_lbl = QLabel("32")
    app.tol_lbl.setStyleSheet("color:#bfbfbf; font-size:10px; min-width:20px;")
    tol_layout.addWidget(app.tol_lbl)
    brush_group.grid.addLayout(tol_layout, 1, 0)

    layout.addWidget(brush_group)

def setup_text_group(layout, app):
    """Setup the text settings ribbon group"""
    from ui_components import RibbonGroup

    text_group = RibbonGroup("Text")
    app.font_combo = QFontComboBox()
    app.font_combo.setCurrentFont(QFont(app.canvas.font_family))
    app.font_combo.setFixedWidth(130)
    app.font_combo.currentFontChanged.connect(app.change_font_family)
    text_group.grid.addWidget(app.font_combo, 0, 0)

    size_layout = QHBoxLayout()
    size_layout.addWidget(QLabel("Size:"))
    app.font_size_spin = QSlider(Qt.Orientation.Horizontal)
    app.font_size_spin.setRange(8, 72)
    app.font_size_spin.setValue(app.canvas.font_size)
    app.font_size_spin.setFixedWidth(80)
    app.font_size_spin.valueChanged.connect(app.change_font_size)
    size_layout.addWidget(app.font_size_spin)
    text_group.grid.addLayout(size_layout, 1, 0)

    app.bold_btn = QToolButton()
    app.bold_btn.setText("B")
    app.bold_btn.setCheckable(True)
    app.bold_btn.setStyleSheet("font-weight:bold; min-width:28px;")
    app.bold_btn.clicked.connect(app.change_font_bold)
    text_group.grid.addWidget(app.bold_btn, 2, 0)

    app.italic_btn = QToolButton()
    app.italic_btn.setText("I")
    app.italic_btn.setCheckable(True)
    app.italic_btn.setStyleSheet("font-style:italic; min-width:28px;")
    app.italic_btn.clicked.connect(app.change_font_italic)
    text_group.grid.addWidget(app.italic_btn, 2, 1)

    layout.addWidget(text_group)