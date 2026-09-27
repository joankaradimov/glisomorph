"""How much detail beyond the originals' pixels can be recovered? A benchmark with a real answer key.

    python -m poc.superres --mpq PATH/TO/DIABDAT.MPQ --preset warrior --scale 2

There's no high-resolution Diablo sprite to compare with, so the benchmark makes the originals the
answer key. Each direction is shrunk by the scale (its pixels averaged in blocks, and snapped to the
palette, as a renderer with antialiasing would draw it smaller), and each method has to bring the
small sprites back to full size. Shrinking by 2 and enlarging by 2 is the same problem as enlarging the
originals by 2, but here the detail to recover is the artist's. (A first version used a supersampled
fit as the truth, rendered finer; its detail below a pixel was noise that the fit was free to invent,
which no method could, or should, recover.)

Two tests, scored against the originals (without their baked shadows):
- known directions: all 8 small sprites in, all 8 back at full size;
- a hidden direction: 7 small sprites in, the 8th made at full size.

The methods see only the small sprites and the camera:
- upscaled: no new information. The small sprite's pixels repeated; a hidden direction is copied at
  the small size first.
- fit: a Gaussian fit of the small sprites, rendered at full size: its own colors, or copied pixels
  (the small sprites' palette indices at each pixel's surface point, as evaluate.py copies them).
- supersampled fit: the same, fitted supersampled by the scale, so that it can hold detail finer
  than a small pixel, as far as the 8 small sprites pin it down.
What a method gains over "upscaled" is detail it recovered.

Outputs, in out/superres-<preset>-<scale>x/: metrics.json and compare.png (the known direction S and the
hidden direction: the original, then each method).
"""

import argparse
import dataclasses
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image, ImageDraw

from poc import fit
from poc.evaluate import Renderer, quantize, score
from poc.field import VoxelField, allowed_masks, camera_basis, carve, pixel_rays
from poc.gaussians import DISTANCE, GaussianField, intrinsics, viewmat
from poc.reproject import Warp
from poc.scene import Scene, masks_for
from poc.views import PRESETS, View, load_views

CANDIDATES = [0] + list(range(128, 255))  # the indices sprites use


def shrink(indices, mask, palette, candidates, scale: int):
    """A sprite drawn `scale` times smaller: its pixels (where mask) averaged in scale x scale blocks,
    solid where they cover at least half of the block, and snapped to the palette."""
    color = palette[indices.clamp(min=0)] * mask[..., None]
    down = F.avg_pool2d(torch.cat([color, mask[..., None]], -1).permute(2, 0, 1)[None], scale)[0].permute(1, 2, 0)
    return quantize(down[..., :3], down[..., 3], palette, candidates)


def render_at(field, shape, pivot, offset, basis, scale: int):
    """A field at `scale` pixels per world unit: premultiplied colors (H, W, 3), opacity (H, W) and
    expected depth (H, W)."""
    right, up, forward = basis
    h, w = shape
    K = intrinsics(pivot, offset, right.device, scale)
    colors, alpha, _ = field.rasterize(viewmat(right, up, forward)[None], K[None], w * scale, h * scale)
    return colors[0, ..., :3], alpha[0, ..., 0], colors[0, ..., 3] - DISTANCE


