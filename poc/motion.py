"""Gaussians that move: one set for a whole looping animation, moved by a few hundred nodes.

    python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk
    python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --hide-direction 1
    python -m poc.motion --mpq PATH/TO/DIABDAT.MPQ --preset warrior-walk --hide-frames odd

A looping animation is a torus: 8 directions around one circle, the frames around another. A
direction is the camera turning around the model, which calibration already knows; a frame is the
model changing pose, which has to be learned. So the model here is one set of Gaussians (gaussians.py)
whose shape, opacity and color are shared by every frame, moved per frame by a few hundred nodes
(embedded deformation, as in SC-GS): each node has a rotation and a translation per frame, each
Gaussian follows its nearest nodes, and neighbouring nodes are held rigid to each other. Moving
whole limbs through a few nodes is far better posed than moving every Gaussian on its own.

1. Every frame is fitted like a still (fit.py --model gaussians). Frame 0 calibrates the camera, and
   its Gaussians become the moving ones; the other stills are targets.
2. Each next frame starts from the previous one's node poses and moves them to fit its views. Two
   things pull from afar, where the images' gradients don't reach: the Gaussians are drawn to the
   nearest same-colored Gaussians of that frame's still (a chamfer distance, recomputed now and then
   as in ICP), and blurred copies of the images are compared first.
3. All frames are then refined together, the last one tied to the first, with node paths kept smooth.

A phase between frames interpolates the node poses periodically (Catmull-Rom). --hide-direction and
--hide-frames keep a direction or every other frame out of the fit, to score the in-betweens against
the originals.

Outputs, in out/<preset>-motion[-<test>]/: metrics.json, sheet.png (16 directions by twice the frames,
in the palette; originals without their baked shadows, which the model doesn't cast yet),
directions.gif and motion.pt.
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
from gsplat import rasterization

from poc import fit
from poc.animate import write_gif, write_sheet
from poc.evaluate import quantize, score
from poc.field import camera_basis
from poc.gaussians import intrinsics, viewmat
from poc.scene import masks_for
from poc.views import PRESETS, frame_count, load_views


def quat_multiply(a, b):
    aw, ax, ay, az = a.unbind(-1)
    bw, bx, by, bz = b.unbind(-1)
    return torch.stack([aw * bw - ax * bx - ay * by - az * bz, aw * bx + ax * bw + ay * bz - az * by,
                        aw * by - ax * bz + ay * bw + az * bx, aw * bz + ax * by - ay * bx + az * bw], -1)


def quat_rotate(q, v):
    """Rotate vectors v (..., 3) by unit quaternions q (..., 4)."""
    w, xyz = q[..., :1], q[..., 1:]
    t = 2 * torch.cross(xyz, v, dim=-1)
    return v + w * t + torch.cross(xyz, t, dim=-1)


def same_hemisphere(q, reference):
    """q with its sign flipped where it points away from `reference` (q and -q are one rotation)."""
    return q * torch.where((q * reference).sum(-1, keepdim=True) < 0, -1.0, 1.0)


def catmull_rom(points, phase, quaternions: bool = False):
    """Periodic Catmull-Rom interpolation of points (N, ...) at a phase in [0, N) (frames as units).
    With `quaternions`, the four control quaternions are first put on one hemisphere, and the result
    is normalized."""
    n = points.shape[0]
    k = int(math.floor(phase)) % n
    t = phase - math.floor(phase)
    p0, p1, p2, p3 = (points[(k + d) % n] for d in (-1, 0, 1, 2))
    if quaternions:
        p0, p2, p3 = (same_hemisphere(p, p1) for p in (p0, p2, p3))
    out = 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3)
    return F.normalize(out, dim=-1) if quaternions else out


def farthest_points(points, count: int):
    """Indices of `count` points spread over the set by farthest point sampling."""
    chosen = torch.zeros(count, dtype=torch.long, device=points.device)
    chosen[0] = (points - points.mean(0)).norm(dim=-1).argmin()
    dist = torch.full((len(points),), float("inf"), device=points.device)
    for i in range(1, count):
        dist = torch.minimum(dist, (points - points[chosen[i - 1]]).norm(dim=-1))
        chosen[i] = dist.argmax()
    return chosen


class MovingGaussians(torch.nn.Module):
    """Shared Gaussians (rest means and quaternions, log scales, opacity and color logits), moved by
    nodes with a unit quaternion and a translation each, per frame."""

    def __init__(self, still, frames: int, nodes: int = 256, bind: int = 4, links: int = 6):
        super().__init__()
        p = still.params
        self.means0 = torch.nn.Parameter(p["means"].detach().clone())
        self.quats0 = torch.nn.Parameter(F.normalize(p["quats"].detach(), dim=-1))
        self.scales = torch.nn.Parameter(p["scales"].detach().clone())
        self.opacities = torch.nn.Parameter(p["opacities"].detach().clone())
        self.colors = torch.nn.Parameter(p["colors"].detach().clone())
        with torch.no_grad():
            opaque = self.means0[torch.sigmoid(self.opacities) > 0.3]
            centers = opaque[farthest_points(opaque, nodes)]
            gaps = torch.cdist(centers, centers).topk(2, largest=False).values[:, 1]
            spacing = float(gaps.median())
            # Each Gaussian follows its nearest nodes, weighted by closeness.
            d, idx = torch.cdist(self.means0, centers).topk(bind, largest=False)
            w = torch.exp(-d ** 2 / (2 * spacing ** 2)) + 1e-6
            # Neighbouring nodes, held rigid to each other.
            nd, nidx = torch.cdist(centers, centers).topk(links + 1, largest=False)
        self.register_buffer("centers", centers)
        self.register_buffer("bind_idx", idx)
        self.register_buffer("bind_w", w / w.sum(-1, keepdim=True))
        self.register_buffer("links", nidx[:, 1:])
        self.register_buffer("link_w", torch.exp(-nd[:, 1:] ** 2 / (2 * spacing ** 2)))
        self.spacing = spacing
        identity = torch.tensor([1.0, 0, 0, 0], device=centers.device)
        self.node_quats = torch.nn.Parameter(identity.repeat(frames, nodes, 1))
        self.node_moves = torch.nn.Parameter(torch.zeros((frames, nodes, 3), device=centers.device))

    def node_pose(self, phase: float):
        """The nodes' unit quaternions (M, 4) and translations (M, 3) at a phase in model frames."""
        if float(phase).is_integer():
            k = int(phase) % self.node_quats.shape[0]
            return F.normalize(self.node_quats[k], dim=-1), self.node_moves[k]
        return (catmull_rom(F.normalize(self.node_quats, dim=-1), phase, quaternions=True),
                catmull_rom(self.node_moves, phase))

    def pose(self, phase: float):
        """The Gaussians' means (G, 3) and unit quaternions (G, 4) at a phase."""
        rot, move = self.node_pose(phase)
        idx, w = self.bind_idx, self.bind_w[..., None]
        offsets = self.means0[:, None] - self.centers[idx]
        means = (w * (quat_rotate(rot[idx], offsets) + self.centers[idx] + move[idx])).sum(1)
        turns = rot[idx]
        turn = F.normalize((w * same_hemisphere(turns, turns[:, :1])).sum(1), dim=-1)
        return means, quat_multiply(turn, F.normalize(self.quats0, dim=-1))

    def rasterize(self, phase, viewmats, Ks, width, height):
        means, quats = self.pose(phase)
        return rasterization(means, quats, torch.exp(self.scales), torch.sigmoid(self.opacities),
                             torch.sigmoid(self.colors), viewmats, Ks, width, height, camera_model="ortho",
                             render_mode="RGB+ED", packed=False)

    def arap(self, slot: int):
        """As rigid as possible: where a node's pose puts each neighbouring node, against where that
        neighbour's own pose puts it (embedded deformation's regularizer), in node spacings."""
        rot, move = F.normalize(self.node_quats[slot], dim=-1), self.node_moves[slot]
        c, n = self.centers, self.links
        predicted = quat_rotate(rot[:, None].expand(-1, n.shape[1], -1), c[n] - c[:, None]) + c[:, None] + move[:, None]
        actual = c[n] + move[n]
        return (self.link_w * (predicted - actual).norm(dim=-1)).mean() / self.spacing

    def smoothness(self):
        """Node paths around the loop: squared second differences of translations and quaternions."""
        m = self.node_moves
        q = F.normalize(self.node_quats, dim=-1)
        accel = (m.roll(-1, 0) - 2 * m + m.roll(1, 0)).square().sum(-1).mean()
        qn, qp = same_hemisphere(q.roll(-1, 0), q), same_hemisphere(q.roll(1, 0), q)
        return accel + 100 * (qn - 2 * q + qp).square().sum(-1).mean()


