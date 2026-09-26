"""Render a fitted scene: score the held-out directions and draw the pictures.

    python -m poc.evaluate out/warrior-holdout1-h0 --mpq PATH/TO/DIABDAT.MPQ --warp plain --out out/plain

fit.py runs this after fitting. Run by hand, it evaluates a saved fit again, for example with other
reprojection settings (`--warp`, see reproject.py), without fitting again.

Outputs: metrics.json, views.npz (truth, field colors, reprojected and relit colors per view),
compare.png, in_between.png and turntable.gif.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

from diablo1.palette import ramp_of
from poc.reproject import Warp, fill, neighbour, reproject, source_depth
from poc.scene import Scene

WARPS = {"coherent": Warp(), "plain": Warp.plain()}
# Warp settings that can be changed from the command line, over the chosen warp's.
OVERRIDES = {
    "depth": {"choices": ["median", "expected"], "help": "which depth reprojection uses"},
    "smooth": {"type": int, "help": "radius of the plane fits that smooth depth (0 = off)"},
    "coherence": {"type": float, "help": "cost of switching direction between neighbours inside a surface"},
    "shading": {"type": float, "help": "cost of a direction that shades a surface differently"},
    "fill": {"type": int, "help": "how far pixels that no direction sees take a neighbour's color"},
}


def add_warp_arguments(ap: argparse.ArgumentParser) -> None:
    ap.add_argument("--warp", default="coherent", choices=sorted(WARPS),
                    help="how new views fetch colors from the known directions: 'plain' fetches each pixel "
                         "on its own; 'coherent' smooths depth and keeps regions to one direction")
    for name, options in OVERRIDES.items():
        ap.add_argument("--" + name, default=None, **{**options, "help": "override: " + options["help"]})


def warp_from_args(args) -> Warp:
    changes = {k: getattr(args, k) for k in OVERRIDES if getattr(args, k) is not None}
    return Warp(**{**WARPS[args.warp].__dict__, **changes})


def quantize(rgb, alpha, palette, candidates):
    """Palette index per pixel (-1 where transparent) for premultiplied rgb (H, W, 3)."""
    color = rgb / alpha.clamp(min=1e-6)[..., None]
    pal = palette[candidates]                                            # (C, 3)
    dist = ((color[..., None, :] - pal) ** 2).sum(-1)                   # (H, W, C)
    idx = candidates[dist.argmin(-1)]
    return torch.where(alpha >= 0.5, idx, torch.full_like(idx, -1))


def blurred(indices, palette, sigma: float = 1.0):
    """Colors (H, W, 3) blurred by a Gaussian within the silhouette."""
    solid = (indices >= 0).float()
    layers = torch.cat([(palette[indices.clamp(min=0)] * solid[..., None]).permute(2, 0, 1), solid[None]])
    r = 2
    g = torch.exp(-torch.arange(-r, r + 1, device=indices.device, dtype=torch.float32) ** 2 / (2 * sigma ** 2))
    kernel = (g[:, None] * g[None, :] / g.sum() ** 2).expand(4, 1, -1, -1)
    out = F.conv2d(F.pad(layers[None], (r,) * 4), kernel, groups=4)[0]
    return (out[:3] / out[3:].clamp(min=1e-6)).permute(1, 2, 0)


def stray_pixels(indices, palette, threshold: float = 20.0) -> float:
    """Speckle: the share of pixels within the silhouette (all four neighbours solid) whose color differs
    from every neighbour's by more than `threshold` (mean absolute RGB difference, 0-255)."""
    solid = indices >= 0
    rgb = (palette[indices.clamp(min=0)] * 255).permute(2, 0, 1)
    interior = solid.clone()
    stray = solid.clone()
    for d in range(4):
        interior &= neighbour(solid, d, False)
        stray &= (rgb - neighbour(rgb, d)).abs().mean(0) > threshold
    return float((stray & interior).sum() / interior.sum().clamp(min=1))


