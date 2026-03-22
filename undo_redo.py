class UndoRedoManager:
    def __init__(self, canvas):
        self.canvas = canvas
        self.undo_history = []
        self.redo_history = []
        self.max_undo = 30

    def save_state(self):
        if len(self.undo_history) > self.max_undo: self.undo_history.pop(0)
        self.undo_history.append({
            'layers': [img.copy() for img in self.canvas.layers],
            'names': list(self.canvas.layer_names),
            'visible': list(self.canvas.layer_visible),
            'active': self.canvas.active_layer
        })
        self.redo_history.clear(); self.canvas.modified = True

    def undo(self):
        self.canvas.selection_manager.commit_selection()
        if self.undo_history:
            self.redo_history.append({'layers': [img.copy() for img in self.canvas.layers],
                'names': list(self.canvas.layer_names), 'visible': list(self.canvas.layer_visible),
                'active': self.canvas.active_layer})
            state = self.undo_history.pop()
            self.canvas.layers, self.canvas.layer_names, self.canvas.layer_visible, self.canvas.active_layer = \
                state['layers'], state['names'], state['visible'], state['active']
            self.canvas._invalidate_composite()
            if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
            self.canvas.set_zoom(self.canvas.zoom_factor)

    def redo(self):
        self.canvas.selection_manager.commit_selection()
        if self.redo_history:
            self.undo_history.append({'layers': [img.copy() for img in self.canvas.layers],
                'names': list(self.canvas.layer_names), 'visible': list(self.canvas.layer_visible),
                'active': self.canvas.active_layer})
            state = self.redo_history.pop()
            self.canvas.layers, self.canvas.layer_names, self.canvas.layer_visible, self.canvas.active_layer = \
                state['layers'], state['names'], state['visible'], state['active']
            self.canvas._invalidate_composite()
            if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
            self.canvas.set_zoom(self.canvas.zoom_factor)
