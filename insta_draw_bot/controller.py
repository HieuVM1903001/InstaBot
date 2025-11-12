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
        pen_size: float = 1.0,
        fill_mode: str = "contour",
        stroke_mode: str = "drag",
        initial_bbox: Optional[Tuple[int, int, int, int]] = None,
        initial_palette_positions: Optional[List[Tuple[int, int]]] = None,
        initial_palette_colors: Optional[List[Tuple[int, int, int]]] = None,
    ):
        self.image_path = image_path
        self.speed = max(0.01, float(speed))
        self.dry_run = bool(dry_run)
        self.move_delay = max(0.0, float(move_delay))
        self.pen_size = max(0.1, float(pen_size))
        self.fill_mode = fill_mode or "none"
        self.stroke_mode = (stroke_mode or "drag").lower()

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
        print("Listeners started. 's' = canvas, 'f' = color, 'p' = draw, Esc = stop.")

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
        # start drawing on 'p' key
        if ch and ch.lower() == "p":
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

        fill_regions = []
        # generate fill paths for selected fill mode (skip if fill_mode == "none")
        if self.fill_mode != "none" and self.palette_colors:
            spacing = max(2, int(round(8.0 / max(0.1, self.speed))))
            fill_regions = image_processing.generate_fill_paths(img, self.palette_colors, mode=self.fill_mode, spacing=spacing)

        print(f"{len(strokes_norm)} strokes, {len(dots_norm)} dots")

        # compute total actions for progress bar (fill paths + stroke actions)
        total_actions = 0
        # fill paths count
        for region in fill_regions:
            total_actions += len(region.get('paths', []))
        # strokes count depends on stroke_mode
        for stroke in strokes_norm:
            total_actions += 1 if self.stroke_mode == "drag" else max(1, len(stroke))
        action_done = 0

        def to_screen(nx, ny):
            px = int(top_left_x + off_x + nx * img.size[0])
            py = int(top_left_y + off_y + ny * img.size[1])
            return px, py

        def sample_img_color(nx, ny):
            ix = int(min(max(0, nx * img.size[0]), img.size[0] - 1))
            iy = int(min(max(0, ny * img.size[1]), img.size[1] - 1))
            c = img.getpixel((ix, iy))
            return (c[0], c[1], c[2])

        def interpolate_points(points: List[Tuple[float, float]], pen_size: float) -> List[Tuple[float, float]]:
            """Interpolate points to create smooth lines based on pen size."""
            if len(points) < 2:
                return points
            # More interpolation points for smaller pen sizes to ensure smooth coverage
            interp_steps = max(1, int(self.pen_size / 2.0))
            result = [points[0]]
            for i in range(1, len(points)):
                x1, y1 = points[i - 1]
                x2, y2 = points[i]
                for step in range(1, interp_steps + 1):
                    t = step / (interp_steps + 1)
                    x = x1 + t * (x2 - x1)
                    y = y1 + t * (y2 - y1)
                    result.append((x, y))
                result.append(points[i])
            return result

        # Faster delays: reduced minimums for snappier movement
        MOVE_DELAY = max(0.001, 0.0005 / self.speed)
        STROKE_GAP = max(0.002, 0.0015 / self.speed)
        DOT_DELAY = max(0.0005, 0.0001 / self.speed)
        FILL_GAP = max(0.001, 0.0008 / self.speed)

        palette = list(self.palette_colors)
        prev_palette_idx = None

        def select_palette(idx):
            nonlocal prev_palette_idx
            if idx is not None and idx != prev_palette_idx and idx < len(self.palette_positions):
                px, py = self.palette_positions[idx]
                if self.dry_run:
                    print(f"[DRY] Select color {idx}: {px},{py}")
                else:
                    try:
                        # use pyautogui for fast clicks
                        pyautogui.click(px, py)
                    except Exception:
                        # fallback to pynput
                        self.mouse.position = (px, py)
                        self.mouse.click(Button.left, 1)
                    time.sleep(max(0.002, self.move_delay))
                prev_palette_idx = idx

        print("=== DRAWING STARTED ===")

        try:
            # Fill regions using the generated path families
            if fill_regions:
                for region in fill_regions:
                    if self._stop_flag.is_set():
                        return
                    color = region.get('color')
                    try:
                        palette_idx = palette.index(color)
                    except ValueError:
                        palette_idx = None
                    if palette:
                        if palette_idx is None and region.get('paths'):
                            # sample first point of first path to choose nearest palette entry
                            p0 = region['paths'][0][0]
                            col_sample = img.getpixel((p0[0], p0[1]))
                            nearest = utils.find_nearest_color(col_sample, palette, prev_idx=prev_palette_idx)
                            try:
                                palette_idx = palette.index(nearest)
                            except ValueError:
                                palette_idx = None
                    select_palette(palette_idx)
                    for path in region.get('paths', []):
                        if not path:
                            continue
                        pts_screen = [to_screen(p[0] / img.size[0], p[1] / img.size[1]) for p in path]
                        # interpolate for smooth lines
                        pts_smooth = interpolate_points(pts_screen, self.pen_size)
                        if self.dry_run:
                            print(f"[DRY] fill path sample: {pts_smooth[:6]}")
                            continue
                        try:
                            sx, sy = pts_smooth[0]
                            pyautogui.moveTo(int(sx), int(sy))
                            pyautogui.mouseDown(button='left')
                            for x, y in pts_smooth[1:]:
                                if self._stop_flag.is_set():
                                    pyautogui.mouseUp(button='left')
                                    return
                                import math

                                dx = int(x) - pyautogui.position().x
                                dy = int(y) - pyautogui.position().y
                                dist = math.hypot(dx, dy)
                                duration = max(MOVE_DELAY, dist / (800.0 * self.speed))
                                pyautogui.dragTo(int(x), int(y), duration=duration, button='left')
                            pyautogui.mouseUp(button='left')
                        except Exception:
                            for x, y in pts_smooth:
                                if self._stop_flag.is_set():
                                    return
                                self.mouse.position = (int(x), int(y))
                                self.mouse.click(Button.left, 1)
                                time.sleep(max(0.001, MOVE_DELAY * 0.3))
                        time.sleep(FILL_GAP)

            # strokes
            # choose stroke mode: 'drag' = continuous drag, 'click' = per-point clicks
            total_actions = 0
            for stroke in strokes_norm:
                # each stroke counts as 1 action if drag, or len(points) if click
                total_actions += 1 if self.stroke_mode == "drag" else max(1, len(stroke))
            # add fill paths count
            for region in fill_regions:
                for path in region.get('paths', []):
                    total_actions += 1

            action_done = 0

            for stroke in strokes_norm:
                if self._stop_flag.is_set():
                    print("Stopped mid-stroke.")
                    return
                if len(stroke) < 1:
                    continue
                # choose color for this stroke
                color = sample_img_color(stroke[0][0], stroke[0][1])
                nearest = utils.find_nearest_color(color, palette, prev_idx=prev_palette_idx)
                palette_idx = palette.index(nearest) if nearest in palette else None
                select_palette(palette_idx)

                pts_screen = [to_screen(p[0], p[1]) for p in stroke]
                # interpolate for smooth lines
                pts_smooth = interpolate_points(pts_screen, self.pen_size)
                
                if self.dry_run:
                    pts_preview = pts_smooth[:8]
                    print(f"[DRY] stroke (drag) sample: {pts_preview}")
                    continue

                if len(pts_smooth) == 1:
                    x, y = pts_smooth[0]
                    try:
                        pyautogui.click(int(x), int(y))
                    except Exception:
                        self.mouse.position = (int(x), int(y))
                        self.mouse.click(Button.left, 1)
                    time.sleep(STROKE_GAP)
                    continue

                # perform a continuous drag along the stroke with interpolated smooth points
                try:
                    sx, sy = pts_smooth[0]
                    pyautogui.moveTo(int(sx), int(sy))
                    pyautogui.mouseDown(button='left')
                    for x, y in pts_smooth[1:]:
                        if self._stop_flag.is_set():
                            pyautogui.mouseUp(button='left')
                            return
                        # compute duration proportional to distance
                        import math

                        dx = int(x) - pyautogui.position().x
                        dy = int(y) - pyautogui.position().y
                        dist = math.hypot(dx, dy)
                        duration = max(MOVE_DELAY, dist / (800.0 * self.speed))
                        pyautogui.dragTo(int(x), int(y), duration=duration, button='left')
                    pyautogui.mouseUp(button='left')
                except Exception:
                    # fallback to clicking smooth interpolated points
                    for x, y in pts_smooth:
                        if self._stop_flag.is_set():
                            return
                        self.mouse.position = (x, y)
                        self.mouse.click(Button.left, 1)
                        time.sleep(max(0.001, MOVE_DELAY * 0.3))
                # mark action complete(s)
                action_done += 1 if self.stroke_mode == "drag" else max(1, len(pts_screen))
                # print progress
                pct = int(100.0 * action_done / max(1, total_actions))
                bar = ('#' * (pct // 2)).ljust(50)
                print(f"Progress: |{bar}| {pct}% ({action_done}/{total_actions})", end='\r')
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
            # ensure progress bar line ends
            print()

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
        }
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"Config saved to {path}")
        except Exception as e:
            print(f"Failed to save config: {e}")

    def save_canvas_config(self, path: str):
        """Save only the canvas bbox to a JSON file."""
        data = {"bbox": self.bbox}
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"Canvas config saved to {path}")
        except Exception as e:
            print(f"Failed to save canvas config: {e}")

    def save_palette_config(self, path: str):
        """Save palette positions and colors to a JSON file."""
        data = {
            "palette_positions": self.palette_positions,
            "palette_colors": self.palette_colors,
        }
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            print(f"Palette config saved to {path}")
        except Exception as e:
            print(f"Failed to save palette config: {e}")
