# ui_components.py
# Contains UI component classes like RibbonGroup and LayerCard

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QGridLayout, QFrame, QHBoxLayout, QToolButton
from PyQt6.QtCore import Qt

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

    def mouseMoveEvent(self, event):
        if self.app._drag_idx == self.idx and event.buttons() & Qt.MouseButton.LeftButton:
            # Calculate new position based on mouse movement
            dy = event.globalPosition().y() - self.app._drag_y
            if abs(dy) > 10:  # Threshold to start drag
                new_idx = self.idx
                if dy > 20: new_idx = min(len(self.canvas.layers)-1, self.idx+1)
                elif dy < -20: new_idx = max(0, self.idx-1)
                if new_idx != self.idx:
                    self.canvas.move_layer(self.idx, new_idx)
                    self.app._drag_idx = new_idx
                    self.app._drag_y = event.globalPosition().y()
                    self.app.refresh_layer_panel()

    def mouseReleaseEvent(self, event):
        self.app._drag_idx = -1