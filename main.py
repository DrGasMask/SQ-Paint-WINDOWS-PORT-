import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame, QToolButton, QGridLayout, QSlider, QFileDialog, 
                             QColorDialog, QMessageBox, QStatusBar, QScrollArea, QDialog,
                             QInputDialog, QFontComboBox, QSpinBox, QCheckBox)
from PyQt6.QtGui import QColor, QKeySequence, QShortcut, QPainter, QImage, QFont, QCursor, QIcon, QPixmap
import os
from PyQt6.QtCore import Qt, QPoint, QMimeData
from canvas import Canvas
from dialogs import ResizeDialog

class RibbonGroup(QWidget):
    def __init__(self, title):
        super().__init__()
        v = QVBoxLayout(self); v.setSpacing(4); v.setContentsMargins(6,6,6,6)
        self.grid = QGridLayout(); v.addLayout(self.grid)
        lbl = QLabel(title); lbl.setAlignment(Qt.AlignmentFlag.AlignCenter); lbl.setStyleSheet("color:#bfbfbf; font-size:11px;"); v.addWidget(lbl)

class LayerCard(QFrame):
    """Layer row with right-click context menu and proper drag reorder."""
    def __init__(self, idx, canvas, sqpaint_ref, parent=None):
        super().__init__(parent)
        self.idx = idx
        self.canvas = canvas
        self.app = sqpaint_ref
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        is_active = (idx == canvas.active_layer)
        bg = '#0078d4' if is_active else '#2e2e2e'
        self.setStyleSheet(
            f"background: {bg}; border-radius: 4px; margin: 2px;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6); lay.setSpacing(4)

        vis_btn = QToolButton()
        vis_btn.setText("👁️" if canvas.layer_visible[idx] else "◦")
        vis_btn.setFixedSize(24, 24)
        vis_btn.clicked.connect(lambda: sqpaint_ref.toggle_visibility(self.idx))

        name_lbl = QLabel(canvas.layer_names[idx])
        name_lbl.setStyleSheet("color: white; font-weight: bold; font-size: 11px;")

        del_btn = QToolButton(); del_btn.setText("×"); del_btn.setFixedSize(24, 24)
        del_btn.clicked.connect(lambda: canvas.delete_layer(self.idx))

        lay.addWidget(vis_btn)
        lay.addWidget(name_lbl, stretch=1)
        lay.addWidget(del_btn)

    def _show_context_menu(self, pos):
        from PyQt6.QtWidgets import QMenu
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu { background:#2a2a2a; color:white; border:1px solid #555; }
            QMenu::item:selected { background:#0078d4; }
            QMenu::item { padding: 6px 20px; }
        """)
        menu.addAction("Move Up",    lambda: self.canvas.move_layer(self.idx,
            min(len(self.canvas.layers)-1, self.idx+1)))
        menu.addAction("Move Down",  lambda: self.canvas.move_layer(self.idx,
            max(0, self.idx-1)))
        menu.addSeparator()
        menu.addAction("Rename",     lambda: self.app.rename_layer(self.idx))
        menu.addAction("Duplicate",  lambda: self.canvas.duplicate_layer(self.idx))
        menu.addSeparator()
        menu.addAction("Merge Down", lambda: self.canvas.merge_down(self.idx))
        menu.addAction("Merge Up",   lambda: self.canvas.merge_up(self.idx))
        menu.exec(self.mapToGlobal(pos))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.app.set_active_layer(self.idx)
            # Store drag state on the parent SQPaint so it survives panel refresh
            self.app._drag_idx = self.idx
            self.app._drag_y = event.globalPosition().y()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton): return
        if not hasattr(self.app, '_drag_idx') or self.app._drag_idx < 0: return
        dy = event.globalPosition().y() - self.app._drag_y
        if abs(dy) >= 30:
            n = len(self.canvas.layers)
            direction = 1 if dy < 0 else -1   # drag up = higher index = on top
            new_idx = max(0, min(n-1, self.app._drag_idx + direction))
            if new_idx != self.app._drag_idx:
                self.canvas.move_layer(self.app._drag_idx, new_idx)
                self.app._drag_idx = new_idx
                self.app._drag_y = event.globalPosition().y()

    def mouseReleaseEvent(self, event):
        if hasattr(self.app, '_drag_idx'):
            self.app._drag_idx = -1
        super().mouseReleaseEvent(event)


class SQPaint(QMainWindow):
    def __init__(self):
        super().__init__()
        self.canvas = Canvas(); self.setWindowTitle("SQ Paint v1.34"); self.resize(1300, 850)
        self.setStyleSheet("""
            QMainWindow { background:#1f1f1f; } 
            QFrame#Ribbon { background:#2a2a2a; border-bottom:1px solid #3a3a3a; } 
            QFrame#LayerPanel { background:#252525; border-left:1px solid #3a3a3a; min-width:200px; }
            QToolButton { color: white; border-radius: 4px; padding: 4px; font-weight: bold; } 
            QToolButton:hover { background: #444; } 
            QToolButton:checked { background: #0078d4; }
        """)
        
        self.status = QStatusBar(); self.setStatusBar(self.status)
        self.tool_lbl, self.coord_lbl, self.zoom_lbl, self.dim_lbl = QLabel("Tool: Pencil"), QLabel("0, 0px"), QLabel("100%"), QLabel("900 x 600px")
        for w in [self.tool_lbl, self.coord_lbl, self.zoom_lbl, self.dim_lbl]: 
            w.setStyleSheet("color: #aaa; padding: 0 10px;"); self.status.addPermanentWidget(w)
        
        self.canvas.status_callback = self.coord_lbl.setText
        self.canvas.zoom_callback = self.zoom_lbl.setText
        self.canvas.dim_callback = self.dim_lbl.setText
        self.canvas.color_picked_callback = self.change_color
        self.canvas.layers_changed_callback = self.refresh_layer_panel

        central = QWidget(); self.setCentralWidget(central); main_layout = QVBoxLayout(central); main_layout.setContentsMargins(0,0,0,0)
        ribbon = QFrame(); ribbon.setObjectName("Ribbon"); ribbon_layout = QHBoxLayout(ribbon)
        self.init_ribbon(ribbon_layout); main_layout.addWidget(ribbon)
        
        workspace = QHBoxLayout(); workspace.setSpacing(0)

        # Opacity slider panel — left side of canvas
        opacity_panel = QFrame()
        opacity_panel.setStyleSheet("QFrame { background:#222; border-right:1px solid #3a3a3a; }")
        opacity_panel.setFixedWidth(36)
        op_layout = QVBoxLayout(opacity_panel); op_layout.setContentsMargins(4, 8, 4, 8); op_layout.setSpacing(4)
        op_label = QLabel("A"); op_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        op_label.setStyleSheet("color:#aaa; font-size:10px; font-weight:bold;")
        self.opacity_slider = QSlider(Qt.Orientation.Vertical)
        self.opacity_slider.setRange(1, 255); self.opacity_slider.setValue(255)
        self.opacity_slider.setToolTip("Brush Opacity")
        self.opacity_slider.valueChanged.connect(self.change_opacity)
        self.opacity_lbl = QLabel("100%"); self.opacity_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.opacity_lbl.setStyleSheet("color:#aaa; font-size:9px;")
        op_layout.addWidget(op_label); op_layout.addWidget(self.opacity_slider, stretch=1); op_layout.addWidget(self.opacity_lbl)
        workspace.addWidget(opacity_panel)
        self.scroll = QScrollArea(); self.scroll.setWidget(self.canvas); self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter); self.scroll.setStyleSheet("QScrollArea { border:none; background:#2b2b2b; }")
        workspace.addWidget(self.scroll, stretch=1)
        
        self.layer_panel = QFrame(); self.layer_panel.setObjectName("LayerPanel")
        self.layer_vbox = QVBoxLayout(self.layer_panel); self.layer_list_container = QVBoxLayout()
        self.layer_vbox.addLayout(self.layer_list_container); self.layer_vbox.addStretch()
        add_lay_btn = QToolButton(); add_lay_btn.setText("+ Add Layer"); add_lay_btn.setFixedWidth(180)
        add_lay_btn.clicked.connect(self.canvas.add_new_layer); self.layer_vbox.addWidget(add_lay_btn)
        workspace.addWidget(self.layer_panel); main_layout.addLayout(workspace)
        
        self._drag_idx = -1
        self._drag_y = 0
        self.refresh_layer_panel(); self.setup_shortcuts()

    def init_ribbon(self, layout):
        file_group = RibbonGroup("File")
        for i, (ic, fn) in enumerate([("📂", self.open_file), ("💾", self.save_file)]):
            b = QToolButton(); b.setText(ic); b.clicked.connect(fn); file_group.grid.addWidget(b, 0, i)
        layout.addWidget(file_group)

        image_group = RibbonGroup("Image")
        for i, (ic, m) in enumerate([("↔️", "flip_h"), ("↕️", "flip_v"), ("⟳90", "rot_90"), ("⟳180", "rot_180")]):
            b = QToolButton(); b.setText(ic); b.clicked.connect(lambda ch, mode=m: self.transform_or_selection(mode))
            image_group.grid.addWidget(b, i//2, i%2)
        res_btn = QToolButton(); res_btn.setText("Resize"); res_btn.clicked.connect(self.show_resize_dialog)
        image_group.grid.addWidget(res_btn, 0, 2, 2, 1); layout.addWidget(image_group)

        view_group = RibbonGroup("View")
        b_in = QToolButton(); b_in.setText("➕"); b_in.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor + 0.1))
        b_out = QToolButton(); b_out.setText("➖"); b_out.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor - 0.1))
        b_res = QToolButton(); b_res.setText("1:1"); b_res.clicked.connect(lambda: self.canvas.set_zoom(1.0))
        view_group.grid.addWidget(b_in, 0, 0); view_group.grid.addWidget(b_out, 0, 1); view_group.grid.addWidget(b_res, 1, 0, 1, 2); layout.addWidget(view_group)

        tools_group = RibbonGroup("Tools"); self.tools = {}
        t_icons = [("select","✂️"),("pencil","✏️"),("eraser","🧽"),("fill","🫗"),
                   ("picker","🧪"),("text","A"),("line","╱"),("rect","⬜"),
                   ("ellipse","⭕"),("rounded_rect","▢"),("triangle","△"),
                   ("diamond","◇"),("pentagon","⬠"),("hexagon","⬡"),
                   ("star","★"),("arrow","➤")]
        for i, (n, ic) in enumerate(t_icons):
            b = QToolButton(); b.setText(ic); b.setCheckable(True)
            b.clicked.connect(lambda ch, name=n: self.set_tool(name)); self.tools[n] = b
            tools_group.grid.addWidget(b, i // 8, i % 8)
        self.tools["pencil"].setChecked(True)
        self.size_slider = QSlider(Qt.Orientation.Horizontal); self.size_slider.setRange(1, 100); self.size_slider.setValue(3)
        self.size_slider.valueChanged.connect(self.change_size); tools_group.grid.addWidget(self.size_slider, 2, 0, 1, 8); layout.addWidget(tools_group)

        edit_group = RibbonGroup("Edit")
        u_b, r_b, c_b = QToolButton(), QToolButton(), QToolButton()
        u_b.setText("↩️"); u_b.clicked.connect(self.canvas.undo); r_b.setText("↪️"); r_b.clicked.connect(self.canvas.redo)
        c_b.setText("🗑️"); c_b.clicked.connect(self.clear_canvas)
        edit_group.grid.addWidget(u_b, 0, 0); edit_group.grid.addWidget(r_b, 0, 1); edit_group.grid.addWidget(c_b, 1, 0, 1, 2); layout.addWidget(edit_group)

        colours_group = RibbonGroup("Colours")
        self.swatch = QLabel(); self.swatch.setFixedSize(24, 24); self.swatch.setStyleSheet("background:black; border:1px solid white;")
        palette = ["black", "white", "red", "green", "blue", "yellow", "purple", "orange"]
        for i, c in enumerate(palette):
            b = QToolButton(); b.setFixedSize(20, 20); b.setStyleSheet(f"background:{c}; border-radius:10px; border: 1px solid #555;")
            b.clicked.connect(lambda ch, col=c: self.change_color(QColor(col))); colours_group.grid.addWidget(b, i//4, i%4)
        custom_btn = QToolButton(); custom_btn.setText("🎨"); custom_btn.clicked.connect(self.pick_custom_color)
        colours_group.grid.addWidget(custom_btn, 0, 4, 2, 1); colours_group.grid.addWidget(self.swatch, 0, 5, 2, 1)
        self.recent_row = QWidget(); self.recent_row_layout = QHBoxLayout(self.recent_row); self.recent_row_layout.setContentsMargins(0,0,0,0)
        colours_group.grid.addWidget(self.recent_row, 2, 0, 1, 6); layout.addWidget(colours_group)

        # Font Group
        font_group = RibbonGroup("Font")
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(__import__("PyQt6.QtGui", fromlist=["QFont"]).QFont("Arial"))
        self.font_combo.setFixedWidth(130)
        self.font_combo.currentFontChanged.connect(self.change_font_family)
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 144); self.font_size_spin.setValue(14)
        self.font_size_spin.setFixedWidth(55)
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        self.bold_btn = QToolButton(); self.bold_btn.setText("B")
        self.bold_btn.setCheckable(True)
        self.bold_btn.setStyleSheet("font-weight:bold; min-width:28px;")
        self.bold_btn.clicked.connect(self.change_font_bold)
        self.italic_btn = QToolButton(); self.italic_btn.setText("I")
        self.italic_btn.setCheckable(True)
        self.italic_btn.setStyleSheet("font-style:italic; min-width:28px;")
        self.italic_btn.clicked.connect(self.change_font_italic)
        font_group.grid.addWidget(self.font_combo, 0, 0, 1, 2)
        font_group.grid.addWidget(self.font_size_spin, 0, 2)
        font_group.grid.addWidget(self.bold_btn, 1, 0)
        font_group.grid.addWidget(self.italic_btn, 1, 1)
        layout.addWidget(font_group); layout.addStretch()

    def refresh_layer_panel(self):
        while self.layer_list_container.count():
            item = self.layer_list_container.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for i in reversed(range(len(self.canvas.layers))):
            card = LayerCard(i, self.canvas, self)
            self.layer_list_container.addWidget(card)


    def set_active_layer(self, idx): self.canvas.active_layer = idx; self.canvas._invalidate_composite(); self.refresh_layer_panel(); self.canvas.update()
    def toggle_visibility(self, idx): self.canvas.layer_visible[idx] = not self.canvas.layer_visible[idx]; self.canvas._invalidate_composite(); self.refresh_layer_panel(); self.canvas.update()
    def rename_layer(self, idx):
        current = self.canvas.layer_names[idx]
        name, ok = QInputDialog.getText(self, "Rename Layer", "Layer name:", text=current)
        if ok and name.strip(): self.canvas.rename_layer(idx, name)
    def change_opacity(self, value):
        self.canvas.pen_opacity = value
        self.opacity_lbl.setText(f"{int(value / 255 * 100)}%")
    def transform_or_selection(self, mode):
        """If a selection is active, transform just the selection buffer.
        Otherwise transform the whole canvas as normal."""
        c = self.canvas
        if c.selection_state in ["selected", "moving", "rotating"] and c.selection_buffer:
            from PyQt6.QtGui import QTransform
            buf = c.selection_buffer
            if mode == "rot_90":
                buf = buf.transformed(QTransform().rotate(90))
            elif mode == "rot_180":
                buf = buf.transformed(QTransform().rotate(180))
            elif mode == "flip_h":
                buf = buf.mirrored(True, False)
            elif mode == "flip_v":
                buf = buf.mirrored(False, True)
            c.selection_buffer = buf
            # Keep selection_rect centered, adjust size for 90-deg rotations
            if mode in ("rot_90", "rot_180") and mode == "rot_90":
                old_r = c.selection_rect.normalized()
                cx, cy = old_r.center().x(), old_r.center().y()
                nw, nh = old_r.height(), old_r.width()
                c.selection_rect.setRect(cx - nw//2, cy - nh//2, nw, nh)
            c.update()
        else:
            c.transform_image(mode)

    def set_tool(self, tool):
        self.canvas.commit_selection(); self.canvas.finalize_text(); self.canvas.tool = tool
        for name, btn in self.tools.items(): btn.setChecked(name == tool)
        self.tool_lbl.setText(f"Tool: {tool.capitalize()}")
    def change_color(self, color):
        if not isinstance(color, QColor): color = QColor(color)
        self.canvas.pen_color = color; self.swatch.setStyleSheet(f"background: {color.name()}; border: 1px solid white;")
        if color in self.canvas.recent_colors: self.canvas.recent_colors.remove(color)
        self.canvas.recent_colors.appendleft(color); self.refresh_recent_colors()
    def refresh_recent_colors(self):
        while self.recent_row_layout.count():
            item = self.recent_row_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        for color in list(self.canvas.recent_colors):
            b = QToolButton(); b.setFixedSize(16, 16); b.setStyleSheet(f"background:{color.name()}; border-radius:8px; border: 1px solid #444;")
            b.clicked.connect(lambda ch, col=color: self.change_color(col)); self.recent_row_layout.addWidget(b)
        self.recent_row_layout.addStretch()
    def change_size(self, value): self.canvas.pen_width = value; self.status.showMessage(f"Brush Size: {value}px", 2000)
    def change_font_family(self, font): self.canvas.font_family = font.family()
    def change_font_size(self, value): self.canvas.font_size = value
    def change_font_bold(self): self.canvas.font_bold = self.bold_btn.isChecked()
    def change_font_italic(self): self.canvas.font_italic = self.italic_btn.isChecked()
    def clear_canvas(self): self.canvas.commit_selection(); self.canvas.save_state(); self.canvas.get_active().fill(Qt.GlobalColor.white if self.canvas.active_layer == 0 else Qt.GlobalColor.transparent); self.canvas._invalidate_composite(); self.canvas.update()
    def pick_custom_color(self):
        color = QColorDialog.getColor()
        if color.isValid(): self.change_color(color)
    def show_resize_dialog(self):
        dlg = ResizeDialog(self.canvas.layers[0].width(), self.canvas.layers[0].height(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            w, h, ax, ay = dlg.get_values(); self.canvas.resize_canvas(w, h, ax, ay)
    def open_file(self):
        self.canvas.commit_selection(); path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg)")
        if path:
            self.canvas.save_state()
            # Convert to RGB32 first to normalize pixel format — this ensures
            # flood fill can sample pixel values consistently regardless of
            # the source image's original format (JPEG, PNG, etc.)
            raw = QImage(path).convertToFormat(QImage.Format.Format_RGB32)
            base = QImage(raw.size(), QImage.Format.Format_ARGB32_Premultiplied)
            base.fill(Qt.GlobalColor.white)
            p = QPainter(base)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            p.drawImage(0, 0, raw)
            p.end()
            self.canvas.layers = [base]
            self.canvas.layer_names = ["Background"]; self.canvas.layer_visible = [True]
            self.canvas.active_layer = 0; self.canvas._invalidate_composite()
            self.refresh_layer_panel(); self.canvas.set_zoom(self.canvas.zoom_factor)
            self.canvas.modified = False
    def save_file(self):
        self.canvas.commit_selection(); path, filt = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG (*.png);;JPEG (*.jpg)")
        if path:
            if not path.lower().endswith((".png", ".jpg", ".jpeg")): path += ".jpg" if "JPEG" in filt else ".png"
            comp = self.canvas.get_composite()
            if path.lower().endswith((".jpg", ".jpeg")):
                flat = QImage(comp.size(), QImage.Format.Format_RGB32); flat.fill(Qt.GlobalColor.white); p = QPainter(flat); p.drawImage(0, 0, comp); p.end(); comp = flat
            if not comp.save(path): QMessageBox.warning(self, "Save Error", f"Could not save to:\n{path}")
            else: self.canvas.modified = False
    def setup_shortcuts(self):
        map_tools = [("M","select"), ("P","pencil"), ("E","eraser"), ("B","fill"), ("I","picker"), ("T","text"), ("L","line"), ("R","rect"), ("O","ellipse")]
        for k, t in map_tools: QShortcut(QKeySequence(k), self, lambda tool=t: self.set_tool(tool))
        QShortcut(QKeySequence("Ctrl+Z"), self, self.canvas.undo); QShortcut(QKeySequence("Ctrl+Y"), self, self.canvas.redo)
    def closeEvent(self, event):
        if self.canvas.modified and QMessageBox.question(self, 'Save?', "Unsaved changes. Quit?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: event.ignore()
        else: event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Set app-wide icon (shows on taskbar and window title)
    _base = getattr(__import__("sys"), "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    _icon_path = os.path.join(_base, "sq_paint_icon.png")
    if not os.path.exists(_icon_path):
        _icon_path = os.path.join(_base, "SQ_Paint_Logo.png")
    if os.path.exists(_icon_path):
        app.setWindowIcon(QIcon(_icon_path))

    # Splash screen
    from splash import SQSplash
    splash = SQSplash()
    splash.show()
    app.processEvents()

    # Build main window while splash is visible
    window = SQPaint()
    if os.path.exists(_icon_path):
        window.setWindowIcon(QIcon(_icon_path))

    # Show main window and close splash after a short delay
    from PyQt6.QtCore import QTimer
    def _launch():
        window.show()
        splash.finish(window)
    QTimer.singleShot(1200, _launch)

    sys.exit(app.exec())
