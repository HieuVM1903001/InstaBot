import math
from typing import Tuple, List, Optional


def clamp(v, a, b):
    return max(a, min(b, v))


# --- color conversion helpers (sRGB -> CIEXYZ -> CIELab) ---
def _srgb_to_linear(c: float) -> float:
    c = c / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _rgb_to_xyz(rgb: Tuple[int, int, int]):
    r_lin = _srgb_to_linear(rgb[0])
    g_lin = _srgb_to_linear(rgb[1])
    b_lin = _srgb_to_linear(rgb[2])
    # sRGB D65
    x = r_lin * 0.4124564 + g_lin * 0.3575761 + b_lin * 0.1804375
    y = r_lin * 0.2126729 + g_lin * 0.7151522 + b_lin * 0.0721750
    z = r_lin * 0.0193339 + g_lin * 0.1191920 + b_lin * 0.9503041
    return (x, y, z)


def _xyz_to_lab(x, y, z):
    # D65 reference white
    xr = x / 0.95047
    yr = y / 1.00000
    zr = z / 1.08883

    def f(t):
        if t > 0.008856:
            return t ** (1.0 / 3.0)
        return (7.787 * t) + (16.0 / 116.0)

    fx = f(xr)
    fy = f(yr)
    fz = f(zr)

    L = (116.0 * fy) - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return (L, a, b)


def rgb_to_lab(rgb: Tuple[int, int, int]):
    x, y, z = _rgb_to_xyz(rgb)
    return _xyz_to_lab(x, y, z)


def _lab_distance(a_lab, b_lab):
    return math.sqrt((a_lab[0] - b_lab[0]) ** 2 + (a_lab[1] - b_lab[1]) ** 2 + (a_lab[2] - b_lab[2]) ** 2)


def find_nearest_color(target: Tuple[int, int, int], palette: List[Tuple[int, int, int]], prev_idx: Optional[int] = None, stickiness: float = 0.2):
    """
    Find the closest matching color in the palette to the target color.
    
    Uses perceptual color distance (CIELab) so matches look natural to human eyes.
    
    Args:
        target: RGB color to match (r, g, b) where each component is 0-255
        palette: List of available RGB colors to choose from
        prev_idx: Index of previously used color (helps reduce flickering)
        stickiness: How much to prefer the previous color (0=no preference, 1=maximum preference)
    
    Returns:
        The closest matching color from the palette
    """
    if not palette:
        return target

    target_lab = rgb_to_lab(target)
    
    closest_color = None
    smallest_distance = float('inf')
    
    for idx, palette_color in enumerate(palette):
        palette_lab = rgb_to_lab(palette_color)
        distance = _lab_distance(target_lab, palette_lab)
        
        # If this was the previous color, make it "stickier" to reduce color flickering
        if idx == prev_idx:
            distance *= (1.0 - stickiness)
        
        if distance < smallest_distance:
            smallest_distance = distance
            closest_color = palette_color
    
    return closest_color
