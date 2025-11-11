# Instagram Drawing Bot

Small Python tool that converts an image into simple drawing primitives (lines/strokes/dots) and automates drawing them in a browser-based canvas (for example Instagram's drawing tool).

WARNING: This tool will move your mouse and send clicks. Keep an eye on the system when running it and be prepared to press Esc to stop.

Features implemented in this scaffold:
- Specify a drawing canvas by pressing Space then clicking top-left and bottom-right on the canvas.
- Press `f` then click in the canvas to register a color location; the tool samples the screen pixel at that point and stores that color.
- Load an image and produce simple primitives (edges -> lines; grid -> dots).
- Press Enter to start automated drawing. Press Esc to stop.

This is a scaffold — image-to-stroke algorithms are basic and intended as a starting point.

Requirements
- Python 3.8+
- See `requirements.txt` for required packages.

Quick start
1. Create a virtualenv and install requirements:

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt
```

2. Start the tool pointing to an image:

```powershell
python -m insta_draw_bot.main --image path\to\image.jpg
```

3. In the browser/canvas:
- Press Space, click top-left then bottom-right to set canvas bounds.
- Press `f`, then click to register colors (as many as you need). These are the palette colors the bot will use.
- Press Enter to start the drawing. Press Esc to stop at any time.

Notes and next steps
- Improve stroke extraction (vectorization, ordering, speed).
- Add GUI for color palette mapping and stroke smoothing.
- Add retries and more robust keyboard handling for different environments.

Enjoy and use carefully.
