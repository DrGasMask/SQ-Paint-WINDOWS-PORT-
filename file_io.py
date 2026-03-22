import zipfile, json, tempfile, os
from PyQt6.QtGui import QImage
from PyQt6.QtCore import QRect


class FileIO:
    @staticmethod
    def save_sqish(canvas, path):
        """Save full project (all layers) to a .sqish file (zip + JSON manifest)."""
        try:
            canvas.selection_manager.commit_selection()
            with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
                manifest = {
                    'version': 1,
                    'active_layer': canvas.active_layer,
                    'layer_names': canvas.layer_names,
                    'layer_visible': canvas.layer_visible,
                    'layer_count': len(canvas.layers),
                }
                zf.writestr('manifest.json', json.dumps(manifest, indent=2))
                for i, layer in enumerate(canvas.layers):
                    # Save each layer to a temp PNG file then read bytes
                    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    tmp.close()
                    layer.save(tmp.name, 'PNG')
                    with open(tmp.name, 'rb') as f:
                        png_bytes = f.read()
                    os.unlink(tmp.name)
                    zf.writestr(f'layer_{i}.png', png_bytes)
            return True
        except Exception as e:
            print(f'sqish save error: {e}')
            return False

    @staticmethod
    def load_sqish(canvas, path):
        """Load a .sqish project file, restoring all layers exactly."""
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                manifest = json.loads(zf.read('manifest.json'))
                count = manifest['layer_count']
                layers = []
                for i in range(count):
                    data = zf.read(f'layer_{i}.png')
                    # Write to temp file and load via QImage (most reliable path)
                    tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                    tmp.write(data); tmp.close()
                    img = QImage(tmp.name)
                    os.unlink(tmp.name)
                    if img.isNull():
                        raise ValueError(f'Failed to load layer_{i}.png')
                    img = img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                    layers.append(img)
                canvas.layers = layers
                canvas.layer_names = manifest['layer_names']
                canvas.layer_visible = manifest['layer_visible']
                canvas.active_layer = min(manifest['active_layer'], len(layers)-1)
                canvas.selection_manager.selection_state = 'idle'
                canvas.selection_manager.selection_buffer = None
                canvas.selection_manager.selection_rect = QRect()
                canvas._invalidate_composite()
                if canvas.layers_changed_callback: canvas.layers_changed_callback()
                canvas.set_zoom(canvas.zoom_factor)
            return True
        except Exception as e:
            print(f'sqish load error: {e}')
            return False