def nearest(a, b):
    """For each row of a (Na, D), the index of the nearest row of b (Nb, D)."""
    return torch.cat([torch.cdist(chunk, b).argmin(-1) for chunk in torch.split(a, 4096)])


def matching(means, colors, weight, target_means, target_colors, pairs=None, color_scale: float = 10.0):
    """A chamfer distance from the moving Gaussians (means, colors, weight: how opaque) to a frame's own
    still (target means and colors), in position and color: each side pulled to its nearest point on
    the other. `pairs` are the nearest-neighbour indices, recomputed now and then (as in ICP); pass
    None to compute them. Returns the loss and the pairs."""
    a = torch.cat([means, color_scale * colors], -1)
    b = torch.cat([target_means, color_scale * target_colors], -1)
    if pairs is None:
        with torch.no_grad():
            pairs = (nearest(a, b), nearest(b, a))
    to_target = (weight * (a - b[pairs[0]]).norm(dim=-1)).sum() / weight.sum()
    from_target = (b - a[pairs[1]]).norm(dim=-1).mean()
    return to_target + from_target, pairs


def image_loss(colors, alphas, targets, masks, blur: int = 1):
    """Color error inside the silhouettes and silhouette error, at full size or averaged over blur x blur."""
    rgb, alpha = colors[..., :3], alphas[..., 0]
    solid = masks.float()
    if blur > 1:
        def down(x):
            return F.avg_pool2d(x.movedim(-1, 1) if x.dim() == 4 else x[:, None], blur).movedim(1, -1).squeeze(-1)
        rgb, alpha, targets, solid = down(rgb), down(alpha), down(targets * solid[..., None]), down(solid)
        return ((rgb - targets) ** 2).mean() + 0.5 * ((alpha - solid) ** 2).mean()
    loss = ((rgb - targets) ** 2)[masks].mean()
    return loss + 0.5 * F.binary_cross_entropy(alpha.clamp(1e-5, 1 - 1e-5), solid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--hide-direction", type=int, default=None, help="leave this direction out of every frame")
    ap.add_argument("--hide-frames", choices=["odd"], default=None, help="leave every other frame out")
    ap.add_argument("--nodes", type=int, default=256, help="how many nodes move the Gaussians")
    ap.add_argument("--track-iters", type=int, default=800, help="iterations per frame while tracking")
    ap.add_argument("--refine-iters", type=int, default=3000, help="iterations of the joint refinement")
    ap.add_argument("--arap", type=float, default=0.1, help="weight of the nodes' rigidity")
    ap.add_argument("--matching", type=float, default=0.05,
                    help="weight of the pull toward each frame's own still (0 = images only)")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    device = torch.device("cuda")
    t_start = time.time()

    preset = PRESETS[args.preset]
    count = frame_count(args.mpq, preset)
    frames = list(range(0, count, 2)) if args.hide_frames == "odd" else list(range(count))
    split = "all" if args.hide_direction is None else "holdout:%d" % args.hide_direction
    test = "" if args.hide_direction is None and args.hide_frames is None else (
        "-hide%d" % args.hide_direction if args.hide_direction is not None else "-hideodd")
    out_dir = Path(args.out) / ("%s-motion%s" % (args.preset, test))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Every fitted frame as a still; frame 0 calibrates the camera, and the others share it.
    def still(k, camera=None):
        argv = ["--mpq", args.mpq, "--preset", args.preset, "--split", split, "--frame", str(k), "--model",
                "gaussians", "--tag", "motion-f%d%s" % (k, test), "--out", args.out, "--no-evaluate"]
        return fit.main(argv + (["--camera", str(camera)] if camera else []))

    still_scene, still_dir = still(0)
    stills = {0: still_scene.field}
    for k in frames[1:]:
        stills[k] = still(k, still_dir)[0].field
    elevation, offset, sign = still_scene.elevation, still_scene.offset, still_scene.sign
    train_dirs = still_scene.train
    palette = still_scene.palette

    all_views = {k: load_views(args.mpq, dataclasses.replace(preset, frame=k))[0] for k in range(count)}
    h, w = all_views[0][0].shape
    pivot = all_views[0][0].pivot
    yaws = sign * torch.tensor([v.yaw for v in all_views[0]], dtype=torch.float32, device=device)
    right, up, forward = camera_basis(yaws, elevation)
    viewmats = torch.stack([viewmat(right[d], up[d], forward[d]) for d in range(len(yaws))])
    K = intrinsics(pivot, offset, device)
    Ks = K[None].repeat(len(yaws), 1, 1)
    dirs = torch.tensor(train_dirs, device=device)

    def targets_of(k):
        views = [all_views[k][d] for d in train_dirs]
        masks = masks_for(views, preset.shadows, device)
        idx = [torch.as_tensor(v.indices, device=device).long().clamp(min=0) for v in views]
        return torch.stack([palette[i] for i in idx]), torch.stack([m == 1 for m in masks])

    def cloud(field):
        """The opaque Gaussians of a still: means and colors."""
        p = field.params
        keep = torch.sigmoid(p["opacities"]) > 0.5
        return p["means"][keep].detach(), torch.sigmoid(p["colors"][keep]).detach()

    model = MovingGaussians(still_scene.field, len(frames), nodes=args.nodes)
    print("%d Gaussians, %d nodes %.1f pixels apart" % (len(model.means0), args.nodes, model.spacing))

    def only_slot(j):
        """Zero the gradients of every frame's node poses but slot j's."""
        for p in (model.node_quats, model.node_moves):
            keep = torch.ones(p.shape[0], device=device, dtype=torch.bool)
            keep[j] = False
            p.grad[keep] = 0

    # 2. Tracking, frame by frame (slot j holds frame frames[j]).
    colors_now = torch.sigmoid(model.colors).detach()
    weight = torch.sigmoid(model.opacities).detach()
    for j in range(1, len(frames)):
        t0 = time.time()
        with torch.no_grad():
            model.node_quats[j] = model.node_quats[j - 1]
            model.node_moves[j] = model.node_moves[j - 1]
        targets, masks = targets_of(frames[j])
        target_means, target_colors = cloud(stills[frames[j]])
        pairs = None
        opt = torch.optim.Adam([{"params": [model.node_moves], "lr": 0.1}, {"params": [model.node_quats], "lr": 0.01}])
        for it in range(args.track_iters):
            colors, alphas, _ = model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)
            blur = 4 if it < args.track_iters // 3 else 2 if it < 2 * args.track_iters // 3 else 1
            loss = image_loss(colors, alphas, targets, masks, blur) + args.arap * model.arap(j)
            if args.matching:
                # The pull toward the frame's own still fades out, leaving the images the last word.
                if it % 20 == 0:
                    pairs = None
                means, _ = model.pose(j)
                match, pairs = matching(means, colors_now, weight, target_means, target_colors, pairs)
                loss = loss + args.matching * (1 - it / args.track_iters) * match
            opt.zero_grad()
            loss.backward()
            only_slot(j)
            opt.step()
        print("tracked frame %d (%d of %d): loss %.5f (%.0fs)" % (frames[j], j, len(frames) - 1, loss.item(),
                                                                   time.time() - t0))

    # 3. Joint refinement of every frame, the loop closed by the smoothness of the node paths.
    all_targets = [targets_of(k) for k in frames]
    opt = torch.optim.Adam([{"params": [model.node_moves], "lr": 0.02}, {"params": [model.node_quats], "lr": 0.002},
                            {"params": [model.means0], "lr": 0.005}, {"params": [model.quats0], "lr": 0.001},
                            {"params": [model.scales], "lr": 0.002}, {"params": [model.opacities], "lr": 0.01},
                            {"params": [model.colors], "lr": 0.01}])
    t0 = time.time()
    for it in range(args.refine_iters):
        j = it % len(frames)
        targets, masks = all_targets[j]
        colors, alphas, _ = model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)
        loss = image_loss(colors, alphas, targets, masks) + args.arap * model.arap(j) + 0.01 * model.smoothness()
        opt.zero_grad()
        loss.backward()
        opt.step()
        if it % 500 == 0 or it == args.refine_iters - 1:
            print("refine %5d  loss %.5f  (%.0fs)" % (it, loss.item(), time.time() - t0))

    # 4. Scores and pictures.
    candidates = torch.tensor(list(range(128, 255)) if preset.shadows else [0] + list(range(128, 255)), device=device)
    per_frame = len(frames) / count  # model slots per animation frame
    results = {"fitted": [], "hidden_direction": [], "hidden_frames": [], "hidden_frames_repeat_previous": []}
    with torch.no_grad():
        def render(frame_phase, d_yaw):
            r, u, f = (x[0] for x in camera_basis(torch.tensor([d_yaw], device=device), elevation))
            colors, alphas, _ = model.rasterize(frame_phase * per_frame, viewmat(r, u, f)[None], K[None], w, h)
            return quantize(colors[0, ..., :3], alphas[0, ..., 0], palette, candidates)

        def truth(k, d):
            v = all_views[k][d]
            idx = torch.as_tensor(v.indices, device=device).long()
            m = masks_for([v], preset.shadows, device)[0]
            return torch.where(m == 1, idx, torch.full_like(idx, -1))

        for k in range(count):
            for d in range(len(yaws)):
                s = score(render(k, float(yaws[d])), truth(k, d), palette)
                if d == args.hide_direction:
                    results["hidden_direction"].append(s)
                elif args.hide_frames and k % 2:
                    results["hidden_frames"].append(s)
                    results["hidden_frames_repeat_previous"].append(score(truth(k - 1, d), truth(k, d), palette))
                else:
                    results["fitted"].append(s)
        summary = {"preset": args.preset, "frames": count, "fitted_frames": frames, "directions": train_dirs,
                   "elevation_deg": math.degrees(float(elevation)), "gaussians": len(model.means0),
                   "nodes": args.nodes, "seconds": time.time() - t_start}
        for key, rows in results.items():
            if rows:
                summary[key] = {m: float(np.mean([r[m] for r in rows])) for m in rows[0]}
                print(key, json.dumps({m: round(v, 3) for m, v in summary[key].items()}))
        (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2))

        # 16 directions by twice the frames: originals where they exist and were fitted, the model elsewhere.
        pal = (palette.cpu().numpy() * 255).round().astype(np.uint8)
        sheet = []
        for step in range(2 * count):
            column = []
            for n in range(16):
                known = n % 2 == 0 and step % 2 == 0 and n // 2 != args.hide_direction and step // 2 in frames
                column.append(truth(step // 2, n // 2).cpu().numpy() if known
                              else render(step / 2, sign * n * 22.5).cpu().numpy())
            sheet.append(column)
        write_sheet(sheet, pal, out_dir / "sheet.png")
        write_gif(sheet, pal, out_dir / "directions.gif")
    torch.save({"model": model.state_dict(), "frames": frames}, out_dir / "motion.pt")
    print("wrote", out_dir, "(%.0fs)" % (time.time() - t_start))


if __name__ == "__main__":
    main()
