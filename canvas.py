from PyQt6.QtWidgets import QWidget, QLineEdit
from PyQt6.QtCore import Qt, QPoint, QRect, QPointF
from PyQt6.QtGui import (QPainter, QPen, QImage, QColor, QFont, QTransform,
                         QGuiApplication, QPolygon, QPainterPath, QBrush)
from collections import deque
import numpy as np
import math

HANDLE_SIZE = 8
ROT_HANDLE_OFFSET = 24  # px above top-center in canvas space


class Canvas(QWidget):
    def __init__(self):
        super().__init__()
        self.layers = [QImage(900, 600, QImage.Format.Format_ARGB32_Premultiplied)]
        self.layers[0].fill(Qt.GlobalColor.white)
        self.layer_names = ["Background"]; self.layer_visible = [True]; self.active_layer = 0
        self.setFixedSize(900, 600); self.zoom_factor = 1.0

        self._composite_cache = None
        self._composite_dirty = True

        self.text_input = QLineEdit(self); self.text_input.setFrame(False); self.text_input.hide()
        self.text_input.returnPressed.connect(self.finalize_text)

        # Selection
        self.selection_rect = QRect()
        self.selection_buffer = None
        self.selection_state = "idle"   # idle|selecting|selected|moving|resizing|rotating
        self.move_offset = QPoint()
        self.resize_handle = -1
        self.resize_origin_rect = QRect()
        self.resize_origin_pos = QPoint()
        self.selection_angle = 0.0
        self.rotate_origin = QPointF()
        self.rotate_start_angle = 0.0

        self.recent_colors = deque(maxlen=10)
        self.undo_history, self.redo_history = [], []
        self.drawing = False; self.modified = False
        self.start_point = self.prev_point = self.last_point = QPoint()
        self.pen_color = QColor("black"); self.pen_width = 3; self.tool = "pencil"
        self.pen_opacity = 255
        self.stroke_buffer = None
        self.text_pos = QPoint()
        self.font_family = "Arial"
        self.font_size = 14
        self.font_bold = False
        self.font_italic = False
        self.status_callback = self.zoom_callback = self.dim_callback = \
            self.color_picked_callback = self.layers_changed_callback = None

    # ── Composite cache ───────────────────────────────────────────────────────
    def _invalidate_composite(self): self._composite_dirty = True

    def get_composite(self):
        if self._composite_dirty or self._composite_cache is None:
            comp = QImage(self.layers[0].size(), QImage.Format.Format_ARGB32_Premultiplied)
            comp.fill(Qt.GlobalColor.transparent)
            p = QPainter(comp)
            for i, layer in enumerate(self.layers):
                if self.layer_visible[i]: p.drawImage(0, 0, layer)
            p.end()
            self._composite_cache = comp
            self._composite_dirty = False
        return self._composite_cache

    def get_active(self): return self.layers[self.active_layer]

    # ── Handle helpers ────────────────────────────────────────────────────────
    def _handle_rects(self):
        r = self.selection_rect.normalized()
        cx, cy = r.center().x(), r.center().y()
        pts = [
            QPoint(r.left(),  r.top()),
            QPoint(cx,        r.top()),
            QPoint(r.right(), r.top()),
            QPoint(r.left(),  cy),
            QPoint(r.right(), cy),
            QPoint(r.left(),  r.bottom()),
            QPoint(cx,        r.bottom()),
            QPoint(r.right(), r.bottom()),
        ]
        hs = HANDLE_SIZE // 2
        return [QRect(pt.x()-hs, pt.y()-hs, HANDLE_SIZE, HANDLE_SIZE) for pt in pts]

    def _rot_handle_pos(self):
        r = self.selection_rect.normalized()
        return QPoint(r.center().x(), r.top() - ROT_HANDLE_OFFSET)

    def _hit_handle(self, pos):
        for i, hr in enumerate(self._handle_rects()):
            if hr.contains(pos): return i
        return -1

    def _hit_rot_handle(self, pos):
        rp = self._rot_handle_pos()
        return (pos - rp).manhattanLength() <= HANDLE_SIZE + 2

    # ── Selection ─────────────────────────────────────────────────────────────
    def lift_selection(self):
        active = self.get_active()
        r = self.selection_rect.normalized().intersected(active.rect())
        if r.width() < 2 or r.height() < 2:
            self.selection_state = "idle"; self.selection_rect = QRect(); return
        self.save_state()
        self.selection_buffer = active.copy(r)
        p = QPainter(active)
        if self.active_layer == 0:
            p.fillRect(r, Qt.GlobalColor.white)
        else:
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            p.fillRect(r, Qt.GlobalColor.transparent)
        p.end()
        self._invalidate_composite()
        self.selection_rect = r
        self.selection_angle = 0.0
        self.selection_state = "selected"
        self.update()

    def commit_selection(self):
        if self.selection_state in ["selected", "moving", "resizing", "rotating"] \
                and self.selection_buffer:
            p = QPainter(self.get_active())
            if self.selection_angle != 0.0:
                rotated = self._rotated_buffer()
                cx = self.selection_rect.center().x() - rotated.width() // 2
                cy = self.selection_rect.center().y() - rotated.height() // 2
                p.drawImage(cx, cy, rotated)
            else:
                p.drawImage(self.selection_rect.topLeft(), self.selection_buffer)
            p.end()
            self._invalidate_composite()
            self.modified = True
        self.selection_buffer = None
        self.selection_rect = QRect()
        self.selection_state = "idle"
        self.selection_angle = 0.0
        self.update()

    def _rotated_buffer(self):
        if self.selection_buffer is None: return None
        t = QTransform().rotate(self.selection_angle)
        return self.selection_buffer.transformed(t, Qt.TransformationMode.SmoothTransformation)

    # ── Mouse events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.map_to_canvas(event.position())

            if self.tool == "select":
                if self.selection_state in ["selected", "moving", "resizing", "rotating"]:
                    if self._hit_rot_handle(pos):
                        self.selection_state = "rotating"
                        self.rotate_origin = QPointF(self.selection_rect.center())
                        dx = pos.x() - self.rotate_origin.x()
                        dy = pos.y() - self.rotate_origin.y()
                        self.rotate_start_angle = math.degrees(math.atan2(dy, dx)) \
                            - self.selection_angle
                        return
                    h = self._hit_handle(pos)
                    if h >= 0:
                        self.selection_state = "resizing"
                        self.resize_handle = h
                        self.resize_origin_rect = QRect(self.selection_rect)
                        self.resize_origin_pos = pos
                        return
                    if self.selection_rect.contains(pos):
                        self.selection_state = "moving"
                        self.move_offset = pos - self.selection_rect.topLeft()
                        return
                    self.commit_selection()
                self.selection_state = "selecting"
                self.start_point = pos
                self.selection_rect = QRect(pos, pos)
                return

            if self.tool == "picker":
                comp = self.get_composite()
                if comp.rect().contains(pos):
                    if self.color_picked_callback:
                        self.color_picked_callback(QColor(comp.pixel(pos.x(), pos.y())))
                return

            if self.tool == "text":
                if self.text_input.isVisible():
                    self.finalize_text()
                else:
                    self.text_pos = pos
                    scaled_f = int(self.font_size * self.zoom_factor)
                    bold_str = "bold" if self.font_bold else "normal"
                    italic_str = "italic" if self.font_italic else "normal"
                    self.text_input.setStyleSheet(
                        f"background:transparent; border:1px dashed #ccc; "
                        f"color:{self.pen_color.name()}; font-size:{scaled_f}pt; "
                        f"font-family:{self.font_family}; font-weight:{bold_str}; "
                        f"font-style:{italic_str};")
                    sp = event.position().toPoint()
                    self.text_input.setGeometry(sp.x(), sp.y(),
                        int(500 * self.zoom_factor), scaled_f + 20)
                    self.text_input.show(); self.text_input.setFocus()
                return

            self.save_state()
            if self.tool == "fill":
                self.flood_fill(pos.x(), pos.y())
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
        held = event.buttons() & Qt.MouseButton.LeftButton

        if self.tool == "select":
            if self.selection_state == "selecting" and held:
                self.selection_rect = QRect(self.start_point, pos).normalized()
            elif self.selection_state == "moving" and held:
                self.selection_rect.moveTo(pos - self.move_offset)
            elif self.selection_state == "rotating" and held:
                dx = pos.x() - self.rotate_origin.x()
                dy = pos.y() - self.rotate_origin.y()
                raw = math.degrees(math.atan2(dy, dx))
                self.selection_angle = raw - self.rotate_start_angle
                if QGuiApplication.keyboardModifiers() == Qt.KeyboardModifier.ShiftModifier:
                    self.selection_angle = round(self.selection_angle / 15) * 15
            elif self.selection_state == "resizing" and held:
                self._apply_resize(pos)

            # Cursor feedback
            if self.selection_state in ["selected", "moving", "resizing", "rotating"]:
                if self._hit_rot_handle(pos):
                    self.setCursor(Qt.CursorShape.CrossCursor)
                elif self._hit_handle(pos) >= 0:
                    self.setCursor(Qt.CursorShape.SizeBDiagCursor)
                elif self.selection_rect.contains(pos):
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

        elif held and self.drawing:
            if self.tool in ["pencil", "eraser"]:
                if self.tool in ["pencil"] and self.stroke_buffer is not None:
                    p = QPainter(self.stroke_buffer)
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    p.setPen(QPen(self.pen_color, self.pen_width,
                        Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                        Qt.PenJoinStyle.RoundJoin))
                    p.drawLine(self.prev_point, pos); p.end()
                else:
                    p = QPainter(self.get_active())
                    p.setRenderHint(QPainter.RenderHint.Antialiasing)
                    if self.tool == "eraser":
                        if self.active_layer == 0:
                            p.setPen(QPen(Qt.GlobalColor.white, self.pen_width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
                        else:
                            p.setCompositionMode(
                                QPainter.CompositionMode.CompositionMode_Clear)
                            p.setPen(QPen(Qt.GlobalColor.transparent, self.pen_width,
                                Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
                    else:
                        p.setPen(QPen(self.pen_color, self.pen_width,
                            Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                            Qt.PenJoinStyle.RoundJoin))
                    p.drawLine(self.prev_point, pos); p.end()
                    self._invalidate_composite()
                self.prev_point = pos
            # For shape tools with opacity, draw live preview into stroke buffer
            if self.tool not in ["pencil", "eraser"] and self.stroke_buffer is not None:
                self.stroke_buffer.fill(Qt.GlobalColor.transparent)
                p = QPainter(self.stroke_buffer)
                p.setRenderHint(QPainter.RenderHint.Antialiasing)
                p.setPen(QPen(self.pen_color, self.pen_width))
                self._draw_shape(p, self.tool,
                    self.start_point, self.apply_constraints(self.start_point, pos))
                p.end()
            self.last_point = self.apply_constraints(self.start_point, pos)
            self.update()

        if self.status_callback: self.status_callback(f"{pos.x()}, {pos.y()}px")

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.tool == "select":
                if self.selection_state == "selecting":
                    self.lift_selection()
                elif self.selection_state in ["moving", "rotating"]:
                    self.selection_state = "selected"
                elif self.selection_state == "resizing":
                    if self.selection_buffer:
                        raw = self.selection_rect
                        flip_h = raw.width() < 0
                        flip_v = raw.height() < 0
                        r = raw.normalized()
                        buf = self.selection_buffer.scaled(
                            max(1, r.width()), max(1, r.height()),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
                        # Mirror buffer if the rect was dragged past zero
                        if flip_h or flip_v:
                            buf = buf.mirrored(flip_h, flip_v)
                        self.selection_buffer = buf
                        self.selection_rect = r
                    self.selection_state = "selected"
            elif self.drawing:
                if self.stroke_buffer is not None:
                    p = QPainter(self.get_active())
                    p.setOpacity(self.pen_opacity / 255.0)
                    p.drawImage(0, 0, self.stroke_buffer); p.end()
                    self.stroke_buffer = None
                    self._invalidate_composite()
                elif self.start_point != self.last_point:
                    if self.stroke_buffer is not None:
                        # Shape was drawn into stroke buffer for opacity
                        p = QPainter(self.get_active())
                        p.setOpacity(self.pen_opacity / 255.0)
                        p.drawImage(0, 0, self.stroke_buffer); p.end()
                        self.stroke_buffer = None
                    else:
                        p = QPainter(self.get_active())
                        p.setRenderHint(QPainter.RenderHint.Antialiasing)
                        p.setPen(QPen(self.pen_color, self.pen_width))
                        self._draw_shape(p, self.tool, self.start_point, self.last_point)
                        p.end()
                    self._invalidate_composite()
                self.drawing = False
                self.update()

    def _apply_resize(self, pos):
        # Work from the raw (non-normalized) rect so dragging past zero
        # causes the handles to cross, which naturally flips the buffer on commit.
        r = QRect(self.selection_rect)
        h = self.resize_handle
        dx = pos.x() - self.resize_origin_pos.x()
        dy = pos.y() - self.resize_origin_pos.y()
        if abs(dx) < 1 and abs(dy) < 1: return
        if h in (0, 3, 5): r.setLeft(r.left() + dx)
        if h in (2, 4, 7): r.setRight(r.right() + dx)
        if h in (0, 1, 2): r.setTop(r.top() + dy)
        if h in (5, 6, 7): r.setBottom(r.bottom() + dy)
        self.selection_rect = r
        self.resize_origin_pos = pos

    # ── Shape drawing ─────────────────────────────────────────────────────────
    def _draw_shape(self, painter, tool, start, end):
        r = QRect(start, end).normalized()
        if tool == "rect":         painter.drawRect(r)
        elif tool == "ellipse":    painter.drawEllipse(r)
        elif tool == "line":       painter.drawLine(start, end)
        elif tool == "rounded_rect": painter.drawRoundedRect(r, 12, 12)
        elif tool == "triangle":   self._draw_ngon(painter, r, 3, offset=-90)
        elif tool == "diamond":    self._draw_ngon(painter, r, 4, offset=0)
        elif tool == "pentagon":   self._draw_ngon(painter, r, 5, offset=-90)
        elif tool == "hexagon":    self._draw_ngon(painter, r, 6, offset=0)
        elif tool == "star":       self._draw_star(painter, r)
        elif tool == "arrow":      self._draw_arrow(painter, r)

    def _draw_ngon(self, painter, r, sides, offset=0):
        cx, cy = r.center().x(), r.center().y()
        rx, ry = r.width() / 2, r.height() / 2
        pts = []
        for i in range(sides):
            a = math.radians(i * 360 / sides + offset)
            pts.append(QPoint(int(cx + rx * math.cos(a)), int(cy + ry * math.sin(a))))
        painter.drawPolygon(QPolygon(pts))

    def _draw_star(self, painter, r):
        cx, cy = r.center().x(), r.center().y()
        orx, ory = r.width() / 2, r.height() / 2
        irx, iry = orx * 0.4, ory * 0.4
        pts = []
        for i in range(10):
            a = math.radians(i * 36 - 90)
            rx = orx if i % 2 == 0 else irx
            ry = ory if i % 2 == 0 else iry
            pts.append(QPoint(int(cx + rx * math.cos(a)), int(cy + ry * math.sin(a))))
        painter.drawPolygon(QPolygon(pts))

    def _draw_arrow(self, painter, r):
        path = QPainterPath()
        w, h = r.width(), r.height()
        shaft_top = r.top() + h * 0.3
        shaft_bot = r.top() + h * 0.7
        head_x = r.left() + w * 0.6
        path.moveTo(r.left(), shaft_top)
        path.lineTo(head_x, shaft_top)
        path.lineTo(head_x, r.top())
        path.lineTo(r.right(), r.top() + h / 2)
        path.lineTo(head_x, r.bottom())
        path.lineTo(head_x, shaft_bot)
        path.lineTo(r.left(), shaft_bot)
        path.closeSubpath()
        painter.drawPath(path)

    # ── Paint ─────────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        p = QPainter(self)
        p.scale(self.zoom_factor, self.zoom_factor)
        p.drawImage(0, 0, self.get_composite())

        # Opacity stroke preview
        if self.drawing and self.stroke_buffer is not None:
            p.setOpacity(self.pen_opacity / 255.0)
            p.drawImage(0, 0, self.stroke_buffer)
            p.setOpacity(1.0)

        # Floating selection buffer (with rotation)
        if self.selection_state in ["selected", "moving", "resizing", "rotating"] \
                and self.selection_buffer:
            p.save()
            if self.selection_angle != 0.0:
                cx = self.selection_rect.center().x()
                cy = self.selection_rect.center().y()
                p.translate(cx, cy)
                p.rotate(self.selection_angle)
                p.translate(-self.selection_buffer.width() / 2,
                             -self.selection_buffer.height() / 2)
                p.drawImage(0, 0, self.selection_buffer)
            else:
                p.drawImage(self.selection_rect.topLeft(), self.selection_buffer)
            p.restore()

        # Selection border + handles
        if self.selection_state != "idle" and not self.selection_rect.isNull():
            p.save()
            if self.selection_angle != 0.0:
                cx = self.selection_rect.center().x()
                cy = self.selection_rect.center().y()
                p.translate(cx, cy); p.rotate(self.selection_angle)
                p.translate(-self.selection_rect.width() / 2,
                             -self.selection_rect.height() / 2)
                p.setPen(QPen(QColor(0, 120, 212), 1, Qt.PenStyle.DashLine))
                p.drawRect(0, 0, self.selection_rect.width(), self.selection_rect.height())
            else:
                p.setPen(QPen(QColor(0, 120, 212), 1, Qt.PenStyle.DashLine))
                p.drawRect(self.selection_rect)
            p.restore()

            # Resize handles
            p.setPen(QPen(QColor(0, 120, 212), 1))
            p.setBrush(QBrush(Qt.GlobalColor.white))
            for hr in self._handle_rects():
                p.drawRect(hr)

            # Rotation handle (green circle)
            rp = self._rot_handle_pos()
            tc = QPoint(self.selection_rect.center().x(), self.selection_rect.top())
            p.setPen(QPen(QColor(0, 200, 100), 1))
            p.drawLine(tc, rp)
            p.setBrush(QBrush(Qt.GlobalColor.white))
            p.drawEllipse(rp, HANDLE_SIZE // 2, HANDLE_SIZE // 2)

        # Shape preview while drawing
        if self.drawing and self.tool not in \
                ["pencil", "eraser", "fill", "picker", "text", "select"]:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QPen(self.pen_color, self.pen_width))
            self._draw_shape(p, self.tool, self.start_point, self.last_point)

    # ── Text ──────────────────────────────────────────────────────────────────
    def finalize_text(self):
        if not self.text_input.isVisible(): return
        content = self.text_input.text().strip()
        if content:
            self.save_state()
            p = QPainter(self.get_active())
            color = QColor(self.pen_color)
            color.setAlpha(self.pen_opacity)
            p.setPen(color)
            font = QFont(self.font_family, self.font_size)
            font.setBold(self.font_bold); font.setItalic(self.font_italic)
            p.setFont(font)
            p.drawText(self.text_pos.x() + 2, self.text_pos.y() + self.font_size, content)
            p.end(); self._invalidate_composite()
        self.text_input.clear(); self.text_input.hide(); self.update()

    # ── Flood fill ────────────────────────────────────────────────────────────
    def flood_fill(self, x, y, tolerance=30):
        """Tolerance-based scanline flood fill.
        Pixels within  color distance of the target are filled,
        which closes the anti-aliased gaps left along drawn edges.
        """
        active = self.get_active()
        if not active.rect().contains(x, y): return
        w, h = active.width(), active.height()
        ptr = active.bits(); ptr.setsize(h * w * 4)
        arr = np.frombuffer(ptr, dtype=np.uint32).reshape((h, w)).copy()

        target = arr[y, x]
        fc = self.pen_color
        fill = np.uint32((fc.alpha() << 24) | (fc.red() << 16) |
                         (fc.green() << 8) | fc.blue())
        if target == fill: return

        # Decompose target into ARGB channels as int16 to avoid overflow in diff
        ta = np.int16((target >> 24) & 0xFF)
        tr = np.int16((target >> 16) & 0xFF)
        tg = np.int16((target >>  8) & 0xFF)
        tb = np.int16( target        & 0xFF)

        def in_tolerance(pixel):
            a = np.int16((pixel >> 24) & 0xFF)
            r = np.int16((pixel >> 16) & 0xFF)
            g = np.int16((pixel >>  8) & 0xFF)
            b = np.int16( pixel        & 0xFF)
            return (abs(r-tr) + abs(g-tg) + abs(b-tb) + abs(a-ta)) <= tolerance * 4

        mask = np.zeros((h, w), dtype=bool)
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= w or cy < 0 or cy >= h: continue
            if mask[cy, cx] or not in_tolerance(arr[cy, cx]): continue
            xl = cx
            while xl > 0 and not mask[cy, xl-1] and in_tolerance(arr[cy, xl-1]): xl -= 1
            xr = cx
            while xr < w-1 and not mask[cy, xr+1] and in_tolerance(arr[cy, xr+1]): xr += 1
            mask[cy, xl:xr+1] = True
            for nx in range(xl, xr+1):
                if cy > 0 and not mask[cy-1, nx] and in_tolerance(arr[cy-1, nx]):
                    stack.append((nx, cy-1))
                if cy < h-1 and not mask[cy+1, nx] and in_tolerance(arr[cy+1, nx]):
                    stack.append((nx, cy+1))
        arr[mask] = fill
        result = QImage(arr.tobytes(), w, h, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(active)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(0, 0, result); p.end()

    # ── Undo / Redo ───────────────────────────────────────────────────────────
    def save_state(self):
        if len(self.undo_history) > 30: self.undo_history.pop(0)
        self.undo_history.append({
            'layers': [img.copy() for img in self.layers],
            'names': list(self.layer_names),
            'visible': list(self.layer_visible),
            'active': self.active_layer
        })
        self.redo_history.clear(); self.modified = True

    def undo(self):
        self.commit_selection()
        if self.undo_history:
            self.redo_history.append({'layers': [img.copy() for img in self.layers],
                'names': list(self.layer_names), 'visible': list(self.layer_visible),
                'active': self.active_layer})
            state = self.undo_history.pop()
            self.layers, self.layer_names, self.layer_visible, self.active_layer = \
                state['layers'], state['names'], state['visible'], state['active']
            self._invalidate_composite()
            if self.layers_changed_callback: self.layers_changed_callback()
            self.set_zoom(self.zoom_factor)

    def redo(self):
        self.commit_selection()
        if self.redo_history:
            self.undo_history.append({'layers': [img.copy() for img in self.layers],
                'names': list(self.layer_names), 'visible': list(self.layer_visible),
                'active': self.active_layer})
            state = self.redo_history.pop()
            self.layers, self.layer_names, self.layer_visible, self.active_layer = \
                state['layers'], state['names'], state['visible'], state['active']
            self._invalidate_composite()
            if self.layers_changed_callback: self.layers_changed_callback()
            self.set_zoom(self.zoom_factor)

    # ── Layer ops ─────────────────────────────────────────────────────────────
    def add_new_layer(self):
        self.save_state()
        new_img = QImage(self.layers[0].size(), QImage.Format.Format_ARGB32_Premultiplied)
        new_img.fill(Qt.GlobalColor.transparent)
        self.layers.append(new_img)
        self.layer_names.append(f"Layer {len(self.layers)}")
        self.layer_visible.append(True); self.active_layer = len(self.layers) - 1
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    def delete_layer(self, index):
        if len(self.layers) <= 1: return
        self.save_state()
        self.layers.pop(index); self.layer_names.pop(index); self.layer_visible.pop(index)
        self.active_layer = min(self.active_layer, len(self.layers) - 1)
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    def duplicate_layer(self, index):
        self.save_state()
        self.layers.insert(index + 1, self.layers[index].copy())
        self.layer_names.insert(index + 1, self.layer_names[index] + " Copy")
        self.layer_visible.insert(index + 1, self.layer_visible[index])
        self.active_layer = index + 1
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    def move_layer(self, from_idx, to_idx):
        """Move layer from from_idx to to_idx, shifting others accordingly."""
        if from_idx == to_idx: return
        if not (0 <= from_idx < len(self.layers)): return
        if not (0 <= to_idx < len(self.layers)): return
        self.save_state()
        for lst in [self.layers, self.layer_names, self.layer_visible]:
            item = lst.pop(from_idx)
            lst.insert(to_idx, item)
        self.active_layer = to_idx
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    def rename_layer(self, index, name):
        if not name.strip(): return
        self.layer_names[index] = name.strip()
        if self.layers_changed_callback: self.layers_changed_callback()

    def merge_down(self, index):
        if index <= 0: return
        self.save_state()
        below = index - 1
        merged = QImage(self.layers[below].size(), QImage.Format.Format_ARGB32_Premultiplied)
        merged.fill(Qt.GlobalColor.transparent)
        p = QPainter(merged)
        p.drawImage(0, 0, self.layers[below]); p.drawImage(0, 0, self.layers[index])
        p.end()
        self.layers[below] = merged
        self.layers.pop(index); self.layer_names.pop(index); self.layer_visible.pop(index)
        self.active_layer = below
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    def merge_up(self, index):
        if index >= len(self.layers) - 1: return
        self.save_state()
        above = index + 1
        merged = QImage(self.layers[above].size(), QImage.Format.Format_ARGB32_Premultiplied)
        merged.fill(Qt.GlobalColor.transparent)
        p = QPainter(merged)
        p.drawImage(0, 0, self.layers[index]); p.drawImage(0, 0, self.layers[above])
        p.end()
        self.layers[above] = merged
        self.layers.pop(index); self.layer_names.pop(index); self.layer_visible.pop(index)
        self.active_layer = above - 1
        self._invalidate_composite()
        if self.layers_changed_callback: self.layers_changed_callback()
        self.update()

    # ── Canvas transforms ─────────────────────────────────────────────────────
    def set_zoom(self, factor):
        self.zoom_factor = max(0.2, min(5.0, factor))
        curr = self.layers[0]
        self.setFixedSize(int(curr.width() * self.zoom_factor),
                          int(curr.height() * self.zoom_factor))
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

    def resize_canvas(self, new_w, new_h, anchor_x, anchor_y):
        self.commit_selection(); self.save_state()
        for i in range(len(self.layers)):
            new_img = QImage(new_w, new_h, QImage.Format.Format_ARGB32_Premultiplied)
            new_img.fill(Qt.GlobalColor.white if i == 0 else Qt.GlobalColor.transparent)
            p = QPainter(new_img)
            x = int((new_w - self.layers[i].width()) * anchor_x)
            y = int((new_h - self.layers[i].height()) * anchor_y)
            p.drawImage(x, y, self.layers[i]); p.end()
            self.layers[i] = new_img
        self._invalidate_composite(); self.set_zoom(self.zoom_factor)

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
