from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtGui import QPainter, QPen, QPainterPath, QPolygon, QImage
import math


class DrawingTools:
    def __init__(self, canvas):
        self.canvas = canvas

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

    def flood_fill(self, x, y, tolerance=None):
        """Tolerance-based scanline flood fill.
        Pixels within color distance of the target are filled,
        which closes the anti-aliased gaps left along drawn edges.
        """
        import numpy as np
        active = self.canvas.get_active()
        if not active.rect().contains(x, y): return
        w, h = active.width(), active.height()
        ptr = active.bits(); ptr.setsize(h * w * 4)
        arr = np.frombuffer(ptr, dtype=np.uint32).reshape((h, w)).copy()

        if tolerance is None: tolerance = self.canvas.fill_tolerance
        target = arr[y, x]
        fc = self.canvas.pen_color
        fill = np.uint32((fc.alpha() << 24) | (fc.red() << 16) |
                         (fc.green() << 8) | fc.blue())
        if target == fill: return

        # Vectorized tolerance check using numpy — massively faster than pixel loop
        ta = np.int32((target >> 24) & 0xFF)
        tr = np.int32((target >> 16) & 0xFF)
        tg = np.int32((target >>  8) & 0xFF)
        tb = np.int32( target        & 0xFF)

        # Build a boolean "fillable" map for the whole image upfront
        arr32 = arr.astype(np.int32)
        ca = (arr32 >> 24) & 0xFF
        cr = (arr32 >> 16) & 0xFF
        cg = (arr32 >>  8) & 0xFF
        cb =  arr32        & 0xFF
        fillable = (np.abs(cr-tr) + np.abs(cg-tg) + np.abs(cb-tb) + np.abs(ca-ta)) <= tolerance * 4

        mask = np.zeros((h, w), dtype=bool)
        stack = [(x, y)]
        while stack:
            cx, cy = stack.pop()
            if cx < 0 or cx >= w or cy < 0 or cy >= h: continue
            if mask[cy, cx] or not fillable[cy, cx]: continue
            xl = cx
            while xl > 0 and not mask[cy, xl-1] and fillable[cy, xl-1]: xl -= 1
            xr = cx
            while xr < w-1 and not mask[cy, xr+1] and fillable[cy, xr+1]: xr += 1
            mask[cy, xl:xr+1] = True
            for nx in range(xl, xr+1):
                if cy > 0 and not mask[cy-1, nx] and fillable[cy-1, nx]:
                    stack.append((nx, cy-1))
                if cy < h-1 and not mask[cy+1, nx] and fillable[cy+1, nx]:
                    stack.append((nx, cy+1))
        arr[mask] = fill
        result = QImage(arr.tobytes(), w, h, QImage.Format.Format_ARGB32_Premultiplied)
        p = QPainter(active)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.drawImage(0, 0, result); p.end()