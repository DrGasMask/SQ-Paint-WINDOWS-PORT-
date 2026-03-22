import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QFrame, QToolButton, QGridLayout, QSlider, QFileDialog,
                             QColorDialog, QMessageBox, QStatusBar, QScrollArea, QDialog,
                             QInputDialog, QFontComboBox, QSpinBox, QCheckBox)
from PyQt6.QtGui import QColor, QKeySequence, QShortcut, QPainter, QImage, QFont, QCursor, QIcon, QPixmap
import os
from PyQt6.QtCore import Qt, QPoint, QMimeData
from canvas import Canvas
from dialogs import ResizeDialog, SaveFormatDialog
from ui_components import RibbonGroup
from tools import _icon, _set_icon_btn, setup_tools_group, setup_brush_group, setup_text_group
from file_operations import save_file
from layer_operations import refresh_layer_panel, set_active_layer, toggle_visibility
from settings_dialog import SettingsDialog


class SQPaint(QMainWindow):
    def __init__(self):
        super().__init__()
        self.canvas = Canvas(); self.setWindowTitle("SQ Paint v1.45"); self.resize(1300, 850)

        # App-wide settings with sensible defaults
        self.settings = {
            'theme':          'dark',
            'experimental':   False,
            'brush_cursor':   True,
            'antialiasing':   True,
            'smooth_drawing': False,
            'round_lines':    True,
            'fill_tolerance': 30,
            'max_undo':       30,
            'confirm_clear':  True,
        }
        
        self.setStyleSheet("""
            QMainWindow { background:#1f1f1f; } 
            QFrame#Ribbon { background:#2a2a2a; border-bottom:1px solid #3a3a3a; } 
            QFrame#LayerPanel { background:#252525; border-left:1px solid #3a3a3a; min-width:200px; }
            QToolButton { color: white; border-radius: 4px; padding: 4px; font-weight: bold; } 
            QToolButton:hover { background: #444; } 
            QToolButton:checked { background: #0078d4; }
        """)
        
        self.status = QStatusBar(); self.setStatusBar(self.status)
        self.tool_lbl, self.coord_lbl, self.zoom_lbl, self.dim_lbl = QLabel("Tool: Pencil"), QLabel("0, 0px"), QLabel("100%"), QLabel("2048 x 1365px")
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

        # Open button — dropdown menu
        from PyQt6.QtWidgets import QMenu
        open_btn = QToolButton()
        _set_icon_btn(open_btn, "ic_open", "📂")
        open_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        open_menu = QMenu(open_btn)
        open_menu.setStyleSheet("""
            QMenu { background:#2a2a2a; color:white; border:1px solid #555; }
            QMenu::item { padding:6px 20px; }
            QMenu::item:selected { background:#0078d4; }
        """)
        open_menu.addAction("Import .sqish", self.import_sqish)
        open_menu.addAction("Import image",  self.import_image)
        open_btn.setMenu(open_menu)
        file_group.grid.addWidget(open_btn, 0, 0)

        save_btn = QToolButton(); _set_icon_btn(save_btn, "ic_save", "💾")
        save_btn.clicked.connect(self.save_file)
        file_group.grid.addWidget(save_btn, 0, 1)
        layout.addWidget(file_group)

        image_group = RibbonGroup("Image")
        for i, (ic_name, fallback, m) in enumerate([
                ("ic_flip_h", "↔️", "flip_h"), ("ic_flip_v", "↕️", "flip_v"),
                ("ic_rot90", "⟳90", "rot_90"), ("ic_rot180", "⟳180", "rot_180")]):
            b = QToolButton(); _set_icon_btn(b, ic_name, fallback)
            b.clicked.connect(lambda ch, mode=m: self.transform_or_selection(mode))
            image_group.grid.addWidget(b, i//2, i%2)
        res_btn = QToolButton(); _set_icon_btn(res_btn, "ic_resize", "Resize"); res_btn.clicked.connect(self.show_resize_dialog)
        image_group.grid.addWidget(res_btn, 0, 2, 2, 1); layout.addWidget(image_group)

        view_group = RibbonGroup("View")
        b_in = QToolButton(); _set_icon_btn(b_in, "ic_zoom_in", "➕")
        b_in.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor + 0.1))
        b_out = QToolButton(); _set_icon_btn(b_out, "ic_zoom_out", "➖")
        b_out.clicked.connect(lambda: self.canvas.set_zoom(self.canvas.zoom_factor - 0.1))
        b_res = QToolButton(); _set_icon_btn(b_res, "ic_zoom_reset", "1:1")
        b_res.clicked.connect(lambda: self.canvas.set_zoom(1.0))
        view_group.grid.addWidget(b_in, 0, 0); view_group.grid.addWidget(b_out, 0, 1); view_group.grid.addWidget(b_res, 1, 0, 1, 2); layout.addWidget(view_group)

        # Use the new tools setup functions
        setup_tools_group(layout, self)
        setup_brush_group(layout, self)
        setup_text_group(layout, self)

        edit_group = RibbonGroup("Edit")
        u_b, r_b, c_b = QToolButton(), QToolButton(), QToolButton()
        _set_icon_btn(u_b, "ic_undo", "↩️"); u_b.clicked.connect(self.canvas.undo)
        _set_icon_btn(r_b, "ic_redo", "↪️"); r_b.clicked.connect(self.canvas.redo)
        _set_icon_btn(c_b, "ic_clear", "🗑️"); c_b.clicked.connect(self.clear_canvas)
        edit_group.grid.addWidget(u_b, 0, 0); edit_group.grid.addWidget(r_b, 0, 1); edit_group.grid.addWidget(c_b, 1, 0, 1, 2); layout.addWidget(edit_group)

        colours_group = RibbonGroup("Colours")
        self.swatch = QLabel(); self.swatch.setFixedSize(24, 24)
        self.swatch.setStyleSheet("background:black; border:1px solid white;")
        # Full 20-colour MS Paint style persistent palette
        PALETTE = [
            "#000000","#ffffff","#7f7f7f","#c3c3c3",
            "#880015","#b97a57","#ff0000","#ffaec9",
            "#ff7f27","#ffc90e","#fff200","#efe4b0",
            "#22b14c","#b5e61d","#00a2e8","#99d9ea",
            "#3f48cc","#7092be","#a349a4","#c8bfe7",
        ]
        for i, c in enumerate(PALETTE):
            b = QToolButton(); b.setFixedSize(18, 18)
            b.setStyleSheet(f"background:{c}; border:1px solid #555; border-radius:2px;")
            b.clicked.connect(lambda ch, col=c: self.change_color(QColor(col)))
            colours_group.grid.addWidget(b, i // 10, i % 10)
        custom_btn = QToolButton(); custom_btn.setText("＋")
        custom_btn.setToolTip("Custom colour"); custom_btn.clicked.connect(self.pick_custom_color)
        colours_group.grid.addWidget(custom_btn, 0, 10)
        colours_group.grid.addWidget(self.swatch, 1, 10)
        self.recent_row = QWidget()
        self.recent_row_layout = QHBoxLayout(self.recent_row)
        self.recent_row_layout.setContentsMargins(0,0,0,0)
        colours_group.grid.addWidget(self.recent_row, 2, 0, 1, 11)
        layout.addWidget(colours_group)

        # Settings button — top right
        settings_btn = QToolButton()
        _set_icon_btn(settings_btn, 'ic_settings', '⚙️')
        settings_btn.setToolTip('Settings')
        settings_btn.clicked.connect(self.show_settings)
        layout.addWidget(settings_btn)
        layout.addStretch()

    def refresh_layer_panel(self):
        refresh_layer_panel(self)

    def set_active_layer(self, idx):
        set_active_layer(self, idx)

    def toggle_visibility(self, idx):
        toggle_visibility(self, idx)

    def rename_layer(self, idx):
        from layer_operations import rename_layer
        rename_layer(self, idx)
    def change_opacity(self, value):
        self.canvas.pen_opacity = value
        self.opacity_lbl.setText(f"{int(value / 255 * 100)}%")
    def transform_or_selection(self, mode):
        """If a selection is active, transform just the selection buffer.
        Otherwise transform the whole canvas as normal."""
        c = self.canvas
        sm = c.selection_manager
        if sm.selection_state in ["selected", "moving", "rotating"] and sm.selection_buffer:
            from PyQt6.QtGui import QTransform
            buf = sm.selection_buffer
            if mode == "rot_90":
                buf = buf.transformed(QTransform().rotate(90))
            elif mode == "rot_180":
                buf = buf.transformed(QTransform().rotate(180))
            elif mode == "flip_h":
                buf = buf.mirrored(True, False)
            elif mode == "flip_v":
                buf = buf.mirrored(False, True)
            sm.selection_buffer = buf
            # Keep selection_rect centered, adjust size for 90-deg rotations
            if mode == "rot_90":
                old_r = sm.selection_rect.normalized()
                cx, cy = old_r.center().x(), old_r.center().y()
                nw, nh = old_r.height(), old_r.width()
                sm.selection_rect.setRect(cx - nw//2, cy - nh//2, nw, nh)
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
    def _on_tolerance_changed(self, val):
        self.canvas.fill_tolerance = val
        self.settings['fill_tolerance'] = val
        self.tol_lbl.setText(str(val))

    def change_font_family(self, font):
        self.canvas.font_family = font.family()
        if self.canvas.text_tool.active: self.canvas.update()
    def change_font_size(self, value):
        self.canvas.font_size = value
        if self.canvas.text_tool.active: self.canvas.update()
    def change_font_bold(self):
        self.canvas.font_bold = self.bold_btn.isChecked()
        if self.canvas.text_tool.active: self.canvas.update()
    def change_font_italic(self):
        self.canvas.font_italic = self.italic_btn.isChecked()
        if self.canvas.text_tool.active: self.canvas.update()
    def clear_canvas(self):
        if self.settings.get('confirm_clear', True):
            from PyQt6.QtWidgets import QMessageBox
            r = QMessageBox.question(self, 'Clear Canvas', 'Clear the active layer?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes: return
        self.canvas.commit_selection(); self.canvas.save_state()
        self.canvas.get_active().fill(Qt.GlobalColor.white if self.canvas.active_layer == 0 else Qt.GlobalColor.transparent)
        self.canvas._invalidate_composite(); self.canvas.update()
    def pick_custom_color(self):
        color = QColorDialog.getColor()
        if color.isValid(): self.change_color(color)
    def show_resize_dialog(self):
        dlg = ResizeDialog(self.canvas.layers[0].width(), self.canvas.layers[0].height(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            w, h, ax, ay = dlg.get_values(); self.canvas.resize_canvas(w, h, ax, ay)
    

    def import_sqish(self):
        from file_operations import import_sqish
        import_sqish(self)

    def import_image(self):
        from file_operations import import_image
        import_image(self)

    def open_file(self):
        # kept for Ctrl+O shortcut
        from file_operations import import_image
        import_image(self)

    def save_file(self):
        save_file(self)

    def _do_save(self):
        self.canvas.commit_selection()
        dlg = SaveFormatDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted: return
        fmt = dlg.get_format()
        if fmt == "sqish":
            path, _ = QFileDialog.getSaveFileName(self, "Save Project", "",
                "SQ Paint Project (*.sqish)")
            if not path: return
            if not path.lower().endswith(".sqish"): path += ".sqish"
            if self.canvas.save_sqish(path):
                self.canvas.modified = False
            else:
                QMessageBox.warning(self, "Save Error", f"Could not save:\n{path}")
        else:
            filter_map = {"png": "PNG (*.png)", "jpg": "JPEG (*.jpg)", "bmp": "Bitmap (*.bmp)"}
            path, _ = QFileDialog.getSaveFileName(self, "Save Image", "",
                filter_map.get(fmt, "PNG (*.png)"))
            if not path: return
            if not path.lower().endswith(f".{fmt}"): path += f".{fmt}"
            comp = self.canvas.get_composite()
            if fmt == "png":
                # Convert premultiplied back to straight alpha for correct PNG export
                out = comp.convertToFormat(QImage.Format.Format_ARGB32)
            elif fmt in ("jpg", "bmp"):
                # Flatten transparency to white background
                out = QImage(comp.size(), QImage.Format.Format_RGB32)
                out.fill(Qt.GlobalColor.white)
                p = QPainter(out)
                p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                p.drawImage(0, 0, comp); p.end()
            else:
                out = comp
            if not out.save(path):
                QMessageBox.warning(self, "Save Error", f"Could not save:\n{path}")
            else:
                self.canvas.modified = False
    def setup_shortcuts(self):
        # Tool shortcuts
        map_tools = [("M","select"), ("P","pencil"), ("E","eraser"),
                     ("B","fill"), ("F","fill"), ("I","picker"),
                     ("T","text"), ("L","line"), ("R","rect"), ("O","ellipse")]
        for k, t in map_tools: QShortcut(QKeySequence(k), self, lambda tool=t: self.set_tool(tool))

        # File
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_canvas)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_file)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_file)
        QShortcut(QKeySequence("F12"),    self, self.save_as)
        QShortcut(QKeySequence("F11"),    self, self.toggle_fullscreen)

        # Edit
        QShortcut(QKeySequence("Ctrl+Z"), self, self.canvas.undo)
        QShortcut(QKeySequence("Ctrl+Y"), self, self.canvas.redo)
        QShortcut(QKeySequence("Ctrl+C"), self, self.copy_selection)
        QShortcut(QKeySequence("Ctrl+X"), self, self.cut_selection)
        QShortcut(QKeySequence("Ctrl+V"), self, self.paste_from_clipboard)
        QShortcut(QKeySequence("Ctrl+A"), self, self.select_all)
        QShortcut(QKeySequence("Delete"), self, self.delete_selection)
        QShortcut(QKeySequence("Escape"), self, self.canvas.cancel_selection)
        QShortcut(QKeySequence("Ctrl+Shift+X"), self, self.crop_to_selection)

        # View / zoom
        QShortcut(QKeySequence("Ctrl+PgUp"),  self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor + 0.1))
        QShortcut(QKeySequence("Ctrl+PgDown"), self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor - 0.1))
        QShortcut(QKeySequence("Ctrl++"),      self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor + 0.1))
        QShortcut(QKeySequence("Ctrl+="),      self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor + 0.1))
        QShortcut(QKeySequence("Ctrl+-"),      self, lambda: self.canvas.set_zoom(self.canvas.zoom_factor - 0.1))
        QShortcut(QKeySequence("Ctrl+1"), self, lambda: self.canvas.set_zoom(1.0))
        QShortcut(QKeySequence("Ctrl+0"), self, self.zoom_to_fit)

        # Image
        QShortcut(QKeySequence("Ctrl+W"), self, self.show_resize_dialog)

        # Arrow keys — nudge selection 1px
        QShortcut(QKeySequence("Up"),    self, lambda: self.canvas.nudge_selection(0, -1))
        QShortcut(QKeySequence("Down"),  self, lambda: self.canvas.nudge_selection(0,  1))
        QShortcut(QKeySequence("Left"),  self, lambda: self.canvas.nudge_selection(-1, 0))
        QShortcut(QKeySequence("Right"), self, lambda: self.canvas.nudge_selection( 1, 0))

    # ── File actions ──────────────────────────────────────────────────────────
    def new_canvas(self):
        if self.canvas.modified:
            from PyQt6.QtWidgets import QMessageBox
            r = QMessageBox.question(self, "New Canvas", "Discard unsaved changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if r != QMessageBox.StandardButton.Yes: return
        self.canvas.commit_selection()
        self.canvas.save_state()
        _QImage = __import__("PyQt6.QtGui", fromlist=["QImage"]).QImage
        _fmt = _QImage.Format.Format_ARGB32_Premultiplied
        bg = _QImage(2048, 1365, _fmt); bg.fill(Qt.GlobalColor.white)
        l1 = _QImage(2048, 1365, _fmt); l1.fill(Qt.GlobalColor.transparent)
        self.canvas.layers = [bg, l1]
        self.canvas.layer_names = ["Background", "Layer 1"]
        self.canvas.layer_visible = [True, True]
        self.canvas.active_layer = 1
        self.canvas._invalidate_composite()
        self.canvas.modified = False
        self.refresh_layer_panel()
        self.canvas.set_zoom(self.canvas.zoom_factor)

    def save_as(self):
        self._do_save()

    def toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

    def zoom_to_fit(self):
        """Zoom so canvas fits within the scroll area."""
        sa = self.scroll
        factor_w = (sa.width()  - 20) / self.canvas.layers[0].width()
        factor_h = (sa.height() - 20) / self.canvas.layers[0].height()
        self.canvas.set_zoom(min(factor_w, factor_h))

    # ── Edit actions ──────────────────────────────────────────────────────────
    def copy_selection(self):
        self.canvas.copy_selection()

    def cut_selection(self):
        self.canvas.cut_selection()

    def paste_from_clipboard(self):
        self.canvas.paste_from_clipboard()
        for name, btn in self.tools.items():
            btn.setChecked(name == "select")
        self.tool_lbl.setText("Tool: Select")

    def select_all(self):
        if self.canvas.text_tool.active:
            self.canvas.text_tool.text_input.selectAll()
            self.canvas.update()
            return
        self.canvas.select_all()
        for name, btn in self.tools.items():
            btn.setChecked(name == "select")
        self.tool_lbl.setText("Tool: Select")

    def delete_selection(self):
        self.canvas.delete_selection()

    def crop_to_selection(self):
        """Crop canvas to the current selection rect."""
        c = self.canvas
        sm = c.selection_manager
        if sm.selection_state not in ["selected", "moving"] or sm.selection_rect.isNull():
            return
        r = sm.selection_rect.normalized().intersected(c.layers[0].rect())
        if r.width() < 2 or r.height() < 2: return
        c.commit_selection()
        c.save_state()
        for i in range(len(c.layers)):
            c.layers[i] = c.layers[i].copy(r)
        c._invalidate_composite()
        c.set_zoom(c.zoom_factor)

    # ── Settings ──────────────────────────────────────────────────────────
    def show_settings(self):
        dlg = SettingsDialog(self.settings, self)
        dlg.theme_changed.connect(self._apply_theme)
        dlg.aa_changed.connect(self._apply_aa)
        dlg.brush_cursor_changed.connect(self._apply_brush_cursor)
        dlg.tolerance_changed.connect(self._apply_tolerance)
        dlg.max_undo_changed.connect(self._apply_max_undo)
        dlg.round_lines_changed.connect(self._apply_round_lines)
        dlg.smooth_changed.connect(lambda v: self.settings.update({'smooth_drawing': v}))
        dlg.confirm_clear_changed.connect(lambda v: self.settings.update({'confirm_clear': v}))
        dlg.experimental_changed.connect(lambda v: self.settings.update({'experimental': v}))
        dlg.exec()
        self.settings = dlg.get_settings()

    def _apply_theme(self, theme):
        self.settings['theme'] = theme
        if theme == 'light':
            self.setStyleSheet("""
                QMainWindow { background:#f0f0f0; }
                QFrame#Ribbon { background:#e8e8e8; border-bottom:1px solid #ccc; }
                QFrame#LayerPanel { background:#e0e0e0; border-left:1px solid #ccc; min-width:200px; }
                QToolButton { color: #111; border-radius:4px; padding:4px; font-weight:bold; }
                QToolButton:hover { background:#ccc; }
                QToolButton:checked { background:#0078d4; color:white; }
                QScrollArea { border:none; background:#d8d8d8; }
            """)
        else:
            self.setStyleSheet("""
                QMainWindow { background:#1f1f1f; }
                QFrame#Ribbon { background:#2a2a2a; border-bottom:1px solid #3a3a3a; }
                QFrame#LayerPanel { background:#252525; border-left:1px solid #3a3a3a; min-width:200px; }
                QToolButton { color: white; border-radius:4px; padding:4px; font-weight:bold; }
                QToolButton:hover { background:#444; }
                QToolButton:checked { background:#0078d4; }
            """)

    def _apply_aa(self, enabled):
        self.settings['antialiasing'] = enabled
        self.canvas.use_antialiasing = enabled
        self.canvas.update()

    def _apply_brush_cursor(self, enabled):
        self.settings['brush_cursor'] = enabled
        self.canvas.show_brush_cursor = enabled
        self.canvas.update()

    def _apply_tolerance(self, val):
        self.settings['fill_tolerance'] = val
        self.canvas.fill_tolerance = val
        # Sync ribbon tolerance slider without triggering a feedback loop
        if hasattr(self, 'tol_slider'):
            self.tol_slider.blockSignals(True)
            self.tol_slider.setValue(val)
            self.tol_slider.blockSignals(False)
        if hasattr(self, 'tol_lbl'):
            self.tol_lbl.setText(str(val))

    def _apply_max_undo(self, val):
        self.settings['max_undo'] = val
        self.canvas.undo_redo_manager.max_undo = val

    def _apply_round_lines(self, enabled):
        self.settings['round_lines'] = enabled
        self.canvas.round_lines = enabled
        self.canvas.update()

    def closeEvent(self, event):
        if self.canvas.modified and QMessageBox.question(self, 'Save?', "Unsaved changes. Quit?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: event.ignore()
        else: event.accept()

if __name__ == "__main__":
    # Set 125% UI scale before QApplication is created
    # This only applies to SQ Paint, not the whole system
    import os
    os.environ["QT_SCALE_FACTOR"] = "1.25"

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
