"""Entry point for the Instagram drawing bot."""
import os
import time
import json

from .controller import Controller


def main():
    # Fixed settings (hardcoded)
    FILL_MODES = [
    "none", #0
    "dot", #1
    "stipple", #2
    "hatch-h", #3
    "hatch-v", #4
    "hatch-cross" ,#5
    "hatch-diagonal", #6
    "contour", #7
    "spiral", #8
    "wave"#9
    ]
    IMAGE_PATH = "image.png"  # Set your image path here
    SPEED = 2  # Drawing speed multiplier
    PEN_SIZE = 1.0  # Pen size in pixels (float, e.g., 0.5, 1.0, 2.5)
    DRY_RUN = False  # Set to True to test without moving mouse
    MOVE_DELAY = 0.001  # Delay after mouse actions
    FILL_MODE = FILL_MODES[7]  # Set fill mode here (none = no fill)
    STROKE_MODE = "drag"  # "drag" or "click"
    image_path = IMAGE_PATH
    if not os.path.isfile(image_path):
        print("Image not found:", image_path)
        return

    # separate config files: canvas (bbox) and palette (positions/colors)
    canvas_config_path = os.path.join(os.getcwd(), "insta_canvas.json")
    palette_config_path = os.path.join(os.getcwd(), "insta_palette.json")
    initial_bbox = None
    initial_palette_positions = None
    initial_palette_colors = None

    if os.path.isfile(canvas_config_path):
        ans = input(f"Found canvas config at {canvas_config_path}. Use it? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                with open(canvas_config_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                initial_bbox = data.get("bbox")
                print("Loaded bbox from canvas config.")
            except Exception as e:
                print(f"Failed to read canvas config: {e}")

    if os.path.isfile(palette_config_path):
        ans = input(f"Found palette config at {palette_config_path}. Use it? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                with open(palette_config_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                initial_palette_positions = data.get("palette_positions")
                initial_palette_colors = data.get("palette_colors")
                print("Loaded palette from palette config.")
            except Exception as e:
                print(f"Failed to read palette config: {e}")

    ctrl = Controller(
        image_path,
        speed=SPEED,
        dry_run=DRY_RUN,
        move_delay=MOVE_DELAY,
        pen_size=PEN_SIZE,
        initial_bbox=initial_bbox,
        initial_palette_positions=initial_palette_positions,
        initial_palette_colors=initial_palette_colors,
        fill_mode=FILL_MODE,
        stroke_mode=STROKE_MODE
    )
    ctrl.start_listeners()

    print("Listeners started. Follow README instructions to set bounding box and palette.")
    print("Press Ctrl+C to exit this program. Press Enter to start drawing and Esc to stop drawing.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting")
        ans = input(f"Save current canvas and palette configs? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                ctrl.save_canvas_config(canvas_config_path)
                ctrl.save_palette_config(palette_config_path)
            except Exception as e:
                print(f"Failed to save configs: {e}")


if __name__ == "__main__":
    main()
