"""Proof of concept: reconstruct a Diablo 1 sprite as a voxel field and render other directions.

    python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset arrow --split alternate

Splits:
- "alternate" trains on every other direction and tests on the rest;
- "cardinal" trains on S, W, N and E only;
- "holdout:K" trains on every direction but K;
- "all" trains on everything (tests how well the training views are reproduced).

Outputs go to out/<preset>-<split>-h<harmonics>[-<tag>]/: metrics.json, compare.png,
in_between.png and turntable.gif. See poc/README.md.
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from diablo1.palette import RAMPS, ramp_of
from poc.field import LitVoxelField, VoxelField, allowed_masks, camera_basis, carve, silhouettes
from poc.reproject import reproject
from poc.views import PRESETS, View, load_views


def masks_for(views: list[View], shadows: bool, device) -> list[torch.Tensor]:
    """1 where the model is seen, 0 elsewhere.

    A baked shadow (index 0 on a character) is on the ground, and the model doesn't cover it, so it
    counts as transparent.
    """
    out = []
    for v in views:
        idx = torch.as_tensor(v.indices, device=device).long()
        m = (idx >= 0).long()
        if shadows:
            m[idx == 0] = 0
        out.append(m)
    return out


def split_indices(n: int, split: str) -> tuple[list[int], list[int]]:
    if split == "all":
        return list(range(n)), list(range(n))
    if split == "alternate":
        return list(range(0, n, 2)), list(range(1, n, 2))
    if split == "cardinal":
        step = n // 4
        train = list(range(0, n, step))
        return train, [i for i in range(n) if i not in train]
    if split.startswith("holdout:"):
        held = int(split.split(":")[1])
        return [i for i in range(n) if i != held], [held]
    raise ValueError(split)


def calibrate(field, views, masks, yaws, device, elevations, offsets):
    """Pick the elevation and pivot offset whose visual hull best explains every silhouette."""
    best = (0.0, None, None)
    allowed = allowed_masks(masks)
    for elev_deg in elevations:
        elev = torch.tensor(math.radians(elev_deg), device=device)
        right, up, _ = camera_basis(yaws, elev)
        for off in offsets:
            inside = carve(field, allowed, views, right, up, off)
            if not inside.any():
                continue
            projected = silhouettes(inside, field, views, right, up, off)
            covered = total = 0
            for m, p in zip(masks, projected):
                solid = m == 1
                covered += int((p & solid).sum())
                total += int(solid.sum())
            score = covered / max(total, 1)
            if score > best[0]:
                best = (score, elev_deg, off)
    return best


def quantize(rgb, alpha, palette, candidates):
    """Palette index per pixel (-1 where transparent) for premultiplied rgb (H, W, 3)."""
    color = rgb / alpha.clamp(min=1e-6)[..., None]
    pal = palette[candidates]                                            # (C, 3)
    dist = ((color[..., None, :] - pal) ** 2).sum(-1)                   # (H, W, C)
    idx = candidates[dist.argmin(-1)]
    return torch.where(alpha >= 0.5, idx, torch.full_like(idx, -1))


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
    return {
        "silhouette_iou": float(both.sum() / union.sum().clamp(min=1)),
        "exact_index": float(same.sum() / both.sum().clamp(min=1)),
        "same_ramp": float(same_ramp.sum() / both.sum().clamp(min=1)),
        "rgb_error": float(rgb_err),
        "pixels_matching": float(same.sum() / union.sum().clamp(min=1)),
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--split", default="alternate",
                    help="alternate, cardinal, all, or holdout:K (train on every direction but K)")
    ap.add_argument("--harmonics", type=int, default=0,
                    help="order of a Fourier series in yaw for view-dependent color (0 = none; order 2 "
                         "overfit in tests)")
    ap.add_argument("--lighting", default="none", choices=["none", "lambert", "phong"],
                    help="shade albedo with directional lights fixed relative to the camera")
    ap.add_argument("--lights", type=int, default=1, choices=[1, 2])
    ap.add_argument("--light-lr", type=float, default=0.01)
    ap.add_argument("--coupled-normals", action="store_true",
                    help="let shading gradients reshape the density through the normals")
    ap.add_argument("--supersample", type=int, default=1,
                    help="render each pixel as the average of s x s sub-pixel rays (area sampling)")
    ap.add_argument("--refine-camera", action="store_true",
                    help="refine the calibrated elevation and pivot offset by gradient")
    ap.add_argument("--refine-from", type=int, default=300, help="iteration at which camera refinement starts")
    ap.add_argument("--camera-lr", type=float, default=1e-3,
                    help="learning rate of the elevation in radians; the pivot offset's is 20 times this, in pixels")
    ap.add_argument("--frame", type=int, default=None, help="animation frame (default: the preset's)")
    ap.add_argument("--voxel", type=float, default=1.0, help="voxel size in pixels (0.6 suits thin sprites)")
    ap.add_argument("--iters", type=int, default=2000)
    ap.add_argument("--lr", type=float, default=0.05)
    ap.add_argument("--tv", type=float, default=1e-4, help="total-variation weight on density")
    ap.add_argument("--color-tv", type=float, default=1e-4, help="total-variation weight on color")
    ap.add_argument("--sparsity", type=float, default=0.0, help="weight of the per-ray opacity-sum penalty")
    ap.add_argument("--tag", default="", help="suffix for the output folder")
    ap.add_argument("--no-hull", action="store_true", help="don't confine density to the visual hull")
    ap.add_argument("--out", default="out")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    preset = PRESETS[args.preset]
    if args.frame is not None:
        preset.frame = args.frame
    views, palette_np = load_views(args.mpq, preset)
    palette = torch.as_tensor(palette_np, device=device)
    palette_u8 = (palette_np * 255).round().astype(np.uint8)
    masks = masks_for(views, preset.shadows, device)
    train, test = split_indices(len(views), args.split)
    color_model = "h%d" % args.harmonics if args.lighting == "none" else "%s%d" % (args.lighting, args.lights)
    out_dir = Path(args.out) / ("%s-%s-%s%s" % (args.preset, args.split.replace(":", ""), color_model,
                                                ("-" + args.tag) if args.tag else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    # A box generous enough for any elevation we try.
    width = max(v.shape[1] for v in views)
    radius = width / 2 + 4
    top = max(v.pivot[1] for v in views)
    bottom = max(v.shape[0] - v.pivot[1] for v in views)
    theta = math.radians(40)
    box_min = [-radius, -(bottom + radius * math.sin(theta)) / math.cos(theta), -radius]
    box_max = [radius, (top + radius * math.sin(theta)) / math.cos(theta), radius]

    yaws = torch.tensor([v.yaw for v in views], dtype=torch.float32, device=device)
    train_views = [views[i] for i in train]
    train_masks = [masks[i] for i in train]
    train_yaws = yaws[train]

    # 1. Calibration on a coarse grid, for both senses of rotation.
    t0 = time.time()
    coarse = VoxelField(box_min, box_max, 1.0, device)
    offsets = [(dx, dy) for dx in (-2, -1, 0, 1, 2) for dy in range(-6, 7, 2)]
    candidates_by_sign = {}
    for sign in (1, -1):
        candidates_by_sign[sign] = calibrate(coarse, train_views, train_masks, sign * train_yaws, device,
                                             range(20, 41, 2), offsets)
    sign = max(candidates_by_sign, key=lambda s: candidates_by_sign[s][0])
    _, elev_deg, off = candidates_by_sign[sign]
    fine_offsets = [(off[0] + dx, off[1] + dy) for dx in (-0.5, 0, 0.5) for dy in (-1, 0, 1)]
    best = calibrate(coarse, train_views, train_masks, sign * train_yaws, device,
                     [elev_deg + d for d in (-1.5, -1, -0.5, 0, 0.5, 1, 1.5)], fine_offsets)
    coverage, elev_deg, off = best
    print("calibration: yaw sign %+d (coverage %.3f vs %.3f mirrored), elevation %.1f deg, pivot offset %s, "
          "coverage %.3f (%.0fs)" % (sign, candidates_by_sign[sign][0], candidates_by_sign[-sign][0],
                                     elev_deg, off, coverage, time.time() - t0))
    yaws = sign * yaws
    elev = torch.tensor(math.radians(elev_deg), device=device)
    right, up, forward = camera_basis(yaws, elev)

    # 2. The field, started from the visual hull of the training views.
    lit = args.lighting != "none"
    if lit:
        field = LitVoxelField(box_min, box_max, args.voxel, device, lights=args.lights,
                              specular=args.lighting == "phong", detach_normals=not args.coupled_normals)
    else:
        field = VoxelField(box_min, box_max, args.voxel, device, harmonics=args.harmonics)
    yaw_rad = torch.deg2rad(yaws)
    inside = carve(field, allowed_masks(train_masks), train_views, right[train], up[train], off)
    with torch.no_grad():
        field.density[0, 0][inside] = 4.0
    if not args.no_hull:
        field.restrict_to(inside)
    depth = (field.box_max - field.box_min).norm().item()
    samples = int(depth / args.voxel)
    if lit:
        light_ids = {id(p) for p in field.light_parameters()}
        groups = [{"params": [p for p in field.parameters() if id(p) not in light_ids], "lr": args.lr},
                  {"params": field.light_parameters(), "lr": args.light_lr}]
        opt = torch.optim.Adam(groups)
    else:
        opt = torch.optim.Adam(field.parameters(), lr=args.lr)
    # The camera found by calibration, refined by gradient once the field has taken shape.
    elev_param = torch.nn.Parameter(torch.tensor(math.radians(elev_deg), device=device), requires_grad=False)
    off_param = torch.nn.Parameter(torch.tensor(off, dtype=torch.float32, device=device), requires_grad=False)
    if args.refine_camera:
        # Adam steps are about lr in size whatever the gradient, so the rates set the precision:
        # 1e-3 radians is about 0.06 degrees, 2e-2 pixels is 1/50 of a pixel, both decaying tenfold.
        opt.add_param_group({"params": [elev_param], "lr": args.camera_lr})
        opt.add_param_group({"params": [off_param], "lr": args.camera_lr * 20})
    sched = torch.optim.lr_scheduler.ExponentialLR(opt, gamma=(0.1) ** (1 / args.iters))
    targets = [(palette[torch.as_tensor(views[i].indices, device=device).long().clamp(min=0)], masks[i])
               for i in train]

    def tv(p):
        return (((p[..., 1:, :, :] - p[..., :-1, :, :]) ** 2).mean() + ((p[..., :, 1:, :] - p[..., :, :-1, :]) ** 2).mean()
                + ((p[..., :, :, 1:] - p[..., :, :, :-1]) ** 2).mean())

    t0 = time.time()
    for it in range(args.iters):
        if args.refine_camera and it == args.refine_from:
            elev_param.requires_grad_(True)
            off_param.requires_grad_(True)
        opt.zero_grad()
        total = 0.0
        # One backward pass per view keeps memory to a single view's rays, supersampled or not.
        for k, i in enumerate(train):
            if lit:
                field.begin_step()
            r, u, f = camera_basis(yaws[i:i + 1], elev_param)
            h, w = views[i].shape
            rgb, alpha = field.render(h, w, views[i].pivot, off_param, r[0], u[0], f[0], samples,
                                      jitter=True, yaw_rad=yaw_rad[i], supersample=args.supersample)
            color, m = targets[k]
            solid = m == 1
            loss = ((rgb - color) ** 2)[solid].mean()
            loss = loss + 0.5 * torch.nn.functional.binary_cross_entropy(alpha.clamp(1e-5, 1 - 1e-5), solid.float())
            if args.sparsity:
                # Prefer the fewest voxels that explain every view: phantom copies cost extra.
                loss = loss + args.sparsity * field.last_alpha[solid].sum(-1).mean()
            (loss / len(train)).backward()
            total += loss.item() / len(train)
        regularizer = args.tv * tv(field.density) + args.color_tv * tv(field.color)
        regularizer.backward()
        opt.step()
        sched.step()
        if it % 500 == 0 or it == args.iters - 1:
            print("iter %5d  loss %.5f  (%.0fs)" % (it, total + regularizer.item(), time.time() - t0))

    if args.refine_camera:
        elev_deg_refined = math.degrees(elev_param.item())
        off = tuple(off_param.detach().tolist())
        print("refined camera: elevation %.2f deg (was %.1f), pivot offset (%.2f, %.2f)"
              % (elev_deg_refined, elev_deg, off[0], off[1]))
        elev = elev_param.detach()
        right, up, forward = camera_basis(yaws, elev)
    else:
        elev_deg_refined = elev_deg

    # 3. Evaluation. A new view can be colored three ways: the field's own colors (quantized to the
    #    palette), palette indices reprojected from the known directions, and, with a lighting model,
    #    those reprojected colors relit from their source direction's lighting to the new one's.
    candidates = torch.tensor(list(range(128, 255)) if preset.shadows else [0] + list(range(128, 255)), device=device)
    if lit:
        field.begin_step()

    def render_view(h, w, pivot, r, u, f, yaw_deg):
        rgb, alpha = field.render(h, w, pivot, off, r, u, f, samples, jitter=False, yaw_rad=torch.deg2rad(yaw_deg),
                                  supersample=args.supersample)
        points = field.last_origins + field.last_depth[..., None] * f
        return quantize(rgb, alpha, palette, candidates), alpha, points, (field.last_normal if lit else None)

    def colored(pred, alpha, points, normal, yaw_deg, basis, exclude=None):
        """(reprojected, relit) palette indices; relit is None without a lighting model."""
        srcs = [s for s in sources if s["view"] != exclude]
        solid = alpha >= 0.5
        rep, origin = reproject(points, solid, yaw_deg, srcs)
        plain = torch.where(solid & (rep < 0), pred, rep)  # the field's color where no view sees it
        if not lit:
            return plain, None
        rgb = palette[rep.clamp(min=0)]
        target, _ = field.shading(normal, *basis)
        for s in srcs:
            m = origin == s["view"]
            if m.any():
                source, _ = field.shading(normal[m], s["right"], s["up"], s["forward"])
                rgb[m] = rgb[m] * (target[m] / source.clamp(min=1e-3)).clamp(0.5, 2.0)[:, None]
        relit_view = quantize(rgb, (rep >= 0).float(), palette, candidates)
        return plain, torch.where(solid & (rep < 0), pred, relit_view)

    results = {"train": [], "test": [], "test_reprojected": [], "test_relit": [], "baseline": []}
    predictions, reprojected, relit = {}, {}, {}
    with torch.no_grad():
        sources = []
        for j in train:
            v = views[j]
            render_view(*v.shape, v.pivot, right[j], up[j], forward[j], yaws[j])
            idx = torch.as_tensor(v.indices, device=device).long()
            sources.append({"view": j, "yaw": float(yaws[j]), "depth": field.last_depth.clone(),
                            "indices": torch.where(masks[j] == 1, idx, torch.full_like(idx, -1)),
                            "right": right[j], "up": up[j], "forward": forward[j], "pivot": v.pivot, "offset": off})
        for i, v in enumerate(views):
            pred, alpha, points, normal = render_view(*v.shape, v.pivot, right[i], up[i], forward[i], yaws[i])
            predictions[i] = pred
            reprojected[i], relit_i = colored(pred, alpha, points, normal, float(yaws[i]),
                                              (right[i], up[i], forward[i]), exclude=i)
            if relit_i is not None:
                relit[i] = relit_i
            gt = torch.as_tensor(v.indices, device=device).long()
            gt = torch.where(masks[i] == 1, gt, torch.full_like(gt, -1))  # without baked shadows
            if i in train:
                results["train"].append(score(pred, gt, palette))
            if i in test and args.split != "all":
                results["test"].append(score(pred, gt, palette))
                results["test_reprojected"].append(score(reprojected[i], gt, palette))
                if relit_i is not None:
                    results["test_relit"].append(score(relit_i, gt, palette))
                # Baseline: reuse the nearest training direction as-is.
                nearest = min(train, key=lambda j: min(abs(views[j].yaw - v.yaw), 360 - abs(views[j].yaw - v.yaw)))
                base = torch.as_tensor(views[nearest].indices, device=device).long()
                base = torch.where(masks[nearest] == 1, base, torch.full_like(base, -1))
                if base.shape == gt.shape:
                    results["baseline"].append(score(base, gt, palette))
    summary = {
        "preset": args.preset, "split": args.split, "frame": preset.frame, "views": len(views),
        "train_views": train, "test_views": test if args.split != "all" else [],
        "elevation_deg": elev_deg_refined, "elevation_calibrated_deg": elev_deg, "pivot_offset": off,
        "calibration_coverage": coverage, "refine_camera": args.refine_camera, "supersample": args.supersample,
        "voxel": args.voxel, "iters": args.iters, "lighting": args.lighting,
        "train": mean_scores(results["train"]), "test": mean_scores(results["test"]),
        "test_reprojected": mean_scores(results["test_reprojected"]),
        "test_relit": mean_scores(results["test_relit"]),
        "baseline_nearest_view": mean_scores(results["baseline"]),
    }
    if lit:
        with torch.no_grad():
            summary["lights"] = {
                "directions_camera_space": torch.nn.functional.normalize(field.light_dirs, dim=-1).tolist(),
                "power": torch.nn.functional.softplus(field.light_raw).tolist(),
                "ambient": torch.nn.functional.softplus(field.ambient_raw).item(),
                "shininess": torch.exp(field.shininess_raw).item(),
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

    # 4. Pictures. compare.png: ground truth, field colors, reprojected colors, for every view (the
    #    reprojection of a view never uses that view itself).
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

    def best_colors(pred, alpha, points, normal, yaw_deg, basis):
        plain, relit_view = colored(pred, alpha, points, normal, yaw_deg, basis)
        return relit_view if relit_view is not None else plain

    # turntable.gif: 32 directions. in_between.png: the originals with a synthesized direction
    # between each pair, as the game would use them. Both use relit colors when there's a lighting model.
    pal = palette_u8.copy()
    pal[255] = (64, 64, 64)  # sprites never use 255; it stands for transparent here
    frames = []
    with torch.no_grad():
        yaw32 = sign * torch.arange(32, device=device, dtype=torch.float32) * 11.25
        r32, u32, f32 = camera_basis(yaw32, elev)
        for k in range(32):
            pred, alpha, points, normal = render_view(*views[0].shape, views[0].pivot, r32[k], u32[k], f32[k], yaw32[k])
            idx = best_colors(pred, alpha, points, normal, float(yaw32[k]), (r32[k], u32[k], f32[k])).cpu().numpy()
            pixels = upscale(np.where(idx < 0, 255, idx).astype(np.uint8), scale)
            img = Image.frombytes("P", (pixels.shape[1], pixels.shape[0]), pixels.tobytes())
            img.putpalette(pal.flatten().tolist())
            frames.append(img)
        frames[0].save(out_dir / "turntable.gif", save_all=True, append_images=frames[1:], duration=120, loop=0)

        n = len(views)
        strip = []
        mids = sign * (torch.arange(n, device=device, dtype=torch.float32) * (360 / n) + 180 / n)
        rm, um, fm = camera_basis(mids, elev)
        for i, v in enumerate(views):
            pred, alpha, points, normal = render_view(*v.shape, v.pivot, rm[i], um[i], fm[i], mids[i])
            synth = to_rgb(best_colors(pred, alpha, points, normal, float(mids[i]), (rm[i], um[i], fm[i])).cpu().numpy(),
                           palette_u8)
            bar = np.zeros((4, v.shape[1], 3), dtype=np.uint8)
            strip.append(np.concatenate([np.full_like(bar, (0, 160, 0)), to_rgb(v.indices, palette_u8)], 0))
            strip.append(np.concatenate([np.full_like(bar, (40, 90, 220)), synth], 0))
    Image.fromarray(upscale(np.concatenate(strip, 1), scale)).save(out_dir / "in_between.png")
    print("wrote", out_dir)


if __name__ == "__main__":
    main()
