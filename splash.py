"""
SQ Paint Splash Screen
Shows the app icon centered on a dark background while the main app loads.
"""
import os
from PyQt6.QtWidgets import QSplashScreen, QApplication
from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt, QTimer

SPLASH_W = 480
SPLASH_H = 480
ICON_SIZE = 280
BG_COLOR  = "#111111"


def _find_icon() -> str:
    """Locate the icon relative to this file (works both dev and bundled)."""
    base = getattr(__import__('sys'), '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    for name in ("sq_paint_icon.png", "SQ_Paint_Logo.png"):
        path = os.path.join(base, name)
        if os.path.exists(path):
            return path
    return ""


def make_splash_pixmap() -> QPixmap:
    canvas = QPixmap(SPLASH_W, SPLASH_H)
    canvas.fill(QColor(BG_COLOR))

    icon_path = _find_icon()
    if icon_path:
        icon = QPixmap(icon_path).scaled(
            ICON_SIZE, ICON_SIZE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        p = QPainter(canvas)
        x = (SPLASH_W - icon.width())  // 2
        y = (SPLASH_H - icon.height()) // 2
        p.drawPixmap(x, y, icon)
        p.end()

    return canvas


class SQSplash(QSplashScreen):
    def __init__(self):
        super().__init__(make_splash_pixmap())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)

    def mousePressEvent(self, event):
        # Don't close on click — let the app control timing
        pass
