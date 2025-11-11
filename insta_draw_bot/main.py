"""Entry point for the Instagram drawing bot."""
import os
import time
import json

from .controller import Controller


def main():
    # Fixed settings (hardcoded)
    IMAGE_PATH = "D:\Download\maxresdefault.jpg"  # Set your image path here
    SPEED = 2.0  # Drawing speed multiplier
    COLOR_MODE = False  # Enable color painting
    DRY_RUN = False  # Set to True to test without moving mouse
    MOVE_DELAY = 0.001  # Delay after mouse actions

    image_path = IMAGE_PATH
    if not os.path.isfile(image_path):
        print("Image not found:", image_path)
        return

    # config file
    config_path = os.path.join(os.getcwd(), "insta_config.json")
    initial_bbox = None
    initial_palette_positions = None
    initial_palette_colors = None

    # load config if it exists and user agrees
    if os.path.isfile(config_path):
        ans = input(f"Found config at {config_path}. Use it? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                with open(config_path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                initial_bbox = data.get("bbox")
                initial_palette_positions = data.get("palette_positions")
                initial_palette_colors = data.get("palette_colors")
                print("Loaded bbox and palette from config.")
            except Exception as e:
                print(f"Failed to read config: {e}")

    ctrl = Controller(
        image_path,
        speed=SPEED,
        dry_run=DRY_RUN,
        move_delay=MOVE_DELAY,
        color_mode=COLOR_MODE,
        initial_bbox=initial_bbox,
        initial_palette_positions=initial_palette_positions,
        initial_palette_colors=initial_palette_colors,
    )
    ctrl.start_listeners()

    print("Listeners started. Follow README instructions to set bounding box and palette.")
    print("Press Ctrl+C to exit this program. Press Enter to start drawing and Esc to stop drawing.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Exiting")
        ans = input(f"Save current config to {config_path}? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                ctrl.save_config(config_path)
            except Exception as e:
                print(f"Failed to save config: {e}")


if __name__ == "__main__":
    main()
