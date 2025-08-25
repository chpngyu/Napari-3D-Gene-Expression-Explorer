import os
import numpy as np
import pandas as pd
from skimage.io import imread
import napari
from magicgui import magicgui
from qtpy.QtWidgets import QFileDialog, QVBoxLayout, QWidget
from magicgui.widgets import LineEdit, PushButton
import matplotlib.pyplot as plt
from skimage.exposure import rescale_intensity

image_color = 'I Blue' # 'I Orange'

def load_color_images(image_dir):
    image_layers = {}
    for fname in os.listdir(image_dir):
        if fname.endswith('.png') and fname.startswith("region_"):
            region_id = os.path.splitext(fname)[0].split('_')[1]
            image = imread(os.path.join(image_dir, fname))  # Keep original color
            image_layers[region_id] = image
    return image_layers

def stack_images_by_region(image_layers):
    sorted_keys = sorted(image_layers.keys(), key=lambda x: int(x))
    stack = np.stack([image_layers[k] for k in sorted_keys], axis=0)
    return stack, sorted_keys

def map_expression_to_points(spots_df, expr_df, gene, region_ids, min_value=1, max_value=30):
    spot_coords = []
    spot_colors = []

    for _, row in spots_df.iterrows():
        region = str(row['region_id'])
        if region not in region_ids or row['spot_id'] not in expr_df.columns:
            continue
        z_index = region_ids.index(region)
        x, y = row['pixel_x'], row['pixel_y']
        value = expr_df.at[gene, row['spot_id']] if gene in expr_df.index else 0.0
        if value < min_value:
            continue
        spot_coords.append([z_index, y, x])
        spot_colors.append(min(value, max_value))
        #spot_colors.append(min(value, max_value)/max_value)

    coords = np.array(spot_coords)
    values = np.array(spot_colors, dtype=np.float32)
    return coords, values

def log_normalize(values):
    values = np.array(values)
    if np.any(values <= 0):
        raise ValueError("All values must be positive for log transformation.")
    
    # Apply log transformation
    log_values = np.log(values)
    
    # Normalize to range [0, 1]
    min_log = np.min(log_values)
    max_log = np.max(log_values)
    
    # Avoid division by zero if all log_values are the same
    if max_log == min_log:
        return np.zeros_like(log_values)
    
    normalized = (log_values - min_log) / (max_log - min_log)
    return normalized


if __name__ == '__main__':
    viewer = napari.Viewer()
    viewer.dims.ndisplay = 3  # Set default to 3D view

    @magicgui(call_button="Load & Show", layout='vertical',
              image_dir={"label": "Color Image Directory"},
              spot_file={"label": "Spot Data CSV"},
              expr_file={"label": "Gene Expression CSV (.csv.gz)"},
              z_spacing={"label": "Z-Spacing", "min": 1, "max": 100, "step": 1})
    def show_expression_widget(viewer: napari.Viewer,
                               image_dir=QFileDialog.getExistingDirectory(),
                               spot_file=QFileDialog.getOpenFileName()[0],
                               expr_file=QFileDialog.getOpenFileName()[0],
                               z_spacing: int = 35):

        image_layers = load_color_images(image_dir)
        stack, region_ids = stack_images_by_region(image_layers)
        viewer.add_image(stack, name="Color Z-Stack", opacity=0.5, scale=(z_spacing, 1, 1),
            colormap = image_color, blending= 'minimum')  # Keep RGB, no grayscale colormap

        spots_df = pd.read_csv(spot_file)
        expr_df = pd.read_csv(expr_file, index_col=0, compression='gzip')  # Read .csv.gz
        
        # Create a text input box for gene name
        gene_input = LineEdit(label="Gene Name")

        # Create a button to trigger expression update
        gene_button = PushButton(label="Display Gene Expression")

        def update_gene_expression():
            gene = gene_input.value
            if gene not in expr_df.index:
                print(f"Gene '{gene}' not found in expression matrix.")
                return

            coords, values = map_expression_to_points(spots_df, expr_df, gene, region_ids)
            if 'Gene Expression' in viewer.layers:
                print('Updating Gene Expression layer')
                viewer.layers['Gene Expression'].data = coords
                viewer.layers['Gene Expression'].features = {'expression': values}
            else:
                print('Adding Gene Expression layer')
                cmap = plt.get_cmap('jet') # plasma
                colors_array = cmap(log_normalize(values))
                layer = viewer.add_points(coords, name='Gene Expression', size=15,
                                  face_color=colors_array, border_width=0,
                                  opacity=0.3, scale=(z_spacing, 1, 1),
                                  out_of_slice_display=True) # remove features={'expression': values}
                #layer.edge_width = 0
        gene_button.changed.connect(update_gene_expression)
        
        # Add to Napari as a docked widget
        container = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(gene_input.native)
        layout.addWidget(gene_button.native)
        container.setLayout(layout)
        viewer.window.add_dock_widget(container, area='right', name='Gene Selector')

    viewer.window.add_dock_widget(show_expression_widget, area='right', name='Expression Loader')
    napari.run()
