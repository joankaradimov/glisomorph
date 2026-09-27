"""Proof of concept: reconstruct a Diablo 1 sprite as a voxel field and render other directions.

    python -m poc.fit --mpq PATH/TO/DIABDAT.MPQ --preset arrow --split alternate

Splits:
- "alternate" trains on every other direction and tests on the rest;
- "cardinal" trains on S, W, N and E only;
- "holdout:K" trains on every direction but K;
- "all" trains on everything (tests how well the training views are reproduced).

Outputs go to out/<preset>-<split>-<colors>[-<tag>]/, where <colors> is the lighting model and its
number of lights (phong1 by default), or h<harmonics> without one: the fitted scene (scene.pt), and
what evaluate.py makes of it: metrics.json, views.npz, compare.png, in_between.png and
turntable.gif. See poc/README.md.
"""

import argparse
import dataclasses
import math
import time
from pathlib import Path

import torch

from poc.evaluate import add_warp_arguments, evaluate, warp_from_args
from poc.field import VoxelField, allowed_masks, camera_basis, carve, silhouettes
from poc.scene import Scene, make_field, masks_for
from poc.views import PRESETS, load_views


# Gaussians render each pixel as the average of 16 x 16 samples by default: fitted so, they reproduce the
# originals far better (on the warrior, 90% of pixels exactly against 61% sampled once at pixel
# centers), because a pixel of an original is an average too, over partly covered edges and mixed colors.
GAUSSIAN_SUPERSAMPLE = 16


def run_name(preset: str, split: str, lighting: str = "phong", lights: int = 1, harmonics: int = 0,
             tag: str = "", model: str = "voxels") -> str:
    """A fit's output folder: <preset>-<split>-<colors>[-<tag>] (see the module's docstring)."""
    if model == "gaussians":
        colors = "gauss"
    else:
        colors = "h%d" % harmonics if lighting == "none" else "%s%d" % (lighting, lights)
    return "%s-%s-%s%s" % (preset, split.replace(":", ""), colors, ("-" + tag) if tag else "")


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