def score(pred, gt, palette):
    """Metrics comparing predicted and true palette indices (-1 = transparent)."""
    p = pred >= 0
    g = gt >= 0
    both = p & g
    union = p | g
    same = both & (pred == gt)
    ramp_ids = torch.tensor([ramp_of(i) for i in range(256)], device=pred.device)
    same_ramp = both & (ramp_ids[pred.clamp(min=0)] == ramp_ids[gt.clamp(min=0)])
    rgb_err = (palette[pred[both]] - palette[gt[both]]).abs().mean() * 255 if both.any() else torch.tensor(0.0)
    blur_err = ((blurred(pred, palette) - blurred(gt, palette))[both].abs().mean() * 255
                if both.any() else torch.tensor(0.0))
    return {
        "silhouette_iou": float(both.sum() / union.sum().clamp(min=1)),
        "exact_index": float(same.sum() / both.sum().clamp(min=1)),
        "same_ramp": float(same_ramp.sum() / both.sum().clamp(min=1)),
        "rgb_error": float(rgb_err),
        "blurred_rgb_error": float(blur_err),
        "pixels_matching": float(same.sum() / union.sum().clamp(min=1)),
        "stray_pixels": stray_pixels(pred, palette),
        "stray_pixels_truth": stray_pixels(gt, palette),
    }


def mean_scores(items):
    return {k: float(np.mean([s[k] for s in items])) for k in items[0]} if items else {}


def upscale(img: np.ndarray, k: int) -> np.ndarray:
    return img.repeat(k, 0).repeat(k, 1)


def to_rgb(indices: np.ndarray, palette_u8: np.ndarray, background=(64, 64, 64)) -> np.ndarray:
    out = np.empty(indices.shape + (3,), dtype=np.uint8)
    out[:] = background
    solid = indices >= 0
    out[solid] = palette_u8[indices[solid]]
    return out


class Renderer:
    """Renders any direction of a scene and colors it: with the field's own colors, reprojected from
    the known directions, and, with a lighting model, reprojected and relit."""

    def __init__(self, scene: Scene, warp: Warp):
        self.scene, self.warp = scene, warp
        # Sprites use 0 and 128-254; 0 is a baked shadow on characters, which the model doesn't have.
        colors = list(range(128, 255)) if scene.preset.shadows else [0] + list(range(128, 255))
        self.candidates = torch.tensor(colors, device=scene.palette.device)
        if scene.lit:
            scene.field.begin_step()
        right, up, forward = scene.basis(scene.yaws)
        self.sources = []
        for j in scene.train:
            v = scene.views[j]
            r = self.render(v.shape, v.pivot, scene.yaws[j])
            idx = torch.as_tensor(v.indices, device=scene.palette.device).long()
            self.sources.append({
                "view": j, "yaw": float(scene.yaws[j]), "right": right[j], "up": up[j], "forward": forward[j],
                "pivot": v.pivot, "offset": scene.offset,
                "indices": torch.where(scene.masks[j] == 1, idx, torch.full_like(idx, -1)),
                "depth": source_depth(r["target"]["depth"], r["alpha"] >= 0.5, warp)})

    @torch.no_grad()
    def render(self, shape, pivot, yaw_deg) -> dict:
        """Field colors (palette indices), opacity, and what reprojection needs, for one direction."""
        s = self.scene
        right, up, forward = (x[0] for x in s.basis(torch.as_tensor(yaw_deg, device=s.yaws.device).view(1)))
        rgb, alpha = s.field.render(*shape, pivot, s.offset, right, up, forward, s.samples, jitter=False,
                                    yaw_rad=torch.deg2rad(torch.as_tensor(yaw_deg)), supersample=s.supersample)
        depth = s.field.last_surface if self.warp.depth == "median" else s.field.last_depth
        target = {"origins": s.field.last_origins, "depth": depth, "solid": alpha >= 0.5, "yaw": float(yaw_deg),
                  "right": right, "up": up, "forward": forward}
        return {"pred": quantize(rgb, alpha, s.palette, self.candidates), "alpha": alpha, "target": target,
                "normal": s.field.last_normal if s.lit else None}

    def colored(self, r: dict, exclude=None):
        """(reprojected, relit) palette indices; relit is None without a lighting model. Pixels that no
        known direction sees take a neighbour's color (`Warp.fill`), or else keep the field's.
        `exclude` leaves out one known view."""
        s = self.scene
        sources = [src for src in self.sources if src["view"] != exclude]
        t = r["target"]
        rep, origin = reproject(t, sources, self.warp)

        def finish(indices):
            indices = fill(indices, t["solid"], self.warp.fill)
            return torch.where(t["solid"] & (indices < 0), r["pred"], indices)

        plain = finish(rep)
        if not s.lit:
            return plain, None
        # Relight: scale each color by the new direction's shading over its source direction's.
        rgb = s.palette[rep.clamp(min=0)]
        target, _ = s.field.shading(r["normal"], t["right"], t["up"], t["forward"])
        for src in sources:
            m = origin == src["view"]
            if m.any():
                source, _ = s.field.shading(r["normal"][m], src["right"], src["up"], src["forward"])
                rgb[m] = rgb[m] * (target[m] / source.clamp(min=1e-3)).clamp(0.5, 2.0)[:, None]
        return plain, finish(quantize(rgb, (rep >= 0).float(), s.palette, self.candidates))

    def best_colors(self, r: dict):
        plain, relit = self.colored(r)
        return relit if relit is not None else plain