def fit_views(views, masks, palette, yaws, elevation, offset, iters: int, supersample: int, device):
    """A Gaussian fit of views with a known camera, started from their visual hull."""
    width = max(v.shape[1] for v in views)
    radius = width / 2 + 4
    top = max(v.pivot[1] for v in views)
    bottom = max(v.shape[0] - v.pivot[1] for v in views)
    theta = math.radians(40)
    box_min = [-radius, -(bottom + radius * math.sin(theta)) / math.cos(theta), -radius]
    box_max = [radius, (top + radius * math.sin(theta)) / math.cos(theta), radius]
    grid = VoxelField(box_min, box_max, 1.0, device)
    right, up, forward = camera_basis(yaws, elevation)
    inside = carve(grid, allowed_masks(masks), views, right, up, offset)
    field = GaussianField.from_points(grid.voxel_centers()[inside], 1.0)
    targets = torch.stack([palette[torch.as_tensor(v.indices, device=device).long().clamp(min=0)] for v in views])
    field.fit(torch.stack([viewmat(right[i], up[i], forward[i]) for i in range(len(views))]),
              torch.stack([intrinsics(v.pivot, offset, device) for v in views]), targets,
              torch.stack([m == 1 for m in masks]), iters=iters, supersample=supersample)
    return field


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", default="warrior")
    ap.add_argument("--frame", type=int, default=None)
    ap.add_argument("--scale", type=int, default=2)
    ap.add_argument("--hide", type=int, default=1, help="the direction hidden in the second test")
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    device = torch.device("cuda")
    t_start = time.time()
    s = args.scale
    out_dir = Path(args.out) / ("superres-%s-%dx" % (args.preset, s))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. The originals, and their camera (calibrated by fit.py on the originals themselves).
    preset = PRESETS[args.preset]
    if args.frame is not None:
        preset = dataclasses.replace(preset, frame=args.frame)
    views, palette_np = load_views(args.mpq, preset)
    palette = torch.as_tensor(palette_np, dtype=torch.float32, device=device)
    candidates = torch.tensor(CANDIDATES, device=device)
    argv = ["--mpq", args.mpq, "--preset", args.preset, "--split", "all", "--model", "gaussians", "--iters", "1",
            "--tag", "camera", "--out", args.out, "--no-evaluate"]
    if args.frame is not None:
        argv += ["--frame", str(args.frame)]
    folder = Path(args.out) / fit.run_name(args.preset, "all", tag="camera", model="gaussians")
    camera = Scene.load(folder / "scene.pt", args.mpq) if (folder / "scene.pt").exists() else fit.main(argv)[0]
    masks = masks_for(views, preset.shadows, device)
    truth = [torch.where(m == 1, torch.as_tensor(v.indices, device=device).long(), torch.full_like(m, -1))
             for v, m in zip(views, masks)]  # the answer keys: the originals without their baked shadows

    # 2. The small sprites, in their own units: one small pixel per world unit.
    small = []
    for v, t in zip(views, truth):
        idx = shrink(t, (t >= 0).float(), palette, candidates, s)
        small.append(View(yaw=v.yaw, indices=idx.cpu().numpy().astype(np.int16), pivot=(v.pivot[0] / s, v.pivot[1] / s)))
    offset = (camera.offset[0] / s, camera.offset[1] / s)
    yaws, elevation = camera.yaws, camera.elevation
    small_masks = [(torch.as_tensor(v.indices, device=device) >= 0).long() for v in small]

    def basis(i):
        return tuple(x[i] for x in camera.basis(yaws))

    def model(train, supersample):
        t0 = time.time()
        field = fit_views([small[i] for i in train], [small_masks[i] for i in train], palette, yaws[train],
                          elevation, offset, args.iters, supersample, device)
        print("fitted %d small sprites, %dx supersampled (%.0fs)" % (len(train), supersample, time.time() - t0))
        config = dict(camera.config, supersample=1, train_views=train, test_views=[])
        scene = Scene(field=field, views=small, masks=small_masks, palette=palette, yaws=yaws, elevation=elevation,
                      offset=offset, samples=camera.samples, config=config)
        return scene, Renderer(scene, Warp())

    def outputs(scene, renderer, i, scale):
        """The model's own colors, and copied pixels, for direction i at the scale."""
        with torch.no_grad():
            r, u, f = basis(i)
            rgb, alpha, depth = render_at(scene.field, small[i].shape, small[i].pivot, offset, (r, u, f), scale)
            own = quantize(rgb, alpha, palette, candidates)
            target = {"origins": pixel_rays(*small[i].shape, small[i].pivot, offset, r, u, f, supersample=scale)[0],
                      "depth": depth, "solid": alpha >= 0.5, "yaw": float(yaws[i]), "right": r, "up": u, "forward": f}
            copied, _ = renderer.colored({"target": target, "pred": own, "alpha": alpha, "normal": None})
        return own, copied

    def upscale(indices):
        return indices.repeat_interleave(s, 0).repeat_interleave(s, 1)

    # 3. Both tests: all 8 known, and one hidden.
    everything = list(range(len(views)))
    seen = [i for i in everything if i != args.hide]
    tests = {"known directions": (everything, everything), "hidden direction": (seen, [args.hide])}
    results, pictures = {}, {}
    for test, (train, targets) in tests.items():
        plain, sharp = model(train, 1), model(train, s)
        rows = {}
        for i in targets:
            if i in train:
                base = upscale(torch.as_tensor(small[i].indices, device=device).long())
            else:
                base = upscale(outputs(*plain, i, 1)[1])
            cells = {"upscaled": base}
            cells["fit, own colors"], cells["fit, copied"] = outputs(*plain, i, s)
            cells["supersampled fit, own colors"], cells["supersampled fit, copied"] = outputs(*sharp, i, s)
            for name, cell in cells.items():
                rows.setdefault(name, []).append(score(cell, truth[i], palette))
            if i in (0, args.hide) and (test == "hidden direction" or i == 0):
                pictures[test] = [("original", truth[i])] + list(cells.items())
        results[test] = {name: {m: float(np.mean([r[m] for r in v])) for m in v[0]} for name, v in rows.items()}
        print("%s:" % test)
        for name, row in results[test].items():
            print("  %-30s IoU %.3f  exact %5.1f%%  same ramp %5.1f%%  RGB %5.2f  blurred %5.2f" % (
                name, row["silhouette_iou"], 100 * row["exact_index"], 100 * row["same_ramp"], row["rgb_error"],
                row["blurred_rgb_error"]))
    (out_dir / "metrics.json").write_text(json.dumps({"preset": args.preset, "frame": preset.frame, "scale": s,
                                                      "hidden": args.hide, "results": results,
                                                      "seconds": time.time() - t_start}, indent=2))

    # 4. A picture: the known direction S and the hidden direction, the original and each method.
    pal = (palette.cpu().numpy() * 255).round().astype(np.uint8)
    rows = []
    for test in tests:
        tiles = []
        for label, cell in pictures[test]:
            c = cell.cpu().numpy()
            img = np.full(c.shape + (3,), 48, np.uint8)
            img[c >= 0] = pal[c[c >= 0]]
            tiles.append((label, img))
        rows.append((test, tiles))
    th, tw = rows[0][1][0][1].shape[:2]
    zoom = 3
    canvas = Image.new("RGB", (len(rows[0][1]) * (tw * zoom + 6), len(rows) * (th * zoom + 20)), (20, 20, 20))
    draw = ImageDraw.Draw(canvas)
    for j, (test, tiles) in enumerate(rows):
        for i, (label, img) in enumerate(tiles):
            x, y = i * (tw * zoom + 6), j * (th * zoom + 20)
            canvas.paste(Image.fromarray(img).resize((tw * zoom, th * zoom), Image.NEAREST), (x, y + 20))
            draw.text((x + 4, y + 4), "%s: %s" % (test, label), fill=(230, 230, 230))
    canvas.save(out_dir / "compare.png")
    print("wrote", out_dir, "(%.0fs)" % (time.time() - t_start))


if __name__ == "__main__":
    main()
