# file_operations.py
# Contains file open/save functionality

import os
from PyQt6.QtWidgets import QFileDialog, QMessageBox
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtCore import Qt, QRect


def import_sqish(app):
    """Open a .sqish project, replacing the entire canvas state."""
    file_path, _ = QFileDialog.getOpenFileName(
        app, "Open SQ Paint Project", "",
        "SQ Paint Project (*.sqish)"
    )
    if not file_path:
        return
    if app.canvas.load_sqish(file_path):
        app._current_file = file_path
        app.setWindowTitle("SQ Paint v1.45 - " + os.path.basename(file_path))
        app.status.showMessage("Opened " + os.path.basename(file_path), 3000)
        if hasattr(app, 'refresh_layer_panel'):
            app.refresh_layer_panel()
    else:
        QMessageBox.warning(app, "Error", "Failed to load project file.")


def import_image(app):
    """Import an image file onto the canvas as a new floating selection.
    Can be called multiple times to layer images one after another."""
    file_path, _ = QFileDialog.getOpenFileName(
        app, "Import Image", "",
        "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
    )
    if not file_path:
        return

    img = QImage(file_path)
    if img.isNull():
        QMessageBox.warning(app, "Error", "Failed to load image.")
        return

    # Commit any existing floating selection before pasting the new image
    app.canvas.commit_selection()
    app.canvas.save_state()

    # Convert and paste as a floating selection centered on the canvas
    pasted = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    cw = app.canvas.layers[0].width()
    ch = app.canvas.layers[0].height()
    x = max(0, (cw - pasted.width())  // 2)
    y = max(0, (ch - pasted.height()) // 2)

    sm = app.canvas.selection_manager
    sm.selection_buffer = pasted
    sm.selection_rect = QRect(x, y, pasted.width(), pasted.height())
    sm.selection_angle = 0.0
    sm.selection_state = "selected"

    # Switch to select tool so the user can immediately reposition it
    app.canvas.tool = "select"
    if hasattr(app, 'tools'):
        for name, btn in app.tools.items():
            btn.setChecked(name == "select")
    if hasattr(app, 'tool_lbl'):
        app.tool_lbl.setText("Tool: Select")

    app.canvas.update()
    app.status.showMessage(
        f"Imported {os.path.basename(file_path)} — move it then click elsewhere to place", 5000)


def save_file(app):
    """Always show the format/filename dialog when saving."""
    app._do_save()
