"""Entry point for the Instagram drawing bot."""
import os
import time
import json

from .controller import Controller


# Available fill modes
FILL_MODES = [
    "none",           # 0 - No fill
    "dot",            # 1 - Regular grid of dots
    "stipple",        # 2 - Random dots (organic look)
    "hatch-h",        # 3 - Horizontal lines
    "hatch-v",        # 4 - Vertical lines
    "hatch-cross",    # 5 - Cross-hatching
    "hatch-diagonal", # 6 - Diagonal lines (both directions)
    "contour",        # 7 - Fill entire interior with horizontal lines + outlines
    "spiral",         # 8 - Rectangular spiral pattern
    "wave"            # 9 - Wavy horizontal lines
]

# Available stroke modes
STROKE_MODES = [
    "drag",  # Continuous drag - faster, smoother
    "click"  # Click each point - slower, more precise
]


def main():
    # ==================== CONFIGURATION ====================
    
    # Image settings
    IMAGE_PATH = "evolto.png"  # Path to your image
    
    # Speed settings (affects both fill and strokes)
    SPEED = 1.0  # Drawing speed multiplier (higher = faster)
                 # Speed affects: drag duration, spacing between fill lines
    
    # Fill mode settings
    FILL_MODE = FILL_MODES[7]  # Choose from FILL_MODES list (0-9)
    FILL_ONLY = False  # True = only draw fills, skip outlines
                       # False = draw fills + outlines
    
    # Stroke mode settings (applies to BOTH fills and strokes)
    STROKE_MODE = STROKE_MODES[1]  # "drag" or "click"
                                    # "drag" = continuous drag (faster, smoother)
                                    # "click" = click each point (slower, more precise)
    
    # Fine-tuning
    PEN_SIZE = 6.0      # Pen size in pixels (affects interpolation)
    DRY_RUN = False     # True = test without moving mouse
    MOVE_DELAY = 0.1  # Base delay after mouse actions
    
    # =======================================================
    
    image_path = IMAGE_PATH
    if not os.path.isfile(image_path):
        print(f"Image not found: {image_path}")
        print("Please update IMAGE_PATH in main.py")
        return

    # Separate config files: canvas (bbox) and palette (positions/colors)
    canvas_config_path = os.path.join(os.getcwd(), "insta_canvas.json")
    palette_config_path = os.path.join(os.getcwd(), "insta_palette.json")
    initial_bbox = None
    initial_palette_positions = None
    initial_palette_colors = None

    # Load canvas config
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

    # Load palette config
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

    # Display configuration
    print("\n" + "=" * 60)
    print("CONFIGURATION")
    print("=" * 60)
    print(f"Image:        {image_path}")
    print(f"Speed:        {SPEED}x")
    print(f"Fill Mode:    {FILL_MODE}")
    print(f"Fill Only:    {FILL_ONLY}")
    print(f"Stroke Mode:  {STROKE_MODE}")
    print(f"Pen Size:     {PEN_SIZE}px")
    print(f"Dry Run:      {DRY_RUN}")
    print("=" * 60)
    
    if FILL_MODE == "none" and FILL_ONLY:
        print("\nWARNING: FILL_ONLY is True but FILL_MODE is 'none'.")
        print("Nothing will be drawn! Set FILL_MODE to a valid mode or FILL_ONLY to False.")
        return

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
        stroke_mode=STROKE_MODE,
        fill_only=FILL_ONLY,
    )
    ctrl.start_listeners()

    print("\n" + "=" * 60)
    print("CONTROLS")
    print("=" * 60)
    print("Press 's' to set canvas bounds (click top-left, then bottom-right)")
    print("Press 'f' to sample palette colors (click each color)")
    print("Press 'p' to start drawing")
    print("Press 'e' to stop drawing")
    print("Press Ctrl+C to exit program")
    print("=" * 60 + "\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        ans = input(f"Save current canvas and palette configs? [Y/n]: ")
        if ans.strip().lower() in ("y", "", "yes"):
            try:
                ctrl.save_canvas_config(canvas_config_path)
                ctrl.save_palette_config(palette_config_path)
            except Exception as e:
                print(f"Failed to save configs: {e}")


if __name__ == "__main__":
    main()