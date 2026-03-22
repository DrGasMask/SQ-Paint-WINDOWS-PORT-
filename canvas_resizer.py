from PyQt6.QtCore import QRect, QPoint
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter

EDGE_HANDLE_SIZE = 10   # size of canvas edge resize handles
EDGE_MARGIN = 20        # extra space outside canvas for handles


class CanvasResizer:
    def __init__(self, canvas):
        self.canvas = canvas
        # Canvas edge drag-resize state
        self._edge_drag = None   # None | "right" | "bottom" | "corner"
        self._edge_drag_start = QPoint()
        self._edge_drag_orig_w = 0
        self._edge_drag_orig_h = 0
        self._edge_drag_w = 0
        self._edge_drag_h = 0

    def _canvas_pixel_size(self):
        """Return current canvas size in screen pixels (without margin)."""
        w = int(self.canvas.layers[0].width() * self.canvas.zoom_factor)
        h = int(self.canvas.layers[0].height() * self.canvas.zoom_factor)
        return w, h

    def _edge_handle_rects(self):
        """Return (right_rect, bottom_rect, corner_rect) in screen coords."""
        w, h = self._canvas_pixel_size()
        hs = EDGE_HANDLE_SIZE
        right  = QRect(w - hs//2, h//2 - hs//2, hs, hs)
        bottom = QRect(w//2 - hs//2, h - hs//2, hs, hs)
        corner = QRect(w - hs//2, h - hs//2, hs, hs)
        return right, bottom, corner

    def _hit_edge_handle(self, pos):
        right, bottom, corner = self._edge_handle_rects()
        # Inflate hit area for easier grabbing
        inflate = 4
        if corner.adjusted(-inflate,-inflate,inflate,inflate).contains(pos):  return "corner"
        if right.adjusted(-inflate,-inflate,inflate,inflate).contains(pos):   return "right"
        if bottom.adjusted(-inflate,-inflate,inflate,inflate).contains(pos):  return "bottom"
        return None

    def resize_canvas(self, new_w, new_h, anchor_x, anchor_y):
        self.canvas.selection_manager.commit_selection()
        self.canvas.undo_redo_manager.save_state()
        for i in range(len(self.canvas.layers)):
            from PyQt6.QtGui import QImage
            new_img = QImage(new_w, new_h, QImage.Format.Format_ARGB32_Premultiplied)
            new_img.fill(Qt.GlobalColor.white if i == 0 else Qt.GlobalColor.transparent)
            p = QPainter(new_img)
            x = int((new_w - self.canvas.layers[i].width()) * anchor_x)
            y = int((new_h - self.canvas.layers[i].height()) * anchor_y)
            p.drawImage(x, y, self.canvas.layers[i]); p.end()
            self.canvas.layers[i] = new_img
        self.canvas._invalidate_composite(); self.canvas.set_zoom(self.canvas.zoom_factor)