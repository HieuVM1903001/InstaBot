import threading
import time
from typing import Tuple, List, Optional
import json
import os
import pyautogui
from pynput import mouse, keyboard
from pynput.mouse import Button, Controller as MouseController
from . import image_processing, utils


class Controller:
    def __init__(
        self,
        image_path: str,
        speed: float = 1.0,
        dry_run: bool = False,
        move_delay: float = 0.001,
        color_mode: bool = False,
        initial_bbox: Optional[Tuple[int, int, int, int]] = None,
        initial_palette_positions: Optional[List[Tuple[int, int]]] = None,
        initial_palette_colors: Optional[List[Tuple[int, int, int]]] = None,
    ):
        self.image_path = image_path
        self.speed = max(0.01, float(speed))
        self.dry_run = bool(dry_run)
        self.move_delay = max(0.0, float(move_delay))
        self.color_mode = bool(color_mode)

        self.bbox = None
        self._waiting_bbox = False
        self._waiting_color_click = False
        self.palette_positions = []
        self.palette_colors = []
        self._stop_flag = threading.Event()
        self._draw_thread = None

        # Real mouse controller
        self.mouse = MouseController()

        # Listeners
        self.mouse_listener = mouse.Listener(on_click=self._on_click)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_press)

        # Fast PyAutoGUI fallback
        try:
            pyautogui.PAUSE = 0
            pyautogui.FAILSAFE = False
        except Exception:
            pass
        # apply initial config if provided
        if initial_bbox:
            try:
                self.bbox = tuple(int(v) for v in initial_bbox)
                print(f"Loaded initial bbox from config: {self.bbox}")
            except Exception:
                pass
        if initial_palette_positions:
            self.palette_positions = [tuple(int(v) for v in p) for p in initial_palette_positions]
            print(f"Loaded {len(self.palette_positions)} palette positions from config")
        if initial_palette_colors:
            self.palette_colors = [tuple(int(v) for v in c) for c in initial_palette_colors]
            print(f"Loaded {len(self.palette_colors)} palette colors from config")

    def start_listeners(self):
        self.mouse_listener.start()
        self.keyboard_listener.start()
        print("Listeners started. 's' = canvas, f = color, Enter = draw, Esc = stop.")

    def _on_click(self, x, y, button, pressed):
        if not pressed:
            return
        if self._waiting_bbox:
            if self.bbox is None:
                self.bbox = (int(x), int(y), 0, 0)
                print(f"Top-left set: {self.bbox[0:2]}")
            else:
                x1, y1, _, _ = self.bbox
                self.bbox = (x1, y1, int(x), int(y))
                self._waiting_bbox = False
                print(f"Bounding box final: {self.bbox}")
            return
        if self._waiting_color_click:
            img = pyautogui.screenshot()
            try:
                c = img.getpixel((int(x), int(y)))
            except Exception:
                c = (0, 0, 0)
            self.palette_positions.append((int(x), int(y)))
            self.palette_colors.append((c[0], c[1], c[2]))
            self._waiting_color_click = False
            print(f"Saved palette color {self.palette_colors[-1]} at {self.palette_positions[-1]}")

    def _on_press(self, key):
        try:
            ch = key.char
        except AttributeError:
            ch = None
        # toggle bbox selection on 's' (lower or upper)
        if ch and ch.lower() == "s":
            if not self._waiting_bbox:
                self._waiting_bbox = True
                self.bbox = None
                print("'s' pressed: click top-left then bottom-right to set canvas bounds.")
            return
        if ch == "f":
            print("Click a color point to sample it.")
            self._waiting_color_click = True
            return
        if key == keyboard.Key.enter:
            if self.bbox is None:
                print("No bounding box set!")
                return
            if self._draw_thread is None or not self._draw_thread.is_alive():
                print("Start drawing...")
                self._stop_flag.clear()
                self._draw_thread = threading.Thread(target=self._run_drawing)
                self._draw_thread.start()
            return
        if key == keyboard.Key.esc:
            print("Stopping drawing...")
            self._stop_flag.set()
            return

    def _run_drawing(self):
        # ensure bbox
        if not self.bbox:
            print("No bounding box defined!")
            return

        x1, y1, x2, y2 = self.bbox
        w, h = abs(x2 - x1), abs(y2 - y1)
        top_left_x, top_left_y = min(x1, x2), min(y1, y2)

        print(f"Preparing image region {w}x{h} at ({top_left_x},{top_left_y})")
        img, offset = image_processing.load_and_fit_image(self.image_path, w, h)
        off_x, off_y = offset

        strokes_px = image_processing.edges_to_strokes(img)
        dots_px = image_processing.dots_from_image(img, grid=12, threshold=140)
        strokes_norm = image_processing.map_strokes_to_normalized(strokes_px, img.size[0], img.size[1])
        dots_norm = image_processing.map_points_to_normalized(dots_px, img.size[0], img.size[1])

        color_cells = []
        if self.color_mode:
            color_cells = image_processing.color_grid(img, grid=12)

        print(f"{len(strokes_norm)} strokes, {len(dots_norm)} dots, {len(color_cells)} color cells")

        def to_screen(nx, ny):
            px = int(top_left_x + off_x + nx * img.size[0])
            py = int(top_left_y + off_y + ny * img.size[1])
            return px, py

        def sample_img_color(nx, ny):
            ix = int(min(max(0, nx * img.size[0]), img.size[0] - 1))
            iy = int(min(max(0, ny * img.size[1]), img.size[1] - 1))
            c = img.getpixel((ix, iy))
            return (c[0], c[1], c[2])

        # Faster delays: reduced minimums for snappier movement
        MOVE_DELAY = max(0.001, 0.0005 / self.speed)
        STROKE_GAP = max(0.002, 0.0015 / self.speed)
        DOT_DELAY = max(0.0005, 0.0001 / self.speed)

        palette = list(self.palette_colors)
        prev_palette_idx = None

        def select_palette(idx):
            nonlocal prev_palette_idx
            if idx is not None and idx != prev_palette_idx and idx < len(self.palette_positions):
                px, py = self.palette_positions[idx]
                if self.dry_run:
                    print(f"[DRY] Select color {idx}: {px},{py}")
                else:
                    self.mouse.position = (px, py)
                    self.mouse.click(Button.left, 1)
                    time.sleep(max(0.002, self.move_delay))
                prev_palette_idx = idx

        print("=== DRAWING STARTED ===")

        try:
            # color cells first
            if self.color_mode and color_cells:
                for cx, cy, col in color_cells:
                    if self._stop_flag.is_set():
                        return
                    palette_idx = None
                    if palette:
                        nearest = utils.find_nearest_color(col, palette)
                        try:
                            palette_idx = palette.index(nearest)
                        except ValueError:
                            palette_idx = None
                    select_palette(palette_idx)
                    sx = int(top_left_x + off_x + cx)
                    sy = int(top_left_y + off_y + cy)
                    if self.dry_run:
                        print(f"[DRY] paint cell at {sx},{sy} with palette idx {palette_idx}")
                    else:
                        self.mouse.position = (sx, sy)
                        self.mouse.click(Button.left, 1)
                        time.sleep(max(0.002, MOVE_DELAY))

            # strokes
            # strokes: draw by clicking each point instead of press-drag (more compatible)
            for stroke in strokes_norm:
                if self._stop_flag.is_set():
                    print("Stopped mid-stroke.")
                    return
                if len(stroke) < 1:
                    continue
                # choose color for this stroke
                color = sample_img_color(stroke[0][0], stroke[0][1])
                nearest = utils.find_nearest_color(color, palette)
                palette_idx = palette.index(nearest) if nearest in palette else None
                select_palette(palette_idx)

                if self.dry_run:
                    # Print first few points for inspection
                    pts_preview = stroke[:8]
                    print(f"[DRY] stroke (clicks) sample: {[to_screen(p[0], p[1]) for p in pts_preview]}")
                    continue

                # click each point in the stroke
                for pt in stroke:
                    if self._stop_flag.is_set():
                        return
                    x, y = to_screen(pt[0], pt[1])
                    self.mouse.position = (x, y)
                    # tiny pause to ensure the canvas registers the move
                    time.sleep(max(0.0001, MOVE_DELAY * 0.5))
                    self.mouse.click(Button.left, 1)
                    # small gap between clicks
                    time.sleep(max(0.0002, MOVE_DELAY * 0.3))
                time.sleep(STROKE_GAP)

            # dots
            # for d in dots_norm:
            #     if self._stop_flag.is_set():
            #         print("Stopped during dots.")
            #         return
            #     color = sample_img_color(d[0], d[1])
            #     nearest = utils.find_nearest_color(color, palette)
            #     palette_idx = palette.index(nearest) if nearest in palette else None
            #     select_palette(palette_idx)
            #     x, y = to_screen(d[0], d[1])
            #     if self.dry_run:
            #         print(f"[DRY] dot at {x},{y}")
            #     else:
            #         self.mouse.position = (x, y)
            #         time.sleep(0.0002)
            #         self.mouse.press(Button.left)
            #         time.sleep(0.002)
            #         self.mouse.release(Button.left)
            #         time.sleep(DOT_DELAY)

            print("=== DRAWING COMPLETE ===")

        except Exception as e:
            import traceback
            print("Error during drawing:", e)
            traceback.print_exc()
        finally:
            try:
                self.mouse.release(Button.left)
            except Exception:
                pass

    def save_config(self, path: str):
        """Save current bbox and palette to a JSON file."""
        data = {
            "bbox": self.bbox,
            "palette_positions": self.palette_positions,
            "palette_colors": self.palette_colors,
            "speed": self.speed,
            "move_delay": self.move_delay,
            "color_mode": self.color_mode,
        }
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"Config saved to {path}")
        except Exception as e:
            print(f"Failed to save config: {e}")
