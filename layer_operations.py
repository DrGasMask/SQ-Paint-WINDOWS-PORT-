# layer_operations.py
# Contains layer management functionality

from PyQt6.QtWidgets import QInputDialog, QMessageBox

def refresh_layer_panel(app):
    """Refresh the layer panel display"""
    # Clear existing layer cards
    while app.layer_list_container.count():
        child = app.layer_list_container.takeAt(0)
        if child.widget():
            child.widget().deleteLater()

    # Add layer cards in reverse order (top layer first)
    for i in reversed(range(len(app.canvas.layers))):
        from ui_components import LayerCard
        card = LayerCard(i, app.canvas, app)
        app.layer_list_container.addWidget(card)

def set_active_layer(app, idx):
    """Set the active layer"""
    app.canvas.active_layer = idx
    app.canvas._invalidate_composite()
    app.refresh_layer_panel()
    app.canvas.update()

def toggle_visibility(app, idx):
    """Toggle layer visibility"""
    app.canvas.layer_visible[idx] = not app.canvas.layer_visible[idx]
    app.canvas._invalidate_composite()
    app.refresh_layer_panel()
    app.canvas.update()

def rename_layer(app, idx):
    """Rename a layer"""
    name, ok = QInputDialog.getText(app, "Rename Layer", "New name:",
                                   text=app.canvas.layer_names[idx])
    if ok and name.strip():
        app.canvas.layer_names[idx] = name.strip()
        app.refresh_layer_panel()