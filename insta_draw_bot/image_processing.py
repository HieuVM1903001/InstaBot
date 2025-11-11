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
