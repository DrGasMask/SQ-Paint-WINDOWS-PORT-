from PyQt6.QtGui import QPainter, QImage
from PyQt6.QtCore import Qt


class LayerManager:
    def __init__(self, canvas):
        self.canvas = canvas

    def add_new_layer(self):
        self.canvas.save_state()
        new_img = QImage(self.canvas.layers[0].size(), QImage.Format.Format_ARGB32_Premultiplied)
        new_img.fill(Qt.GlobalColor.transparent)
        self.canvas.layers.append(new_img)
        self.canvas.layer_names.append(f"Layer {len(self.canvas.layers)}")
        self.canvas.layer_visible.append(True); self.canvas.active_layer = len(self.canvas.layers) - 1
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()

    def delete_layer(self, index):
        if len(self.canvas.layers) <= 1: return
        self.canvas.save_state()
        self.canvas.layers.pop(index); self.canvas.layer_names.pop(index); self.canvas.layer_visible.pop(index)
        self.canvas.active_layer = min(self.canvas.active_layer, len(self.canvas.layers) - 1)
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()

    def duplicate_layer(self, index):
        self.canvas.save_state()
        self.canvas.layers.insert(index + 1, self.canvas.layers[index].copy())
        self.canvas.layer_names.insert(index + 1, self.canvas.layer_names[index] + " Copy")
        self.canvas.layer_visible.insert(index + 1, self.canvas.layer_visible[index])
        self.canvas.active_layer = index + 1
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()

    def move_layer(self, from_idx, to_idx):
        """Move layer from from_idx to to_idx, shifting others accordingly."""
        if from_idx == to_idx: return
        if not (0 <= from_idx < len(self.canvas.layers)): return
        if not (0 <= to_idx < len(self.canvas.layers)): return
        self.canvas.save_state()
        for lst in [self.canvas.layers, self.canvas.layer_names, self.canvas.layer_visible]:
            item = lst.pop(from_idx)
            lst.insert(to_idx, item)
        self.canvas.active_layer = to_idx
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()

    def rename_layer(self, index, name):
        if not name.strip(): return
        self.canvas.layer_names[index] = name.strip()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()

    def merge_down(self, index):
        if index <= 0: return
        self.canvas.save_state()
        below = index - 1
        merged = QImage(self.canvas.layers[below].size(), QImage.Format.Format_ARGB32_Premultiplied)
        merged.fill(Qt.GlobalColor.transparent)
        p = QPainter(merged)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(0, 0, self.canvas.layers[below]); p.drawImage(0, 0, self.canvas.layers[index])
        p.end()
        self.canvas.layers[below] = merged
        self.canvas.layers.pop(index); self.canvas.layer_names.pop(index); self.canvas.layer_visible.pop(index)
        self.canvas.active_layer = below
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()

    def merge_up(self, index):
        if index >= len(self.canvas.layers) - 1: return
        self.canvas.save_state()
        above = index + 1
        merged = QImage(self.canvas.layers[above].size(), QImage.Format.Format_ARGB32_Premultiplied)
        merged.fill(Qt.GlobalColor.transparent)
        p = QPainter(merged)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(0, 0, self.canvas.layers[index]); p.drawImage(0, 0, self.canvas.layers[above])
        p.end()
        self.canvas.layers[above] = merged
        self.canvas.layers.pop(index); self.canvas.layer_names.pop(index); self.canvas.layer_visible.pop(index)
        self.canvas.active_layer = above - 1
        self.canvas._invalidate_composite()
        if self.canvas.layers_changed_callback: self.canvas.layers_changed_callback()
        self.canvas.update()