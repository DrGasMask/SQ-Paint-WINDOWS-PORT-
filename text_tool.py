from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtCore import Qt, QPoint, QRect
from PyQt6.QtGui import QFont, QColor, QPainter, QFontMetrics, QTextOption


class TextTool:
    def __init__(self, canvas):
        self.canvas = canvas

        # Invisible QTextEdit used only as a keyboard input sink
        self.text_input = QTextEdit(self.canvas)
        self.text_input.setFrameStyle(0)
        self.text_input.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_input.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_input.setWordWrapMode(
            __import__("PyQt6.QtGui", fromlist=["QTextOption"]).QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        # Make the QTextEdit invisible — we draw the preview ourselves in paintEvent
        self.text_input.setStyleSheet("background: transparent; border: none; color: transparent;")
        self.text_input.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.text_input.hide()
        self.text_input.installEventFilter(self.canvas)

        # Connect text / selection changes to trigger a canvas repaint
        self.text_input.textChanged.connect(self.canvas.update)

        self.text_pos = QPoint()
        self.active = False   # True while a text session is open

    # ── public helpers ────────────────────────────────────────────────────────

    def start_text_input(self, pos):
        if self.text_input.isVisible():
            self.finalize_text()
            return
        self.text_pos = pos
        self.active = True
        # Place the hidden QTextEdit somewhere offscreen so it can receive focus/keys
        self.text_input.setGeometry(-2000, -2000, 1, 1)
        self.text_input.clear()
        self.text_input.show()
        self.text_input.setFocus()
        self.canvas.update()

    def finalize_text(self):
        if not self.text_input.isVisible():
            return
        content = self.text_input.toPlainText().strip()
        if content:
            self.canvas.undo_redo_manager.save_state()
            p = QPainter(self.canvas.get_active())
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            color = QColor(self.canvas.pen_color)
            color.setAlpha(self.canvas.pen_opacity)
            p.setPen(color)
            font = self._current_font()
            p.setFont(font)
            fm = p.fontMetrics()
            line_h = fm.height()
            for i, line in enumerate(content.split("\n")):
                p.drawText(self.text_pos.x() + 2,
                           self.text_pos.y() + self.canvas.font_size + i * line_h,
                           line)
            p.end()
            self.canvas._invalidate_composite()
        self.text_input.clear()
        self.text_input.hide()
        self.active = False
        self.canvas.update()

    def paint_preview(self, painter):
        """Called from Canvas.paintEvent while a text session is open.
        Draws the live WYSIWYG text preview including cursor and selection highlight."""
        if not self.active or not self.text_input.isVisible():
            return

        content = self.text_input.toPlainText()
        font = self._current_font()
        painter.setFont(font)
        fm = QFontMetrics(font)
        line_h = fm.height()
        lines = content.split("\n") if content else [""]

        # Measure bounding box for the dashed border
        max_w = max((fm.horizontalAdvance(l) for l in lines), default=0)
        total_h = line_h * max(len(lines), 1)
        x0 = self.text_pos.x() + 2
        y0 = self.text_pos.y()
        # The baseline of the first line sits font_size below y0, matching finalize_text
        baseline_offset = self.canvas.font_size

        # Dashed bounding box
        painter.save()
        painter.setPen(Qt.PenStyle.DashLine)
        from PyQt6.QtGui import QPen
        dash_pen = QPen(QColor(100, 160, 255, 200), 1, Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        pad = 4
        painter.drawRect(QRect(x0 - pad,
                               y0 + baseline_offset - fm.ascent() - pad,
                               max_w + pad * 2 + 20,   # +20 for a bit of breathing room
                               total_h + pad * 2))
        painter.restore()

        # Draw selection highlight
        cursor = self.text_input.textCursor()
        sel_start = min(cursor.selectionStart(), cursor.selectionEnd())
        sel_end   = max(cursor.selectionStart(), cursor.selectionEnd())
        full_text = content

        # Walk characters to paint selection rects per-line
        if sel_start != sel_end:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 120, 212, 80))
            char_idx = 0
            for li, line in enumerate(lines):
                line_start = char_idx
                line_end   = char_idx + len(line)
                ov_start = max(sel_start, line_start) - line_start
                ov_end   = min(sel_end,   line_end)   - line_start
                if ov_start < ov_end:
                    sx = x0 + fm.horizontalAdvance(line[:ov_start])
                    sw = fm.horizontalAdvance(line[ov_start:ov_end])
                    sy = y0 + baseline_offset - fm.ascent() + li * line_h
                    painter.drawRect(QRect(sx, sy, sw, line_h))
                char_idx += len(line) + 1  # +1 for \n
            painter.restore()

        # Draw text
        color = QColor(self.canvas.pen_color)
        color.setAlpha(self.canvas.pen_opacity)
        painter.setPen(color)
        painter.setFont(font)
        for i, line in enumerate(lines):
            painter.drawText(x0,
                             y0 + baseline_offset + i * line_h,
                             line)

        # Draw blinking cursor (always visible — blink handled by Qt focus)
        pos_in_line, line_idx = self._cursor_line_col(cursor.position(), lines)
        cx = x0 + fm.horizontalAdvance(lines[line_idx][:pos_in_line])
        cy_top = y0 + baseline_offset - fm.ascent() + line_idx * line_h
        painter.save()
        from PyQt6.QtGui import QPen
        painter.setPen(QPen(QColor(self.canvas.pen_color), 1))
        painter.drawLine(cx, cy_top, cx, cy_top + line_h)
        painter.restore()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _current_font(self):
        font = QFont(self.canvas.font_family, self.canvas.font_size)
        font.setBold(self.canvas.font_bold)
        font.setItalic(self.canvas.font_italic)
        return font

    def _cursor_line_col(self, pos, lines):
        """Return (col, line_index) for a given absolute cursor position."""
        idx = 0
        for li, line in enumerate(lines):
            end = idx + len(line)
            if pos <= end:
                return pos - idx, li
            idx = end + 1  # +1 for \n
        # fallback: end of last line
        return len(lines[-1]), len(lines) - 1