@torch.no_grad()
def evaluate(scene: Scene, out_dir: Path, warp: Warp) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    views, palette, train, test = scene.views, scene.palette, scene.train, scene.test
    device = palette.device
    palette_np = palette.cpu().numpy()
    palette_u8 = (palette_np * 255).round().astype(np.uint8)
    renderer = Renderer(scene, warp)

    # 1. Scores. A known direction's reprojection never uses that direction itself.
    results = {"train": [], "test": [], "test_reprojected": [], "test_relit": [], "baseline": []}
    predictions, reprojected, relit = {}, {}, {}
    for i, v in enumerate(views):
        r = renderer.render(v.shape, v.pivot, scene.yaws[i])
        predictions[i] = r["pred"]
        reprojected[i], relit_i = renderer.colored(r, exclude=i)
        if relit_i is not None:
            relit[i] = relit_i
        gt = torch.as_tensor(v.indices, device=device).long()
        gt = torch.where(scene.masks[i] == 1, gt, torch.full_like(gt, -1))  # without baked shadows
        if i in train:
            results["train"].append(score(r["pred"], gt, palette))
        if i in test:
            results["test"].append(score(r["pred"], gt, palette))
            results["test_reprojected"].append(score(reprojected[i], gt, palette))
            if relit_i is not None:
                results["test_relit"].append(score(relit_i, gt, palette))
            # Baseline: reuse the nearest training direction as-is.
            nearest = min(train, key=lambda j: min(abs(views[j].yaw - v.yaw), 360 - abs(views[j].yaw - v.yaw)))
            base = torch.as_tensor(views[nearest].indices, device=device).long()
            base = torch.where(scene.masks[nearest] == 1, base, torch.full_like(base, -1))
            if base.shape == gt.shape:
                results["baseline"].append(score(base, gt, palette))
    summary = {**scene.config, "views": len(views), "elevation_deg": float(torch.rad2deg(scene.elevation)),
               "pivot_offset": list(scene.offset), "warp": warp.__dict__,
               "train": mean_scores(results["train"]), "test": mean_scores(results["test"]),
               "test_reprojected": mean_scores(results["test_reprojected"]),
               "test_relit": mean_scores(results["test_relit"]),
               "baseline_nearest_view": mean_scores(results["baseline"])}
    if scene.lit:
        f = scene.field
        summary["lights"] = {
            "directions_camera_space": F.normalize(f.light_dirs, dim=-1).tolist(),
            "power": F.softplus(f.light_raw).tolist(),
            "ambient": F.softplus(f.ambient_raw).item(),
            "shininess": torch.exp(f.shininess_raw).item(),
        }
        print("lights (camera space: x right, y up, z toward the camera):", json.dumps(summary["lights"]))
    (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2))
    np.savez_compressed(out_dir / "views.npz",
                        **{"gt%d" % i: v.indices for i, v in enumerate(views)},
                        **{"pred%d" % i: p.cpu().numpy().astype(np.int16) for i, p in predictions.items()},
                        **{"rep%d" % i: p.cpu().numpy().astype(np.int16) for i, p in reprojected.items()},
                        **{"relit%d" % i: p.cpu().numpy().astype(np.int16) for i, p in relit.items()})
    print(json.dumps({k: summary[k] for k in ("train", "test", "test_reprojected", "test_relit",
                                               "baseline_nearest_view")}, indent=2))

    # 2. compare.png: ground truth, field colors, reprojected colors (and relit ones), for every view.
    scale = 3
    tiles = []
    for i, v in enumerate(views):
        gt_img = to_rgb(v.indices, palette_u8)
        marker = np.zeros((4, gt_img.shape[1], 3), dtype=np.uint8)
        marker[:] = (0, 160, 0) if i in train else (200, 40, 40)
        rows = [marker, gt_img, to_rgb(predictions[i].cpu().numpy(), palette_u8),
                to_rgb(reprojected[i].cpu().numpy(), palette_u8)]
        if i in relit:
            rows.append(to_rgb(relit[i].cpu().numpy(), palette_u8))
        tiles.append(np.concatenate(rows, 0))
    Image.fromarray(upscale(np.concatenate(tiles, 1), scale)).save(out_dir / "compare.png")

    # 3. turntable.gif: 32 directions. in_between.png: the originals with a synthesized direction
    #    between each pair, as the game would use them. Both use relit colors when there's a lighting model.
    pal = palette_u8.copy()
    pal[255] = (64, 64, 64)  # sprites never use 255; it stands for transparent here
    frames = []
    for k in range(32):
        r = renderer.render(views[0].shape, views[0].pivot, scene.sign * k * 11.25)
        idx = renderer.best_colors(r).cpu().numpy()
        pixels = upscale(np.where(idx < 0, 255, idx).astype(np.uint8), scale)
        img = Image.frombytes("P", (pixels.shape[1], pixels.shape[0]), pixels.tobytes())
        img.putpalette(pal.flatten().tolist())
        frames.append(img)
    frames[0].save(out_dir / "turntable.gif", save_all=True, append_images=frames[1:], duration=120, loop=0)

    n = len(views)
    strip = []
    for i, v in enumerate(views):
        r = renderer.render(v.shape, v.pivot, scene.sign * (i * 360 / n + 180 / n))
        synth = to_rgb(renderer.best_colors(r).cpu().numpy(), palette_u8)
        bar = np.zeros((4, v.shape[1], 3), dtype=np.uint8)
        strip.append(np.concatenate([np.full_like(bar, (0, 160, 0)), to_rgb(v.indices, palette_u8)], 0))
        strip.append(np.concatenate([np.full_like(bar, (40, 90, 220)), synth], 0))
    Image.fromarray(upscale(np.concatenate(strip, 1), scale)).save(out_dir / "in_between.png")
    print("wrote", out_dir)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", help="output folder of a fit (with scene.pt)")
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--out", default=None, help="where to write (default: the run's folder)")
    add_warp_arguments(ap)
    args = ap.parse_args()
    scene = Scene.load(Path(args.run) / "scene.pt", args.mpq)
    evaluate(scene, Path(args.out or args.run), warp_from_args(args))


if __name__ == "__main__":
    main()