def main(argv=None):
    """Fit and evaluate, as the command line (or argv) says. Returns the fitted scene and its folder."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--split", default="alternate",
                    help="alternate, cardinal, all, or holdout:K (train on every direction but K)")
    ap.add_argument("--harmonics", type=int, default=0,
                    help="order of a Fourier series in yaw for view-dependent color (0 = none; order 2 "
                         "overfit in tests)")
    ap.add_argument("--model", default="voxels", choices=["voxels", "gaussians"],
                    help="what represents the sprite: a voxel field, or 3D Gaussians (gaussians.py; needs gsplat)")
    ap.add_argument("--lighting", default="phong", choices=["none", "lambert", "phong"],
                    help="shade albedo with directional lights fixed relative to the camera; 'none' fits plain "
                         "colors")
    ap.add_argument("--lights", type=int, default=1, choices=[1, 2])
    ap.add_argument("--light-lr", type=float, default=0.01)
    ap.add_argument("--coupled-normals", action="store_true",
                    help="let shading gradients reshape the density through the normals")
    ap.add_argument("--supersample", type=int, default=None,
                    help="render each pixel as the average of s x s sub-pixel samples (area sampling); by default "
                         "%d for Gaussians, 1 for voxels" % GAUSSIAN_SUPERSAMPLE)
    ap.add_argument("--snap", type=float, default=0.0,
                    help="Gaussians: fit colors as they'll be snapped to the palette, by cross-entropy over its "
                         "colors at this temperature (0: the squared distance to the pixel's palette color)")
    ap.add_argument("--keyed", action="store_true",
                    help="Gaussians: fit opacity as the sprites' 1-bit transparency (any above a half is solid)")
    ap.add_argument("--refine-camera", action="store_true",
                    help="refine the calibrated elevation and pivot offset by gradient")
    ap.add_argument("--refine-from", type=int, default=300, help="iteration at which camera refinement starts")
    ap.add_argument("--camera-lr", type=float, default=1e-3,
                    help="learning rate of the elevation in radians; the pivot offset's is 20 times this, in pixels")
    ap.add_argument("--frame", type=int, default=None, help="animation frame (default: the preset's)")
    ap.add_argument("--camera", default=None,
                    help="take the camera from another fit (its output folder) instead of calibrating: for the "
                         "frames of one animation, so that they share it")
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
    ap.add_argument("--no-evaluate", action="store_true", help="save the fit without scoring it or drawing pictures")
    add_warp_arguments(ap)
    args = ap.parse_args(argv)
    if args.supersample is None:
        args.supersample = GAUSSIAN_SUPERSAMPLE if args.model == "gaussians" else 1

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    preset = PRESETS[args.preset]
    if args.frame is not None:
        preset = dataclasses.replace(preset, frame=args.frame)
    views, palette_np = load_views(args.mpq, preset)
    palette = torch.as_tensor(palette_np, device=device)
    masks = masks_for(views, preset.shadows, device)
    train, test = split_indices(len(views), args.split)
    out_dir = Path(args.out) / run_name(args.preset, args.split, args.lighting, args.lights, args.harmonics, args.tag,
                                        args.model)
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

    # 1. The camera: calibrated on a coarse grid, for both senses of rotation, or taken from another fit.
    #    Silhouettes pin the camera down to about a pixel, so the frames of one animation, calibrated
    #    each on its own, would jitter.
    t0 = time.time()
    if args.camera:
        saved = torch.load(Path(args.camera) / "scene.pt", map_location="cpu")
        sign, elev_deg, off = saved["config"]["yaw_sign"], math.degrees(saved["elevation"]), tuple(saved["offset"])
        coverage = None
        print("camera from %s: yaw sign %+d, elevation %.1f deg, pivot offset %s" % (args.camera, sign, elev_deg, off))
    else:
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
    right, up, _ = camera_basis(yaws, elev)

    # 2. The field, started from the visual hull of the training views: voxels, or a Gaussian at each
    #    voxel of the hull (gaussians.py, unlit for now).
    gaussians = args.model == "gaussians"
    lit = args.lighting != "none" and not gaussians
    config = {"preset": args.preset, "frame": preset.frame, "split": args.split, "train_views": train,
              "test_views": test if args.split != "all" else [], "model": args.model,
              "lighting": args.lighting if lit else "none", "lights": args.lights, "harmonics": args.harmonics,
              "coupled_normals": args.coupled_normals, "voxel": args.voxel, "box_min": box_min, "box_max": box_max,
              "supersample": args.supersample, "snap": args.snap, "keyed": args.keyed, "yaw_sign": sign}
    yaw_rad = torch.deg2rad(yaws)
    if gaussians:
        from poc.gaussians import GaussianField  # needs gsplat
        grid = VoxelField(box_min, box_max, args.voxel, device)
        inside = carve(grid, allowed_masks(train_masks), train_views, right[train], up[train], off)
        field = GaussianField.from_points(grid.voxel_centers()[inside], args.voxel)
        print("%d Gaussians, one per voxel of the visual hull" % len(field.params["means"]))
    else:
        field = make_field(config, device)
        inside = carve(field, allowed_masks(train_masks), train_views, right[train], up[train], off)
        with torch.no_grad():
            field.density[0, 0][inside] = 4.0
        if not args.no_hull:
            field.restrict_to(inside)
    depth = (torch.tensor(box_max) - torch.tensor(box_min)).norm().item()
    samples = int(depth / args.voxel)
    if gaussians:
        if args.refine_camera:
            raise SystemExit("--refine-camera isn't supported with --model gaussians")
        opt = None  # they train with their own optimizers (GaussianField.fit)
    elif lit:
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
    sched = torch.optim.lr_scheduler.ExponentialLR(opt, gamma=(0.1) ** (1 / args.iters)) if opt else None
    targets = [(palette[torch.as_tensor(views[i].indices, device=device).long().clamp(min=0)], masks[i])
               for i in train]

    def tv(p):
        return (((p[..., 1:, :, :] - p[..., :-1, :, :]) ** 2).mean() + ((p[..., :, 1:, :] - p[..., :, :-1, :]) ** 2).mean()
                + ((p[..., :, :, 1:] - p[..., :, :, :-1]) ** 2).mean())

    if gaussians:
        # All training views at once, with densification (gaussians.py).
        from poc.gaussians import intrinsics, viewmat
        r, u, f = camera_basis(yaws[train], elev)
        snap = None
        if args.snap:
            candidates = torch.tensor([0] + list(range(128, 255)), device=device)  # the indices sprites use
            colors = palette[candidates].float()
            class_of = ((palette.float()[:, None] - colors) ** 2).sum(-1).argmin(1)  # each index's nearest
            snap = (colors, torch.stack([class_of[torch.as_tensor(views[i].indices, device=device).long().clamp(min=0)]
                                         for i in train]), args.snap)
        field.fit(torch.stack([viewmat(r[k], u[k], f[k]) for k in range(len(train))]),
                  torch.stack([intrinsics(views[i].pivot, off, device) for i in train]),
                  torch.stack([t[0] for t in targets]), torch.stack([t[1] == 1 for t in targets]),
                  iters=args.iters, lr=args.lr, supersample=args.supersample, snap=snap, keyed=args.keyed)
    else:
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
                if args.sparsity and not gaussians:
                    # Prefer the fewest voxels that explain every view: phantom copies cost extra.
                    loss = loss + args.sparsity * field.last_alpha[solid].sum(-1).mean()
                (loss / len(train)).backward()
                total += loss.item() / len(train)
            if gaussians:
                regularizer = field.regularizer()
            else:
                regularizer = args.tv * tv(field.density) + args.color_tv * tv(field.color)
            regularizer.backward()
            opt.step()
            sched.step()
            if it % 500 == 0 or it == args.iters - 1:
                print("iter %5d  loss %.5f  (%.0fs)" % (it, total + regularizer.item(), time.time() - t0))

    if args.refine_camera:
        off = tuple(off_param.detach().tolist())
        print("refined camera: elevation %.2f deg (was %.1f), pivot offset (%.2f, %.2f)"
              % (math.degrees(elev_param.item()), elev_deg, off[0], off[1]))
        elev = elev_param.detach()
    config.update({"iters": args.iters, "elevation_calibrated_deg": elev_deg, "calibration_coverage": coverage,
                   "camera_from": args.camera, "refine_camera": args.refine_camera})
    scene = Scene(field=field, views=views, masks=masks, palette=palette, yaws=yaws, elevation=elev, offset=off,
                  samples=samples, config=config)
    scene.save(out_dir / "scene.pt")

    # 3. Scores and pictures of the held-out and in-between directions (evaluate.py).
    if not args.no_evaluate:
        evaluate(scene, out_dir, warp_from_args(args))
    return scene, out_dir


if __name__ == "__main__":
    main()
