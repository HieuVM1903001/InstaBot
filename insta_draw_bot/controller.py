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
        fill_only: bool = False,
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
        self.fill_only = bool(fill_only)

        self.bbox = None
        self._waiting_bbox = False
        self._waiting_color_click = False
        self.palette_positions = []
        self.palette_colors = []
        self._stop_flag = threading.Event()
        self._draw_thread = None

        # Progress tracking
        self.total_operations = 0
        self.completed_operations = 0

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
        
        # Apply initial config if provided
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
        print("Listeners started. 's' = canvas, 'f' = color, 'p' = draw, 'e' = stop.")

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
        if ch and ch.lower() == "e":
            print("Stopping drawing... Press 'r' to resume.")
            self._stop_flag.set()
            return
        if ch and ch.lower() == "r":
            if self._draw_thread is not None and self._draw_thread.is_alive():
                print("Resuming drawing...")
                self._stop_flag.clear()
            return

    def _update_progress(self, message: str = ""):
        """Update and display progress bar."""
        if self.total_operations == 0:
            return
        
        progress = (self.completed_operations / self.total_operations) * 100
        bar_length = 50
        filled = int(bar_length * self.completed_operations / self.total_operations)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        print(f'\r[{bar}] {progress:.1f}% {message} ({self.completed_operations}/{self.total_operations})', end='', flush=True)
        
        if self.completed_operations >= self.total_operations:
            print()  # New line when complete

    def _draw_path(self, points: List[Tuple[int, int]], delay_mult: float = 1.0):
        """Draw a path using the current stroke mode."""
        if not points or self._stop_flag.is_set():
            return
        
        if len(points) == 1:
            # Single point - just click
            x, y = points[0]
            try:
                pyautogui.click(int(x), int(y))
            except Exception:
                self.mouse.position = (int(x), int(y))
                self.mouse.click(Button.left, 1)
            time.sleep(max(0.001, self.move_delay * delay_mult))
            return
        
        # Multiple points - use stroke mode
        if self.stroke_mode == "drag":
            # Drag mode: continuous drag
            try:
                sx, sy = points[0]
                pyautogui.moveTo(int(sx), int(sy))
                pyautogui.mouseDown(button='left')
                
                for x, y in points[1:]:
                    if self._stop_flag.is_set():
                        pyautogui.mouseUp(button='left')
                        return
                    
                    # Calculate duration based on distance and speed
                    dx = int(x) - pyautogui.position().x
                    dy = int(y) - pyautogui.position().y
                    dist = (dx*dx + dy*dy) ** 0.5
                    
                    # Speed-aware duration: pixels per second = 800 * speed
                    duration = max(self.move_delay, dist / (800.0 * self.speed))
                    pyautogui.dragTo(int(x), int(y), duration=duration, button='left')
                
                pyautogui.mouseUp(button='left')
            except Exception:
                # Fallback to click mode
                for x, y in points:
                    if self._stop_flag.is_set():
                        return
                    self.mouse.position = (int(x), int(y))
                    self.mouse.click(Button.left, 1)
                    time.sleep(max(0.001, self.move_delay * 0.3 * delay_mult))
        else:
            # Click mode: click each point
            for x, y in points:
                if self._stop_flag.is_set():
                    return
                try:
                    pyautogui.click(int(x), int(y))
                except Exception:
                    self.mouse.position = (int(x), int(y))
                    self.mouse.click(Button.left, 1)
                time.sleep(max(0.001, self.move_delay * 0.3 * delay_mult))

    def _run_drawing(self):
        """Main drawing loop with progress tracking and fill support."""
        if not self.bbox:
            print("No bounding box defined!")
            return

        x1, y1, x2, y2 = self.bbox
        w, h = abs(x2 - x1), abs(y2 - y1)
        top_left_x, top_left_y = min(x1, x2), min(y1, y2)

        print(f"Preparing image region {w}x{h} at ({top_left_x},{top_left_y})")
        img, offset = image_processing.load_and_fit_image(self.image_path, w, h)
        off_x, off_y = offset

        # Get strokes for outlines (only if not fill_only)
        strokes_norm = []
        if not self.fill_only:
            strokes_px = image_processing.edges_to_strokes(img)
            strokes_norm = image_processing.map_strokes_to_normalized(strokes_px, img.size[0], img.size[1])

        # Get fill paths if fill mode is enabled
        fill_data = []
        if self.fill_mode and self.fill_mode != "none" and self.palette_colors:
            print(f"Generating {self.fill_mode} fill patterns...")
            # Speed-aware spacing: faster speed = larger spacing
            spacing = max(2, int(8.0 / max(0.5, self.speed)))
            fill_data = image_processing.generate_fill_paths(
                img, 
                self.palette_colors,
                mode=self.fill_mode,
                spacing=spacing,
                min_area=50
            )
            print(f"Generated {len(fill_data)} color regions with fill patterns")

        # Calculate total operations for progress tracking
        self.total_operations = 0
        self.completed_operations = 0
        
        # Count fill path points
        for region in fill_data:
            for path in region['paths']:
                if self.stroke_mode == "drag":
                    self.total_operations += 1  # One drag per path
                else:
                    self.total_operations += len(path)  # One click per point
        
        # Count stroke points
        for stroke in strokes_norm:
            if self.stroke_mode == "drag":
                self.total_operations += 1  # One drag per stroke
            else:
                self.total_operations += len(stroke)  # One click per point

        print(f"Total operations: {self.total_operations}")
        print(f"Mode: {'Fill only' if self.fill_only else 'Fill + Strokes'}, Stroke mode: {self.stroke_mode}")

        def to_screen(nx, ny):
            px = int(top_left_x + off_x + nx * img.size[0])
            py = int(top_left_y + off_y + ny * img.size[1])
            return px, py

        def to_screen_pixel(px, py):
            """Convert pixel coordinates to screen coordinates."""
            sx = int(top_left_x + off_x + px)
            sy = int(top_left_y + off_y + py)
            return sx, sy

        palette = list(self.palette_colors)
        prev_palette_idx = None

        def select_palette(idx):
            nonlocal prev_palette_idx
            if self._stop_flag.is_set():
                return False
            if idx is not None and idx != prev_palette_idx and idx < len(self.palette_positions):
                px, py = self.palette_positions[idx]
                if self.dry_run:
                    print(f"[DRY] Select color {idx}: {px},{py}")
                else:
                    try:
                        pyautogui.click(px, py)
                    except Exception:
                        self.mouse.position = (px, py)
                        self.mouse.click(Button.left, 1)
                    time.sleep(max(0.002, self.move_delay))
                prev_palette_idx = idx
            return True

        print("\n=== DRAWING STARTED ===")

        try:
            # Draw fills first (background)
            if fill_data:
                print("\nDrawing fill patterns...")
                for region in fill_data:
                    if self._stop_flag.is_set():
                        print("\nStopped during fill.")
                        return
                    
                    color = region['color']
                    paths = region['paths']
                    
                    # Find palette index for this color
                    palette_idx = None
                    if palette:
                        try:
                            palette_idx = palette.index(color)
                        except ValueError:
                            # Find nearest color
                            nearest = utils.find_nearest_color(color, palette, prev_palette_idx)
                            try:
                                palette_idx = palette.index(nearest)
                            except ValueError:
                                palette_idx = None
                    
                    if not select_palette(palette_idx):
                        return
                    
                    # Draw each path in this region
                    for path in paths:
                        if self._stop_flag.is_set():
                            return
                        
                        if len(path) == 0:
                            continue
                        
                        if self.dry_run:
                            print(f"[DRY] Fill path with {len(path)} points")
                            if self.stroke_mode == "drag":
                                self.completed_operations += 1
                            else:
                                self.completed_operations += len(path)
                            continue
                        
                        # Convert pixel coordinates to screen coordinates
                        screen_points = [to_screen_pixel(pt[0], pt[1]) for pt in path]
                        
                        # Draw using current stroke mode
                        self._draw_path(screen_points, delay_mult=0.8)
                        
                        # Update progress
                        if self.stroke_mode == "drag":
                            self.completed_operations += 1
                        else:
                            self.completed_operations += len(path)
                        
                        if self.completed_operations % 10 == 0:
                            self._update_progress("- Filling")

            # Draw outlines/strokes on top (skip if fill_only)
            if strokes_norm and not self.fill_only:
                print("\nDrawing outlines...")
                for stroke_idx, stroke in enumerate(strokes_norm):
                    if self._stop_flag.is_set():
                        print("\nStopped mid-stroke.")
                        return
                    
                    if len(stroke) < 1:
                        continue
                    
                    # Sample color from first point of stroke
                    img_x = int(stroke[0][0] * img.size[0])
                    img_y = int(stroke[0][1] * img.size[1])
                    img_x = max(0, min(img.size[0] - 1, img_x))
                    img_y = max(0, min(img.size[1] - 1, img_y))
                    
                    try:
                        c = img.getpixel((img_x, img_y))
                        color = (c[0], c[1], c[2])
                    except:
                        color = (0, 0, 0)
                    
                    nearest = utils.find_nearest_color(color, palette, prev_palette_idx)
                    palette_idx = palette.index(nearest) if nearest in palette else None
                    
                    if not select_palette(palette_idx):
                        return

                    if self.dry_run:
                        print(f"[DRY] stroke {stroke_idx}: {len(stroke)} points")
                        if self.stroke_mode == "drag":
                            self.completed_operations += 1
                        else:
                            self.completed_operations += len(stroke)
                        continue

                    # Convert normalized coordinates to screen coordinates
                    screen_points = [to_screen(pt[0], pt[1]) for pt in stroke]
                    
                    # Draw using current stroke mode
                    self._draw_path(screen_points, delay_mult=1.0)
                    
                    # Update progress
                    if self.stroke_mode == "drag":
                        self.completed_operations += 1
                    else:
                        self.completed_operations += len(stroke)
                    
                    if self.completed_operations % 10 == 0:
                        self._update_progress("- Drawing strokes")

            self._update_progress("- Complete!")
            print("\n=== DRAWING COMPLETE ===")

        except Exception as e:
            import traceback
            print(f"\nError during drawing: {e}")
            traceback.print_exc()
        finally:
            try:
                self.mouse.release(Button.left)
            except Exception:
                pass
            try:
                pyautogui.mouseUp(button='left')
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
            "fill_mode": self.fill_mode,
            "stroke_mode": self.stroke_mode,
            "fill_only": self.fill_only,
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