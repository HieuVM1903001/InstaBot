import cv2
import numpy as np
from PIL import Image
from typing import Tuple, List


def load_and_fit_image(path: str, target_w: int, target_h: int) -> Tuple[Image.Image, Tuple[int, int]]:
    """Load image and resize to fit inside target_w x target_h keeping aspect ratio.

    Returns: (PIL.Image, (offset_x, offset_y)) where offsets are the top-left offsets inside the target box.
    """
    img = Image.open(path).convert("RGBA")
    w, h = img.size
    scale = min(target_w / w, target_h / h)
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))
    img2 = img.resize((new_w, new_h), Image.LANCZOS)
    offset_x = (target_w - new_w) // 2
    offset_y = (target_h - new_h) // 2
    return img2, (offset_x, offset_y)


def edges_to_strokes(pil_img: Image.Image, edge_thresh1=50, edge_thresh2=150) -> List[List[Tuple[int, int]]]:
    """Simple edge detection -> contour extraction. Returns list of strokes (list of points).
    Coordinates are pixel coordinates in the resized image space.
    """
    arr = np.array(pil_img.convert("L"))
    edges = cv2.Canny(arr, edge_thresh1, edge_thresh2)
    # Dilate to make contours more continuous
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    strokes = []
    for c in contours:
        pts = [(int(p[0][0]), int(p[0][1])) for p in c]
        if len(pts) > 3:
            strokes.append(pts)
    return strokes


def dots_from_image(pil_img: Image.Image, grid=10, threshold=128) -> List[Tuple[int, int]]:
    """Generate dot positions by sampling a grid and using brightness threshold.
    Returns list of (x,y) pixel positions.
    """
    arr = np.array(pil_img.convert("L"))
    h, w = arr.shape
    dots = []
    for y in range(0, h, grid):
        for x in range(0, w, grid):
            val = arr[y, x]
            if val < threshold:
                dots.append((x, y))
    return dots


def color_grid(pil_img: Image.Image, grid=12) -> List[Tuple[int, int, Tuple[int, int, int]]]:
    """Divide the image into grid x grid cells and return a list of (x, y, (r,g,b)) where
    x,y are the pixel coordinates of the cell center and (r,g,b) is the average color.
    Coordinates are in image pixel space.
    """
    img_rgb = pil_img.convert("RGB")
    arr = np.array(img_rgb)
    h, w, _ = arr.shape
    cells = []
    for y in range(0, h, grid):
        for x in range(0, w, grid):
            x2 = min(x + grid, w)
            y2 = min(y + grid, h)
            block = arr[y:y2, x:x2]
            if block.size == 0:
                continue
            avg = block.reshape(-1, 3).mean(axis=0)
            cx = x + (x2 - x) // 2
            cy = y + (y2 - y) // 2
            cells.append((cx, cy, (int(avg[0]), int(avg[1]), int(avg[2]))))
    return cells


import cv2
import numpy as np
from PIL import Image
from typing import Tuple, List
import math


def generate_fill_paths(pil_img: Image.Image, palette: List[Tuple[int, int, int]], 
                       mode: str = "contour", spacing: int = 8, min_area: int = 50) -> List[dict]:
    """
    Generate artistic fill paths for each color in the palette.
    
    Args:
        pil_img: Source image to analyze
        palette: List of RGB colors to map
        mode: Fill pattern - 'none', 'dot', 'stipple', 'hatch-h', 'hatch-v', 
              'hatch-cross', 'hatch-diagonal', 'contour', 'spiral', 'wave'
        spacing: Distance between pattern elements (pixels)
        min_area: Minimum region size to fill (pixels)
    
    Returns:
        List of dicts with 'color' (RGB tuple) and 'paths' (list of point lists)
    """
    mode = (mode or "none").lower()
    if mode == "none":
        return []

    img_rgb = pil_img.convert("RGB")
    arr = np.array(img_rgb)
    h, w, _ = arr.shape
    
    if not palette:
        return []

    # Map each pixel to its nearest palette color
    color_masks = _create_color_masks(arr, palette, h, w, min_area)
    
    results = []
    for palette_idx, (color, mask) in enumerate(color_masks):
        paths = _generate_paths_for_mask(mask, mode, spacing, w, h)
        
        if paths:
            results.append({"color": color, "paths": paths})
    
    return results


