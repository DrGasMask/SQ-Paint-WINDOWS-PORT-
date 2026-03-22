from PyQt6.QtWidgets import QWidget, QLineEdit, QTextEdit
from PyQt6.QtCore import Qt, QPoint, QRect, QPointF
from PyQt6.QtGui import (QPainter, QPen, QImage, QColor, QFont, QTransform,
                         QGuiApplication, QPolygon, QPainterPath, QBrush)
from collections import deque
import numpy as np
import math
import zipfile, json, io

from selection import SelectionManager
from drawing import DrawingTools
from layers import LayerManager
from undo_redo import UndoRedoManager
from file_io import FileIO
from text_tool import TextTool
from canvas_resizer import CanvasResizer

HANDLE_SIZE = 8
ROT_HANDLE_OFFSET = 24  # px above top-center in canvas space
EDGE_HANDLE_SIZE = 10   # size of canvas edge resize handles
EDGE_MARGIN = 20        # extra space outside canvas for handles


class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.layers = [QImage(2048, 1365, QImage.Format.Format_ARGB32_Premultiplied)]
        self.layers[0].fill(Qt.GlobalColor.white)
        layer1 = QImage(2048, 1365, QImage.Format.Format_ARGB32_Premultiplied)
        layer1.fill(Qt.GlobalColor.transparent)
        self.layers.append(layer1)
        self.layer_names = ["Background", "Layer 1"]
        self.layer_visible = [True, True]
        self.active_layer = 1
        self.setFixedSize(2048, 1365); self.zoom_factor = 1.0

        self._composite_cache = None
        self._composite_dirty = True

        self.recent_colors = deque(maxlen=10)
        self.drawing = False; self.modified = False
        self.start_point = self.prev_point = self.last_point = QPoint()
        self.pen_color = QColor("black"); self.pen_width = 3; self.tool = "pencil"
        self.pen_opacity = 255
        self.fill_tolerance = 30     # fill tool tolerance
        self.use_antialiasing = True  # settings-controlled
        self.show_brush_cursor = True # settings-controlled
        self.round_lines = True       # settings-controlled (round vs square caps)
        self.cursor_pos = QPoint()   # for brush cursor overlay
        self.stroke_buffer = None
        self.font_family = "Arial"
        self.font_size = 14
        self.font_bold = False
        self.font_italic = False
        self.status_callback = self.zoom_callback = self.dim_callback =             self.color_picked_callback = self.layers_changed_callback = None

        # Initialize managers
        self.selection_manager = SelectionManager(self)
        self.drawing_tools = DrawingTools(self)
        self.layer_manager = LayerManager(self)
        self.undo_redo_manager = UndoRedoManager(self)
        self.text_tool = TextTool(self)
        self.canvas_resizer = CanvasResizer(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self.text_tool.text_input and event.type() == QEvent.Type.KeyPress:
            key = event.key()
            mods = event.modifiers()
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods & Qt.KeyboardModifier.ControlModifier:
                self.text_tool.finalize_text()
                return True
            if key == Qt.Key.Key_Escape:
                self.text_tool.text_input.clear()
                self.text_tool.text_input.hide()
                self.text_tool.active = False
                self.update()
                return True
        return False

    # ── Composite cache ───────────────────────────────────────────────────────
    def _invalidate_composite(self): self._composite_dirty = True

    def get_composite(self):
        if self._composite_dirty or self._composite_cache is None:
            comp = QImage(self.layers[0].size(), QImage.Format.Format_ARGB32_Premultiplied)
            comp.fill(Qt.GlobalColor.transparent)
            p = QPainter(comp)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            for i, layer in enumerate(self.layers):
                if self.layer_visible[i]:
                    p.drawImage(0, 0, layer)
            p.end()
            self._composite_cache = comp
            self._composite_dirty = False
        return self._composite_cache

    def get_active(self): return self.layers[self.active_layer]

    # ── Selection ─────────────────────────────────────────────────────────────
    def lift_selection(self): self.selection_manager.lift_selection()
    def commit_selection(self): self.selection_manager.commit_selection()
    def select_all(self): self.selection_manager.select_all()
    def cut_selection(self): self.selection_manager.cut_selection()
    def delete_selection(self): self.selection_manager.delete_selection()
    def cancel_selection(self): self.selection_manager.cancel_selection()
    def nudge_selection(self, dx, dy): self.selection_manager.nudge_selection(dx, dy)
    def copy_selection(self): self.selection_manager.copy_selection()
    def paste_from_clipboard(self): self.selection_manager.paste_from_clipboard()

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            screen_pos = event.position().toPoint()
            pos = self.map_to_canvas(event.position())

            # Check edge handles first (in screen coords, before zoom mapping)
            edge = self.canvas_resizer._hit_edge_handle(screen_pos)
            if edge:
                self.canvas_resizer._edge_drag = edge
                self.canvas_resizer._edge_drag_start = screen_pos
                self.canvas_resizer._edge_drag_orig_w = self.layers[0].width()
                self.canvas_resizer._edge_drag_orig_h = self.layers[0].height()
                self.setCursor(Qt.CursorShape.SizeFDiagCursor if edge == "corner"
                               else Qt.CursorShape.SizeHorCursor if edge == "right"
                               else Qt.CursorShape.SizeVerCursor)
                return

            if self.tool == "select":
                if self.selection_manager.selection_state in ["selected", "moving", "resizing", "rotating"]:
                    if self.selection_manager._hit_rot_handle(pos):
                        self.selection_manager.selection_state = "rotating"
                        self.selection_manager.rotate_origin = QPointF(self.selection_manager.selection_rect.center())
                        dx = pos.x() - self.selection_manager.rotate_origin.x()
                        dy = pos.y() - self.selection_manager.rotate_origin.y()
                        self.selection_manager.rotate_start_angle = math.degrees(math.atan2(dy, dx)) \
                            - self.selection_manager.selection_angle
                        return
                    h = self.selection_manager._hit_handle(pos)
                    if h >= 0:
                        self.selection_manager.selection_state = "resizing"
                        self.selection_manager.resize_handle = h
                        self.selection_manager.resize_origin_rect = QRect(self.selection_manager.selection_rect)
                        self.selection_manager.resize_origin_pos = pos
                        return
                    if self.selection_manager.selection_rect.contains(pos):
                        self.selection_manager.selection_state = "moving"
                        self.selection_manager.move_offset = pos - self.selection_manager.selection_rect.topLeft()
                        return
                    self.selection_manager.commit_selection()
                self.selection_manager.selection_state = "selecting"
                self.start_point = pos
                self.selection_manager.selection_rect = QRect(pos, pos)
                return

            if self.tool == "picker":
                comp = self.get_composite()
                if comp.rect().contains(pos):
                    if self.color_picked_callback:
                        self.color_picked_callback(QColor(comp.pixel(pos.x(), pos.y())))
                return

            if self.tool == "text":
                self.text_tool.start_text_input(pos)
                return

            self.undo_redo_manager.save_state()
            if self.tool == "fill":
                self.drawing_tools.flood_fill(pos.x(), pos.y())
                self._invalidate_composite()
            else:
                self.drawing = True
                self.start_point = self.prev_point = self.last_point = pos
                # Use stroke buffer for any tool with opacity < 255
                if self.pen_opacity < 255 and self.tool not in ["eraser"]:
                    self.stroke_buffer = QImage(self.get_active().size(),
                        QImage.Format.Format_ARGB32_Premultiplied)
                    self.stroke_buffer.fill(Qt.GlobalColor.transparent)
                else:
                    self.stroke_buffer = None
            self.update()

    def mouseMoveEvent(self, event):
        pos = self.map_to_canvas(event.position())
        screen_pos = event.position().toPoint()
        held = event.buttons() & Qt.MouseButton.LeftButton

        # Edge drag resize — show ghost preview, commit on release
        if self.canvas_resizer._edge_drag and held:
            dx = int((screen_pos.x() - self.canvas_resizer._edge_drag_start.x()) / self.zoom_factor)
            dy = int((screen_pos.y() - self.canvas_resizer._edge_drag_start.y()) / self.zoom_factor)
            self.canvas_resizer._edge_drag_w = max(10, self.canvas_resizer._edge_drag_orig_w + (dx if self.canvas_resizer._edge_drag in ("right",  "corner") else 0))
            self.canvas_resizer._edge_drag_h = max(10, self.canvas_resizer._edge_drag_orig_h + (dy if self.canvas_resizer._edge_drag in ("bottom", "corner") else 0))
            if self.dim_callback: self.dim_callback(f"{self.canvas_resizer._edge_drag_w} x {self.canvas_resizer._edge_drag_h}px")
            self.update()
            return

        # Update cursor when hovering over edge handles (not dragging)
        if not held:
            edge = self.canvas_resizer._hit_edge_handle(screen_pos)
            if edge == "corner":   self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge == "right":  self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge == "bottom": self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif self.tool not in ["select"]:
                self.setCursor(Qt.CursorShape.CrossCursor)

        if self.tool == "select":
            if self.selection_manager.selection_state == "selecting" and held:
                self.selection_manager.selection_rect = QRect(self.start_point, pos).normalized()
            elif self.selection_manager.selection_state == "moving" and held:
                self.selection_manager.selection_rect.moveTo(pos - self.selection_manager.move_offset)
            elif self.selection_manager.selection_state == "rotating" and held:
                dx = pos.x() - self.selection_manager.rotate_origin.x()
                dy = pos.y() - self.selection_manager.rotate_origin.y()
                raw = math.degrees(math.atan2(dy, dx))
                self.selection_manager.selection_angle = raw - self.selection_manager.rotate_start_angle
                if QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier:
                    self.selection_manager.selection_angle = round(self.selection_manager.selection_angle / 15) * 15
            elif self.selection_manager.selection_state == "resizing" and held:
                self.selection_manager._apply_resize(pos)

            # Cursor feedback
            if self.selection_manager.selection_state in ["selected", "moving", "resizing", "rotating"]:
                if self.selection_manager._hit_rot_handle(pos):
                    self.setCursor(Qt.CursorShape.CrossCursor)
                elif self.selection_manager._hit_handle(pos) >= 0:
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif self.selection_manager.selection_rect.contains(pos):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

        elif held and self.drawing:
            if self.tool in ["pencil", "eraser"]:
                if self.tool in ["pencil"] and self.stroke_buffer is not None:
                    p = QPainter(self.stroke_buffer)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    cap  = Qt.PenCapStyle.RoundCap  if self.round_lines else Qt.PenCapStyle.SquareCap
                    join = Qt.PenJoinStyle.RoundJoin if self.round_lines else Qt.PenJoinStyle.MiterJoin
                    p.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, cap, join))
                    p.drawLine(self.prev_point, pos); p.end()
                else:
                    p = QPainter(self.get_active())
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    if self.tool == "eraser":
                        _cap  = Qt.PenCapStyle.RoundCap  if self.round_lines else Qt.PenCapStyle.SquareCap
                        _join = Qt.PenJoinStyle.RoundJoin if self.round_lines else Qt.PenJoinStyle.MiterJoin
                        if self.active_layer == 0:
                            p.setPen(QPen(Qt.GlobalColor.white, self.pen_width, Qt.PenStyle.SolidLine, _cap, _join))
                        else:
                            p.setCompositionMode(
                                QPainter.CompositionMode.CompositionMode_Clear)
                            p.setPen(QPen(Qt.GlobalColor.transparent, self.pen_width, Qt.PenStyle.SolidLine, _cap, _join))
                    else:
                        _cap  = Qt.PenCapStyle.RoundCap  if self.round_lines else Qt.PenCapStyle.SquareCap
                        _join = Qt.PenJoinStyle.RoundJoin if self.round_lines else Qt.PenJoinStyle.MiterJoin
                        p.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, _cap, _join))
                    p.drawLine(self.prev_point, pos); p.end()
                    self._invalidate_composite()
                self.prev_point = pos
            # For shape tools with opacity, draw live preview into stroke buffer
            if self.tool not in ["pencil", "eraser"] and self.stroke_buffer is not None:
                self.stroke_buffer.fill(Qt.GlobalColor.transparent)
                p = QPainter(self.stroke_buffer)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(self.pen_color, self.pen_width))
                self.drawing_tools._draw_shape(p, self.tool,
                    self.start_point, self.apply_constraints(self.start_point, pos))
                p.end()
            self.last_point = self.apply_constraints(self.start_point, pos)
            self.update()

        self.cursor_pos = pos
        if self.status_callback: self.status_callback(f"{pos.x()}, {pos.y()}px")
        if self.tool in ["pencil", "eraser"]: self.update()  # refresh cursor overlay

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.canvas_resizer._edge_drag:
                new_w, new_h = self.canvas_resizer._edge_drag_w or self.canvas_resizer._edge_drag_orig_w,                                self.canvas_resizer._edge_drag_h or self.canvas_resizer._edge_drag_orig_h
                if new_w != self.canvas_resizer._edge_drag_orig_w or new_h != self.canvas_resizer._edge_drag_orig_h:
                    self.undo_redo_manager.save_state()
                    for i in range(len(self.layers)):
                        new_img = QImage(new_w, new_h, QImage.Format.Format_ARGB32_Premultiplied)
                        new_img.fill(Qt.GlobalColor.white if i == 0 else Qt.GlobalColor.transparent)
                        p = QPainter(new_img)
                        p.drawImage(0, 0, self.layers[i]); p.end()
                        self.layers[i] = new_img
                    self._invalidate_composite()
                    self.set_zoom(self.zoom_factor)
                self.canvas_resizer._edge_drag = None
                self.canvas_resizer._edge_drag_w = 0
                self.canvas_resizer._edge_drag_h = 0
                self.setCursor(Qt.CursorShape.ArrowCursor)
                return
            if self.tool == "select":
                if self.selection_manager.selection_state == "selecting":
                    self.selection_manager.lift_selection()
                elif self.selection_manager.selection_state in ["moving", "rotating"]:
                    self.selection_manager.selection_state = "selected"
                elif self.selection_manager.selection_state == "resizing":
                    if self.selection_manager.selection_buffer:
                        raw = self.selection_manager.selection_rect
                        flip_h = raw.width() < 0
                        flip_v = raw.height() < 0
                        r = raw.normalized()
                        buf = self.selection_manager.selection_buffer.scaled(
                            max(1, r.width()), max(1, r.height()),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        # Mirror buffer if the rect was dragged past zero
                        if flip_h or flip_v:
                            buf = buf.mirrored(flip_h, flip_v)
                        self.selection_manager.selection_buffer = buf
                        self.selection_manager.selection_rect = r
                    self.selection_manager.selection_state = "selected"
            elif self.drawing:
                if self.stroke_buffer is not None:
                    p = QPainter(self.get_active())
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    p.setOpacity(self.pen_opacity / 255.0)
                    p.drawImage(0, 0, self.stroke_buffer); p.end()
                    self.stroke_buffer = None
                    self._invalidate_composite()
                elif self.start_point != self.last_point:
                    p = QPainter(self.get_active())
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    if self.pen_opacity < 255:
                        p.setOpacity(self.pen_opacity / 255.0)
                    _cap  = Qt.PenCapStyle.RoundCap  if self.round_lines else Qt.PenCapStyle.SquareCap
                    _join = Qt.PenJoinStyle.RoundJoin if self.round_lines else Qt.PenJoinStyle.MiterJoin
                    p.setPen(QPen(self.pen_color, self.pen_width, Qt.PenStyle.SolidLine, _cap, _join))
                    self.drawing_tools._draw_shape(p, self.tool, self.start_point, self.last_point)
                    p.end()
                    self._invalidate_composite()
                self.drawing = False
                self.update()

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        if self.use_antialiasing:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.scale(self.zoom_factor, self.zoom_factor)
        p.drawImage(0, 0, self.get_composite())

        # Opacity stroke preview
        if self.drawing and self.stroke_buffer is not None:
            p.setOpacity(self.pen_opacity / 255.0)
            p.drawImage(0, 0, self.stroke_buffer)
            p.setOpacity(1.0)

        # Floating selection buffer (with rotation + live resize scaling)
        if self.selection_manager.selection_state in ["selected", "moving", "resizing", "rotating"] \
                and self.selection_manager.selection_buffer:
            p.save()
            if self.selection_manager.selection_angle != 0.0:
                cx = self.selection_manager.selection_rect.center().x()
                cy = self.selection_manager.selection_rect.center().y()
                p.translate(cx, cy)
                p.rotate(self.selection_manager.selection_angle)
                p.translate(-self.selection_manager.selection_buffer.width() / 2,
                             -self.selection_manager.selection_buffer.height() / 2)
                p.drawImage(0, 0, self.selection_manager.selection_buffer)
            elif self.selection_manager.selection_state == "resizing":
                # Live scale preview during drag — no commit needed
                r = self.selection_manager.selection_rect.normalized()
                if r.width() > 0 and r.height() > 0:
                    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    p.drawImage(r, self.selection_manager.selection_buffer)
            else:
                p.drawImage(self.selection_manager.selection_rect.topLeft(), self.selection_manager.selection_buffer)
            p.restore()

        # Selection border + handles
        if self.selection_manager.selection_state != "idle" and not self.selection_manager.selection_rect.isNull():
            p.save()
            if self.selection_manager.selection_angle != 0.0:
                cx = self.selection_manager.selection_rect.center().x()
                cy = self.selection_manager.selection_rect.center().y()
                p.translate(cx, cy); p.rotate(self.selection_manager.selection_angle)
                p.translate(-self.selection_manager.selection_rect.width() / 2,
                             -self.selection_manager.selection_rect.height() / 2)
                p.setPen(QPen(QColor(0, 120, 212), 1, Qt.PenStyle.DashLine))
                p.drawRect(0, 0, self.selection_manager.selection_rect.width(), self.selection_manager.selection_rect.height())
            else:
                p.setPen(QPen(QColor(0, 120, 212), 1, Qt.PenStyle.DashLine))
                p.drawRect(self.selection_manager.selection_rect)
            p.restore()

            # Resize handles
            p.setPen(QPen(QColor(0, 120, 212), 1))
            p.setBrush(QBrush(Qt.GlobalColor.white))
            for hr in self.selection_manager._handle_rects():
                p.drawRect(hr)

            # Rotation handle (green circle)
            rp = self.selection_manager._rot_handle_pos()
            tc = QPoint(self.selection_manager.selection_rect.center().x(), self.selection_manager.selection_rect.top())
            p.setPen(QPen(QColor(0, 200, 100), 1))
            p.drawLine(tc, rp)
            p.setBrush(QBrush(Qt.GlobalColor.white))
            rot_r = self.selection_manager._handle_size_canvas() // 2
            p.drawEllipse(rp, rot_r, rot_r)

        # Shape preview while drawing
        if self.drawing and self.tool not in                 ["pencil", "eraser", "fill", "picker", "text", "select"]:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(self.pen_color, self.pen_width))
            self.drawing_tools._draw_shape(p, self.tool, self.start_point, self.last_point)

        # Canvas edge resize handles + ghost preview
        p.save()
        p.resetTransform()
        if self.canvas_resizer._edge_drag and self.canvas_resizer._edge_drag_w and self.canvas_resizer._edge_drag_h:
            # Ghost preview of new canvas size
            ghost_w = int(self.canvas_resizer._edge_drag_w * self.zoom_factor)
            ghost_h = int(self.canvas_resizer._edge_drag_h * self.zoom_factor)
            p.setPen(QPen(QColor(0, 120, 212), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(0, 0, ghost_w, ghost_h)
            # Draw handles at new position
            hs = EDGE_HANDLE_SIZE
            for hr in [
                QRect(ghost_w - hs//2, ghost_h//2 - hs//2, hs, hs),
                QRect(ghost_w//2 - hs//2, ghost_h - hs//2, hs, hs),
                QRect(ghost_w - hs//2, ghost_h - hs//2, hs, hs),
            ]:
                p.setPen(QPen(QColor(0, 120, 212), 1))
                p.setBrush(QBrush(Qt.GlobalColor.white))
                p.drawRect(hr)
        else:
            cw, ch = self.canvas_resizer._canvas_pixel_size()
            for hr in self.canvas_resizer._edge_handle_rects():
                p.setPen(QPen(QColor(0, 120, 212), 1))
                p.setBrush(QBrush(Qt.GlobalColor.white))
                p.drawRect(hr)
        p.restore()

        # Brush cursor overlay for pencil/eraser
        if self.show_brush_cursor and self.tool in ["pencil", "eraser"] and not self.cursor_pos.isNull():
            p.save()
            radius = max(1, int(self.pen_width / 2))
            cp = QPointF(self.cursor_pos)
            p.setPen(QPen(QColor(255, 255, 255, 180), 1, Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(cp, float(radius), float(radius))
            p.setPen(QPen(QColor(0, 0, 0, 180), 1, Qt.PenStyle.DotLine))
            p.drawEllipse(cp, float(radius), float(radius))
            p.restore()

        # Live text preview — drawn last so it sits on top of everything
        if self.text_tool.active:
            self.text_tool.paint_preview(p)

    # ── Text ──────────────────────────────────────────────────────────────────
    def finalize_text(self): self.text_tool.finalize_text()

    # ── Undo / Redo ───────────────────────────────────────────────────────────
    def save_state(self): self.undo_redo_manager.save_state()
    def undo(self): self.undo_redo_manager.undo()
    def redo(self): self.undo_redo_manager.redo()

    # ── Layer ops ─────────────────────────────────────────────────────────────
    def add_new_layer(self): self.layer_manager.add_new_layer()
    def delete_layer(self, index): self.layer_manager.delete_layer(index)
    def duplicate_layer(self, index): self.layer_manager.duplicate_layer(index)
    def move_layer(self, from_idx, to_idx): self.layer_manager.move_layer(from_idx, to_idx)
    def rename_layer(self, index, name): self.layer_manager.rename_layer(index, name)
    def merge_down(self, index): self.layer_manager.merge_down(index)
    def merge_up(self, index): self.layer_manager.merge_up(index)

    # ── Canvas transforms ─────────────────────────────────────────────────────
    # ── .sqish format ────────────────────────────────────────────────────────
    def save_sqish(self, path): return FileIO.save_sqish(self, path)
    def load_sqish(self, path): return FileIO.load_sqish(self, path)

    def set_zoom(self, factor):
        self.zoom_factor = max(0.2, min(5.0, factor))
        curr = self.layers[0]
        # Add EDGE_MARGIN so edge handles are visible outside the image boundary
        self.setFixedSize(int(curr.width() * self.zoom_factor) + EDGE_MARGIN,
                          int(curr.height() * self.zoom_factor) + EDGE_MARGIN)
        if self.zoom_callback: self.zoom_callback(f"{int(self.zoom_factor * 100)}%")
        if self.dim_callback: self.dim_callback(f"{curr.width()} x {curr.height()}px")
        self.update()

    def transform_image(self, mode):
        self.commit_selection(); self.save_state()
        for i in range(len(self.layers)):
            t = QTransform()
            if mode == "flip_h": self.layers[i] = self.layers[i].mirrored(True, False)
            elif mode == "flip_v": self.layers[i] = self.layers[i].mirrored(False, True)
            elif mode == "rot_90": self.layers[i] = self.layers[i].transformed(t.rotate(90))
            elif mode == "rot_180": self.layers[i] = self.layers[i].transformed(t.rotate(180))
        self._invalidate_composite(); self.set_zoom(self.zoom_factor)

    def resize_canvas(self, new_w, new_h, anchor_x, anchor_y): self.canvas_resizer.resize_canvas(new_w, new_h, anchor_x, anchor_y)

    # ── Canvas edge resize handles ────────────────────────────────────────────
    def _canvas_pixel_size(self): return self.canvas_resizer._canvas_pixel_size()
    def _edge_handle_rects(self): return self.canvas_resizer._edge_handle_rects()
    def _hit_edge_handle(self, pos): return self.canvas_resizer._hit_edge_handle(pos)

    # ── Utilities ─────────────────────────────────────────────────────────────
    def map_to_canvas(self, screen_pos: QPointF) -> QPoint:
        return (screen_pos / self.zoom_factor).toPoint()

    def apply_constraints(self, start, end):
        if QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier:
            dx, dy = end.x() - start.x(), end.y() - start.y()
            if self.tool in ["rect", "ellipse", "rounded_rect", "diamond"]:
                d = max(abs(dx), abs(dy))
                return QPoint(start.x() + (d if dx > 0 else -d),
                               start.y() + (d if dy > 0 else -d))
            elif self.tool == "line":
                if abs(dx) > abs(dy) * 2: dy = 0
                elif abs(dy) > abs(dx) * 2: dx = 0
                else:
                    d = (abs(dx) + abs(dy)) // 2
                    dx, dy = (d if dx > 0 else -d), (d if dy > 0 else -d)
                return QPoint(start.x() + dx, start.y() + dy)
        return end

    def wheelEvent(self, event):
        if QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.ControlModifier:
            delta = 0.1 if event.angleDelta().y() > 0 else -0.1
            self.set_zoom(self.zoom_factor + delta); event.accept()
        else: super().wheelEvent(event)
