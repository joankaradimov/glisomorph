"""Fit every frame of an animation, and render it in 16 directions.

    python -m poc.animate --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk

Each frame is fitted on all 8 directions (fit.py), unless its fit is already saved. Frame 0
calibrates the camera and the other frames share it, so the new directions don't wobble (see
Motion in README.md). The new directions' shadows are made as the originals' were (shadow.py): each
hangs from its direction's ground row, found in frame 0.

Outputs, in out/<preset>-16/:
- sheet.png: every frame in 16 directions, as the game would store them. There is a row per
  direction, from S clockwise with the originals and the new ones alternating, and a column per
  frame. Frames keep their size and anchor. The image is in the palette, with index 255 transparent.
- directions.gif: the 16 directions animated, enlarged, the new ones marked in blue, at the game's
  speed for walks and attacks (a frame per 50 ms tick).
"""

import argparse
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont

from poc import fit
from poc.evaluate import Renderer, add_warp_arguments, warp_from_args, with_shadow
from poc.scene import Scene
from poc.shadow import lowest_row
from poc.views import PRESETS, frame_count

DIRECTIONS = ["S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW", "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE"]
TRANSPARENT = 255  # sprites never use it
TICK_MS = 50  # the game's tick: walks and attacks show a frame per tick (standing, a frame per 4)
BACKGROUND = (40, 40, 44)


def render_frame(scene: Scene, renderer: Renderer, grounds=None):
    """The 16 directions of one frame, from S clockwise: the originals, with a new one after each; and
    the new ones' ground rows. Their shadows hang from the given ground rows, or, in the first frame
    (None), from their own lowest rows."""
    out, rows = [], []
    for i, v in enumerate(scene.views):
        out.append(v.indices.astype(np.int64))
        r = renderer.render(v.shape, v.pivot, scene.sign * (i * 360 / len(scene.views) + 180 / len(scene.views)))
        colors = renderer.best_colors(r)
        rows.append(lowest_row(colors >= 0) if grounds is None else grounds[i])
        out.append(with_shadow(colors, renderer.shadow(colors >= 0, rows[-1])).cpu().numpy())
    return out, rows


def write_sheet(frames: list[list[np.ndarray]], palette: np.ndarray, path: Path) -> None:
    h, w = frames[0][0].shape
    sheet = np.full((16 * h, len(frames) * w), TRANSPARENT, dtype=np.uint8)
    for k, directions in enumerate(frames):
        for d, img in enumerate(directions):
            sheet[d * h:(d + 1) * h, k * w:(k + 1) * w] = np.where(img < 0, TRANSPARENT, img)
    image = Image.frombytes("P", (sheet.shape[1], sheet.shape[0]), sheet.tobytes())
    image.putpalette(palette.flatten().tolist())
    image.save(path, transparency=TRANSPARENT)


def write_gif(frames: list[list[np.ndarray]], palette: np.ndarray, path: Path, scale: int = 2,
              duration=TICK_MS, columns: int = 8) -> None:
    """All directions of each frame, side by side in rows of `columns`, one GIF frame each, shown for
    `duration` ms (or a list of durations, one per frame)."""
    solid = np.any([img >= 0 for directions in frames for img in directions], axis=0)
    ys, xs = np.nonzero(solid)
    y0, y1, x0, x1 = max(ys.min() - 2, 0), ys.max() + 3, max(xs.min() - 2, 0), xs.max() + 3
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    pictures = []
    for directions in frames:
        tiles = []
        for d, img in enumerate(directions):
            crop = img[y0:y1, x0:x1]
            rgb = np.empty(crop.shape + (3,), dtype=np.uint8)
            rgb[:] = BACKGROUND
            rgb[crop >= 0] = palette[crop[crop >= 0]]
            big = Image.fromarray(rgb).resize((rgb.shape[1] * scale, rgb.shape[0] * scale), Image.NEAREST)
            tile = Image.new("RGB", (big.width, big.height + 24), BACKGROUND)
            tile.paste(big, (0, 24))
            draw = ImageDraw.Draw(tile)
            draw.rectangle([0, 0, big.width, 4], fill=(70, 120, 230) if d % 2 else (70, 170, 70))
            draw.text((5, 6), DIRECTIONS[d], fill=(230, 230, 230), font=font)
            tiles.append(tile)
        tw, th = tiles[0].size
        rows = -(-len(tiles) // columns)
        picture = Image.new("RGB", (columns * (tw + 4) - 4, rows * (th + 4) - 4), (15, 15, 18))
        for n, tile in enumerate(tiles):
            picture.paste(tile, ((n % columns) * (tw + 4), (n // columns) * (th + 4)))
        pictures.append(picture)
    pictures[0].save(path, save_all=True, append_images=pictures[1:], duration=duration, loop=0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--frames", type=int, default=None, help="only the first N frames (default: all)")
    ap.add_argument("--lighting", default="phong", choices=["none", "lambert", "phong"])
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--out", default="out")
    add_warp_arguments(ap)
    args = ap.parse_args()

    preset = PRESETS[args.preset]
    count = frame_count(args.mpq, preset)
    if args.frames:
        count = min(count, args.frames)
    folders = []
    for k in range(count):
        folder = Path(args.out) / fit.run_name(args.preset, "all", args.lighting, tag="f%d" % k)
        if not (folder / "scene.pt").exists():
            print("frame %d of %d: fitting" % (k, count))
            argv = ["--mpq", args.mpq, "--preset", args.preset, "--split", "all", "--frame", str(k),
                    "--lighting", args.lighting, "--iters", str(args.iters), "--out", args.out,
                    "--tag", "f%d" % k, "--no-evaluate"]
            if k:
                argv += ["--camera", str(folders[0])]
            fit.main(argv)
        folders.append(folder)

    warp = warp_from_args(args)
    frames, grounds, palette = [], None, None
    with torch.no_grad():
        for k, folder in enumerate(folders):
            scene = Scene.load(folder / "scene.pt", args.mpq)
            if len(scene.views) != 8:
                raise SystemExit("%s has %d directions; animate.py makes 16 out of 8" % (args.preset, len(scene.views)))
            frame, grounds = render_frame(scene, Renderer(scene, warp), grounds)
            frames.append(frame)
            if palette is None:
                palette = (scene.palette.cpu().numpy() * 255).round().astype(np.uint8)
            print("frame %d of %d: rendered" % (k, count))
    out_dir = Path(args.out) / ("%s-16" % args.preset)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_sheet(frames, palette, out_dir / "sheet.png")
    write_gif(frames, palette, out_dir / "directions.gif")
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