def _create_color_masks(arr: np.ndarray, palette: List[Tuple[int, int, int]], 
                        h: int, w: int, min_area: int) -> List[Tuple[Tuple[int, int, int], np.ndarray]]:
    """Map pixels to palette colors and create smoothed masks for each color."""
    flat_pixels = arr.reshape(-1, 3).astype(np.int32)
    palette_array = np.array(palette).astype(np.int32)
    
    # Calculate squared distances to each palette color
    distances = ((flat_pixels[:, None, :] - palette_array[None, :, :]) ** 2).sum(axis=2)
    nearest_indices = distances.argmin(axis=1).reshape(h, w).astype(np.uint8)
    
    masks = []
    for palette_idx, color in enumerate(palette):
        mask = (nearest_indices == palette_idx).astype(np.uint8)
        
        if mask.sum() < min_area:
            continue
        
        # Smooth the mask to reduce noise
        mask_8bit = (mask * 255).astype(np.uint8)
        mask_8bit = cv2.medianBlur(mask_8bit, 3)
        
        masks.append((color, mask_8bit))
    
    return masks


def _generate_paths_for_mask(mask: np.ndarray, mode: str, spacing: int, 
                             w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Generate fill pattern paths for a single color mask."""
    
    if mode == "dot":
        return _generate_dot_pattern(mask, spacing, w, h)
    
    elif mode == "stipple":
        return _generate_stipple_pattern(mask, spacing, w, h)
    
    elif mode == "hatch-h":
        return _generate_horizontal_hatch(mask, spacing, w, h)
    
    elif mode == "hatch-v":
        return _generate_vertical_hatch(mask, spacing, w, h)
    
    elif mode == "hatch-cross":
        paths = _generate_horizontal_hatch(mask, spacing, w, h)
        paths.extend(_generate_vertical_hatch(mask, spacing, w, h))
        return paths
    
    elif mode == "hatch-diagonal":
        return _generate_diagonal_hatch(mask, spacing, w, h)
    
    elif mode == "wave":
        return _generate_wave_pattern(mask, spacing, w, h)
    
    elif mode == "spiral":
        return _generate_spiral_pattern(mask, spacing, w, h)
    
    else:  # contour (default)
        return _generate_contour_pattern(mask, spacing, min_area=50)


def _generate_dot_pattern(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Regular grid of dots."""
    paths = []
    for y in range(0, h, spacing):
        for x in range(0, w, spacing):
            if mask[y, x] > 0:
                paths.append([(x, y)])
    return paths


def _generate_stipple_pattern(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Randomized dot positions for organic feel."""
    paths = []
    np.random.seed(42)  # Consistent pattern
    
    for y in range(0, h, spacing):
        for x in range(0, w, spacing):
            # Add random offset for natural look
            jitter = spacing // 3
            rx = x + np.random.randint(-jitter, jitter + 1)
            ry = y + np.random.randint(-jitter, jitter + 1)
            
            rx = max(0, min(w - 1, rx))
            ry = max(0, min(h - 1, ry))
            
            if mask[ry, rx] > 0:
                paths.append([(rx, ry)])
    
    return paths


def _generate_horizontal_hatch(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Horizontal hatching lines."""
    paths = []
    
    for y in range(0, h, spacing):
        current_line = None
        
        for x in range(w):
            if mask[y, x] > 0:
                if current_line is None:
                    current_line = [(x, y)]
            else:
                if current_line is not None:
                    current_line.append((x - 1, y))
                    paths.append(current_line)
                    current_line = None
        
        # Close line at edge
        if current_line is not None:
            current_line.append((w - 1, y))
            paths.append(current_line)
    
    return paths


def _generate_vertical_hatch(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Vertical hatching lines."""
    paths = []
    
    for x in range(0, w, spacing):
        current_line = None
        
        for y in range(h):
            if mask[y, x] > 0:
                if current_line is None:
                    current_line = [(x, y)]
            else:
                if current_line is not None:
                    current_line.append((x, y - 1))
                    paths.append(current_line)
                    current_line = None
        
        # Close line at edge
        if current_line is not None:
            current_line.append((x, h - 1))
            paths.append(current_line)
    
    return paths


def _generate_diagonal_hatch(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Diagonal hatching (45° and -45°)."""
    paths = []
    
    # Forward diagonal (↘)
    for offset in range(0, w + h, spacing):
        line_points = []
        x_start = max(0, offset - h + 1)
        x_end = min(w - 1, offset)
        
        for x in range(x_start, x_end + 1):
            y = offset - x
            if 0 <= y < h and mask[y, x] > 0:
                line_points.append((x, y))
            elif line_points:
                paths.append([line_points[0], line_points[-1]])
                line_points = []
        
        if line_points:
            paths.append([line_points[0], line_points[-1]])
    
    # Backward diagonal (↙)
    for offset in range(-h, w, spacing):
        line_points = []
        
        for x in range(max(0, offset), min(w, offset + h)):
            y = x - offset
            if 0 <= y < h and mask[y, x] > 0:
                line_points.append((x, y))
            elif line_points:
                paths.append([line_points[0], line_points[-1]])
                line_points = []
        
        if line_points:
            paths.append([line_points[0], line_points[-1]])
    
    return paths


def _generate_wave_pattern(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Wavy horizontal lines for organic feel."""
    paths = []
    wave_amplitude = spacing
    wave_frequency = 0.3
    
    for y in range(0, h, spacing):
        wave_points = []
        
        for x in range(w):
            # Calculate wave offset
            wave_y = int(y + wave_amplitude * math.sin(x * wave_frequency))
            wave_y = max(0, min(h - 1, wave_y))
            
            if mask[wave_y, x] > 0:
                wave_points.append((x, wave_y))
            elif wave_points:
                if len(wave_points) > 3:  # Only keep substantial segments
                    paths.append(wave_points)
                wave_points = []
        
        if wave_points and len(wave_points) > 3:
            paths.append(wave_points)
    
    return paths


def _generate_spiral_pattern(mask: np.ndarray, spacing: int, w: int, h: int) -> List[List[Tuple[int, int]]]:
    """Concentric rectangular spirals inward."""
    paths = []
    visited = np.zeros_like(mask, dtype=bool)
    
    # Start from edges and spiral inward
    layer = 0
    while layer < min(w, h) // 2:
        spiral_path = []
        
        # Top edge (left to right)
        y = layer
        if y < h:
            for x in range(layer, w - layer):
                if x < w and not visited[y, x] and mask[y, x] > 0:
                    spiral_path.append((x, y))
                    visited[y, x] = True
        
        # Right edge (top to bottom)
        x = w - layer - 1
        if x >= 0:
            for y in range(layer + 1, h - layer):
                if y < h and not visited[y, x] and mask[y, x] > 0:
                    spiral_path.append((x, y))
                    visited[y, x] = True
        
        # Bottom edge (right to left)
        y = h - layer - 1
        if y >= 0:
            for x in range(w - layer - 2, layer - 1, -1):
                if x >= 0 and not visited[y, x] and mask[y, x] > 0:
                    spiral_path.append((x, y))
                    visited[y, x] = True
        
        # Left edge (bottom to top)
        x = layer
        if x < w:
            for y in range(h - layer - 2, layer, -1):
                if y >= 0 and not visited[y, x] and mask[y, x] > 0:
                    spiral_path.append((x, y))
                    visited[y, x] = True
        
        if spiral_path:
            paths.append(spiral_path)
        
        layer += spacing
    
    return paths


def _generate_contour_pattern(mask: np.ndarray, spacing: int, min_area: int) -> List[List[Tuple[int, int]]]:
    """Follow the edges/contours of regions."""
    paths = []
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < min_area:
            continue
        
        points = [(int(p[0][0]), int(p[0][1])) for p in contour]
        if len(points) > 2:
            # Break into segments for smoother drawing
            segment_length = max(2, spacing // 2)
            for i in range(0, len(points), segment_length):
                end_idx = min(i + segment_length, len(points) - 1)
                paths.append([points[i], points[end_idx]])
    
    return paths


def map_strokes_to_normalized(strokes: List[List[Tuple[int, int]]], img_w: int, img_h: int):
    """Convert stroke coordinates (pixels) to normalized [0..1] coordinates.
    Returns list of strokes where each stroke is list of (nx, ny).
    """
    res = []
    for s in strokes:
        ss = []
        for x, y in s:
            ss.append((x / img_w, y / img_h))
        res.append(ss)
    return res


def map_points_to_normalized(points: List[Tuple[int, int]], img_w: int, img_h: int):
    return [(x / img_w, y / img_h) for x, y in points]
