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
whole limbs through a few nodes is far better posed than moving every Gaussian on its own. Long,
thin, straight parts, such as a sword, move as one rigid body instead, on a node of their own
(--rigid, the default): blended from several nodes, a blade bends. Once tracked, the nodes are tied
into the pieces they move as, a skeleton found from the motion (--skeleton), each moving by one rigid
motion, interpolated as one between frames.

1. Every frame is fitted like a still (fit.py --model gaussians); the stills are saved and reused.
   Frame 0 calibrates the camera, and its Gaussians become the moving ones; the other stills are
   targets.
2. Each next frame starts from the previous one's node poses and moves them to fit its views. Two
   things pull from afar, where the images' gradients don't reach: blurred copies of the images are
   compared first, and each Gaussian is drawn to where optimal transport takes the surface around it,
   from the model as it is to the surface of that frame's still (transported again now and then, as
   in ICP). Transport, unlike nearest neighbours, follows a sword through its swing; a rigid part
   jumps there at once.
3. The rest shape and the colors are then refitted to all frames at once, through the tracked
   motion: as parts move, the frames show them from more directions than frame 0 alone. With the
   lighting model (the default), colors are albedo, shaded by a light fixed to the camera, held where
   the voxel fits find it.

A phase between frames interpolates the node poses periodically (Catmull-Rom). A new cell of the
torus takes the artist's pixels (PixelCopier): its surface points are moved to nearby original frames
and directions, and copied from there, relit. Its shadow is made as the originals' were (shadow.py):
its own outline, squashed and sheared about its direction's ground row, found in frame 0.
--hide-direction and --hide-frames keep a direction or every other frame out of the fit, to score the
in-betweens against the originals.

Outputs, in out/<preset>-motion[-<test>][-<tag>]/: metrics.json, sheet.png (16 directions by twice the
frames, in the palette: the originals, and copied pixels over generated shadows in between),
directions.gif, motion.pt, with a test, hidden.npz (the hidden cells as generated), and with --scale S,
directions-<S>x.gif (every cell the model's, S times larger).
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
from poc.edges import clean_edges, edges_over_black
from poc.evaluate import quantize, score
from poc.field import camera_basis, pixel_rays
from poc.gaussians import DISTANCE, intrinsics, viewmat
from poc.ramps import Ramps
from poc.reproject import Warp, choose, fetch, fill, neighbour, smooth_depth, source_depth
from poc.scene import Scene, masks_for
from poc.shadow import baked_shadow, iou, lowest_row, outline_shadow
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


def quat_of_matrix(r):
    """The unit quaternion (w, x, y, z) of a rotation matrix (3, 3), by Shepperd's method: from its
    largest diagonal term, so that it holds for turns near half a turn too."""
    t = r[0, 0] + r[1, 1] + r[2, 2]
    i = int(torch.stack([t, r[0, 0], r[1, 1], r[2, 2]]).argmax())
    if i == 0:
        s = torch.sqrt(1 + t) * 2
        q = [s / 4, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
    elif i == 1:
        s = torch.sqrt(1 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
        q = [(r[2, 1] - r[1, 2]) / s, s / 4, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
    elif i == 2:
        s = torch.sqrt(1 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
        q = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, s / 4, (r[1, 2] + r[2, 1]) / s]
    else:
        s = torch.sqrt(1 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
        q = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, s / 4]
    return F.normalize(torch.stack(q), dim=0)


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


def opening(mask, size: int = 5):
    """A mask (H, W) opened by a size x size square: what remains of it where such a square fits inside
    (outside the image counts as empty)."""
    r = size // 2
    x = mask.float()[None, None]
    eroded = -F.max_pool2d(-F.pad(x, (r, r, r, r), value=0.0), size, stride=1)
    return F.max_pool2d(F.pad(eroded, (r, r, r, r), value=0.0), size, stride=1)[0, 0] > 0.5


def thin_pixels(mask, size: int = 5):
    """The pixels of a mask (H, W) in parts thinner than about `size`: what an opening removes."""
    return mask & ~opening(mask, size)


def rigid_parts(means, opacities, masks, viewmats, Ks, min_views: int, min_length: float = 15.0,
                link: float = 3.0):
    """Long, thin, straight parts of a still, such as a sword, as a part number per Gaussian (-1 for
    none). A part is a clump of Gaussians (linked within `link` pixels) whose centers fall on the
    originals' thin pixels (thin_pixels of each view's mask (H, W)) in at least `min_views` views, at
    least `min_length` pixels long and close to a straight line (off it by under a seventh of that)."""
    n = len(means)
    votes = torch.zeros(n, device=means.device)
    for mask, vm, K in zip(masks, viewmats, Ks):
        thin = thin_pixels(mask)
        cam = means @ vm[:3, :3].T + vm[:3, 3]  # orthographic: pixels from x and y alone
        x = torch.floor(K[0, 0] * cam[:, 0] + K[0, 2]).long()
        y = torch.floor(K[1, 1] * cam[:, 1] + K[1, 2]).long()
        inside = (x >= 0) & (x < mask.shape[1]) & (y >= 0) & (y < mask.shape[0])
        votes[inside] += thin[y[inside], x[inside]].float()
    idx = torch.nonzero((votes >= min_views) & (torch.sigmoid(opacities) > 0.05))[:, 0]
    parts = torch.full((n,), -1, dtype=torch.long, device=means.device)
    if len(idx) == 0:
        return parts
    pts = means[idx]
    near = torch.cdist(pts, pts) < link
    label = torch.arange(len(idx), device=means.device)
    while True:  # each clump takes its smallest member's number
        lower = torch.where(near, label[None, :], torch.full_like(near, len(idx), dtype=torch.long)).min(1).values
        if torch.equal(lower, label):
            break
        label = lower
    count = 0
    for clump in torch.unique(label):
        members = idx[label == clump]
        if len(members) < 50:
            continue
        p = means[members]
        axis = torch.linalg.svd(p - p.mean(0), full_matrices=False)[2][0]
        along = (p - p.mean(0)) @ axis
        length = float(along.max() - along.min())
        off = ((p - p.mean(0)) - along[:, None] * axis).norm(dim=-1).square().mean().sqrt()
        if length >= min_length and off < length / 7:
            parts[members] = count
            count += 1
    return parts


def rigid_residual(rest, posed):
    """How far points (P, 3) are from moving as one rigid body through frames (posed (F, P, 3)): how
    far the point that strays most is from the rigid motion that fits them best (Kabsch), in the frame
    where it strays most. (An RMS over a large group would let it swallow a small one that moves
    apart: the zombie's legs went into its body.)"""
    p = rest - rest.mean(0)
    q = posed - posed.mean(1, keepdim=True)
    u, _, vt = torch.linalg.svd(p.T[None] @ q)
    flip = torch.ones(len(q), 3, device=rest.device)
    flip[:, 2] = torch.sign(torch.det(vt.transpose(1, 2) @ u.transpose(1, 2)))
    rot = vt.transpose(1, 2) @ torch.diag_embed(flip) @ u.transpose(1, 2)
    return float(((p[None] @ rot.transpose(1, 2) - q) ** 2).sum(-1).sqrt().max())


def skeleton(model, slots: int, threshold: float):
    """The tracked nodes grouped into pieces that move rigidly together, a group per node (M,): a
    skeleton, found from the motion. Each node stands for 4 points (its center, and a node spacing
    along each axis, turned by its rotation); linked groups merge, the pair whose union fits one rigid
    motion best first (rigid_residual, over the slots), while that stays under `threshold` pixels. A
    limb splits where its nodes stop moving together, at a joint; a slow bend isn't chained into one
    piece, as each merge is checked as a whole."""
    with torch.no_grad():
        m = len(model.centers)
        axes = model.spacing * torch.cat([torch.zeros(1, 3, device=model.centers.device),
                                          torch.eye(3, device=model.centers.device)])
        rest = model.centers[:, None] + axes
        posed = []
        for k in range(slots):
            rot, move = model.node_pose(k)
            posed.append(quat_rotate(rot[:, None].expand(-1, 4, -1), axes.expand(m, 4, 3)) + (model.centers + move)[:, None])
        posed = torch.stack(posed)
    members = {i: [i] for i in range(m)}
    neighbours = {i: set() for i in range(m)}
    for i in range(m):
        for j in model.links[i].tolist():
            if i != j:
                neighbours[i].add(j)
                neighbours[j].add(i)
    costs = {}

    def cost(a, b):
        if (a, b) not in costs:
            nodes = members[a] + members[b]
            costs[a, b] = rigid_residual(rest[nodes].reshape(-1, 3), posed[:, nodes].reshape(slots, -1, 3))
        return costs[a, b]

    while True:
        pairs = [(cost(a, b), a, b) for a in members for b in neighbours[a] if a < b]
        if not pairs:
            break
        best, a, b = min(pairs)
        if best > threshold:
            break
        members[a] += members.pop(b)
        for n in neighbours.pop(b) - {a}:
            neighbours[n].discard(b)
            neighbours[n].add(a)
            neighbours[a].add(n)
        neighbours[a] -= {a, b}
        costs = {key: v for key, v in costs.items() if a not in key and b not in key}
    group = torch.zeros(m, dtype=torch.long, device=model.centers.device)
    for g, nodes in enumerate(sorted(members.values(), key=len, reverse=True)):
        group[nodes] = g
    return group


def average_down(colors, alpha, s: int):
    """A render s times finer, averaged over s x s blocks: colors with expected depth (C, H*s, W*s, k+1),
    premultiplied, and opacity (C, H*s, W*s, 1). Colors and opacity average plainly; depth is weighted
    by opacity, as it's an expectation over what the pixel covers."""
    if s == 1:
        return colors, alpha

    def pool(x):
        return F.avg_pool2d(x.permute(0, 3, 1, 2), s).permute(0, 2, 3, 1)

    a = pool(alpha)
    depth = pool(colors[..., -1:] * alpha) / a.clamp(min=1e-6)
    return torch.cat([pool(colors[..., :-1]), depth], -1), a


class MovingGaussians(torch.nn.Module):
    """Shared Gaussians (rest means and quaternions, log scales, opacity and color logits), moved by
    nodes with a unit quaternion and a translation each, per frame."""

    def __init__(self, still, frames: int, nodes: int = 256, bind: int = 4, links: int = 6, lit: bool = False,
                 supersample: int = 1, parts=None):
        super().__init__()
        # Each pixel the average of supersample x supersample samples, as the originals' pixels are
        # averages over the edges they partly cover and the colors that mix in them.
        self.supersample = supersample
        self.keep_samples = False
        p = still.params
        self.means0 = torch.nn.Parameter(p["means"].detach().clone())
        self.quats0 = torch.nn.Parameter(F.normalize(p["quats"].detach(), dim=-1))
        self.scales = torch.nn.Parameter(p["scales"].detach().clone())
        self.opacities = torch.nn.Parameter(p["opacities"].detach().clone())
        self.colors = torch.nn.Parameter(p["colors"].detach().clone())
        # Rigid parts (rigid_parts: a sword) move as one: each has a node of its own (after the others),
        # its Gaussians follow that node alone, the rest follow the others alone, and it's held to the
        # nodes around where it's gripped, as any node to its neighbours. Blended from several nodes
        # that turn apart, a blade bends; a hand partly following a sword that turns half a turn in a
        # frame tears.
        if parts is None:
            parts = torch.full((len(self.means0),), -1, dtype=torch.long, device=self.means0.device)
        self.register_buffer("parts", parts)
        n_parts = int(parts.max()) + 1
        with torch.no_grad():
            opaque = self.means0[(torch.sigmoid(self.opacities) > 0.3) & (parts < 0)]
            centers = opaque[farthest_points(opaque, nodes - n_parts)]
            # A part's node is where it's gripped: its point nearest the rest of the model.
            grips = [self.means0[parts == k][torch.cdist(self.means0[parts == k], opaque).min(1).values.argmin()]
                     for k in range(n_parts)]
            free_nodes = centers
            centers = torch.cat([centers] + [g[None] for g in grips])
            gaps = torch.cdist(centers, centers).topk(2, largest=False).values[:, 1]
            spacing = float(gaps.median())
            # Each Gaussian follows its nearest nodes, weighted by closeness.
            d, idx = torch.cdist(self.means0, free_nodes).topk(bind, largest=False)
            w = torch.exp(-d ** 2 / (2 * spacing ** 2)) + 1e-6
            rigid = parts >= 0
            idx[rigid] = (nodes - n_parts + parts[rigid])[:, None]
            w[rigid] = 1.0
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
        # Tied into a skeleton (tie), node_quats and node_moves are the pieces' instead, about their
        # centers, and each node takes its piece's.
        self.register_buffer("node_group", None)
        self.register_buffer("group_centers", None)
        # Small per-frame corrections of each Gaussian's position, on top of the nodes' motion, so that
        # each frame can match its views as closely as a still; and each Gaussian's nearest neighbours,
        # whose corrections should be alike.
        self.residuals = torch.nn.Parameter(torch.zeros((frames, len(self.means0), 3), device=centers.device))
        with torch.no_grad():
            near = [torch.cdist(chunk, self.means0).topk(5, largest=False).indices[:, 1:]
                    for chunk in torch.split(self.means0, 4096)]
        self.register_buffer("gaussian_links", torch.cat(near))
        # The lighting model, as field.py's LitVoxelField: colors become albedo, shaded by a light
        # fixed to the camera (x right, y up, z toward it), with an ambient term and a Blinn-Phong
        # highlight of per-Gaussian strength. The light is held where the voxel fits of Diablo's sprites
        # find it: fitted along with a color per Gaussian, it drifts anywhere, down to no light at all
        # (the colors can explain the shading), and relighting copied pixels suffers.
        self.lit = lit
        if lit:
            device = centers.device
            self.specular = torch.nn.Parameter(torch.full((len(self.means0),), -3.0, device=device))
            self.shininess_raw = torch.nn.Parameter(torch.tensor(math.log(16.0), device=device))
            self.register_buffer("light_dirs", torch.tensor([[0.4, 0.75, 0.5]], device=device))
            self.register_buffer("light_raw", torch.tensor([math.log(math.expm1(0.6))], device=device))
            self.register_buffer("ambient_raw", torch.tensor(math.log(math.expm1(0.6)), device=device))

    def node_pose(self, phase: float):
        """The nodes' unit quaternions (M, 4) and translations (M, 3) at a phase in model frames."""
        if float(phase).is_integer():
            k = int(phase) % self.node_quats.shape[0]
            rot, move = F.normalize(self.node_quats[k], dim=-1), self.node_moves[k]
        else:
            rot, move = (catmull_rom(F.normalize(self.node_quats, dim=-1), phase, quaternions=True),
                         catmull_rom(self.node_moves, phase))
        if self.node_group is None:
            return rot, move
        # Each node moves with its piece: turned about the piece's center, and carried along.
        g = self.node_group
        rot = rot[g]
        return rot, quat_rotate(rot, self.centers - self.group_centers[g]) + self.group_centers[g] + move[g] - self.centers

    def tie(self, groups):
        """Tie the nodes into rigid pieces (groups (M,), a piece per node: skeleton), each moving by one
        rigid motion per frame, at first the one that best fits its nodes' (Kabsch, on their centers and
        a spacing along each axis)."""
        with torch.no_grad():
            n = int(groups.max()) + 1
            device = self.centers.device
            counts = torch.bincount(groups, minlength=n).float()
            centers = torch.zeros((n, 3), device=device).index_add_(0, groups, self.centers) / counts[:, None]
            axes = self.spacing * torch.cat([torch.zeros(1, 3, device=device), torch.eye(3, device=device)])
            rest = self.centers[:, None] + axes
            frames = self.node_quats.shape[0]
            quats = torch.zeros((frames, n, 4), device=device)
            moves = torch.zeros((frames, n, 3), device=device)
            for k in range(frames):
                rot, move = self.node_pose(k)
                posed = quat_rotate(rot[:, None].expand(-1, 4, -1), axes.expand(len(rot), 4, 3)) + (self.centers + move)[:, None]
                for g in range(n):
                    p = rest[groups == g].reshape(-1, 3) - centers[g]
                    q = posed[groups == g].reshape(-1, 3)
                    pm, qm = p.mean(0), q.mean(0)
                    u, _, vt = torch.linalg.svd((p - pm).T @ (q - qm))
                    flip = torch.ones(3, device=device)
                    flip[2] = torch.sign(torch.det(vt.T @ u.T))
                    r = vt.T @ torch.diag(flip) @ u.T
                    quats[k, g] = quat_of_matrix(r)
                    moves[k, g] = qm - r @ pm - centers[g]  # posed = r (x - center) + center + move
        self.register_buffer("node_group", groups)
        self.register_buffer("group_centers", centers)
        self.node_quats = torch.nn.Parameter(quats)
        self.node_moves = torch.nn.Parameter(moves)

    def residual(self, phase: float):
        if float(phase).is_integer():
            return self.residuals[int(phase) % self.residuals.shape[0]]
        return catmull_rom(self.residuals, phase)

    def pose(self, phase: float):
        """The Gaussians' means (G, 3) and unit quaternions (G, 4) at a phase."""
        rot, move = self.node_pose(phase)
        idx, w = self.bind_idx, self.bind_w[..., None]
        offsets = self.means0[:, None] - self.centers[idx]
        means = (w * (quat_rotate(rot[idx], offsets) + self.centers[idx] + move[idx])).sum(1) + self.residual(phase)
        turns = rot[idx]
        turn = F.normalize((w * same_hemisphere(turns, turns[:, :1])).sum(1), dim=-1)
        return means, quat_multiply(turn, F.normalize(self.quats0, dim=-1))

    def highlight_parameters(self):
        return [self.specular, self.shininess_raw]

    def normals(self, quats, forward):
        """Unit normals (G, 3) of posed Gaussians: each one's thinnest axis, turned to face the camera."""
        axis = F.one_hot(self.scales.argmin(-1), 3).float()
        n = quat_rotate(quats, axis)
        return torch.where((n @ -forward)[:, None] < 0, -n, n)

    def shading(self, normals, right, up, forward):
        """Diffuse-plus-ambient factor (...,) and highlight (...,) for unit normals (..., 3), seen by a
        camera; the light turns with it."""
        cam = F.normalize(self.light_dirs, dim=-1)
        light = F.normalize(cam[:, :1] * right + cam[:, 1:2] * up - cam[:, 2:3] * forward, dim=-1)
        power = F.softplus(self.light_raw)
        diffuse = F.softplus(self.ambient_raw) + (power * torch.relu(normals @ light.t())).sum(-1)
        halfway = F.normalize(light - forward, dim=-1)
        highlight = (power * torch.relu(normals @ halfway.t()) ** torch.exp(self.shininess_raw)).sum(-1)
        return diffuse, highlight

    def rasterize(self, phase, viewmats, Ks, width, height):
        """Colors with expected depth (C, H, W, 4), opacity (C, H, W, 1) and gsplat's info, each pixel
        the average of supersample x supersample samples. With the lighting model, albedo, normal and
        highlight strength are rendered, then shaded per sample (deferred), before averaging; the
        pixels' normals are kept in last_normal (C, H, W, 3). With keep_samples, the samples' own colors
        (premultiplied) and opacity are kept in last_samples, before averaging."""
        s = self.supersample
        if s > 1:
            Ks = Ks.clone()
            Ks[:, :2] *= s  # s samples per world unit, the origin where it was
        means, quats = self.pose(phase)
        self.last_means = means  # for the transport's pull, without posing again
        common = dict(camera_model="ortho", render_mode="RGB+ED", packed=False)
        if not self.lit:
            out, alpha, info = rasterization(means, quats, torch.exp(self.scales), torch.sigmoid(self.opacities),
                                             torch.sigmoid(self.colors), viewmats, Ks, width * s, height * s, **common)
            if self.keep_samples:
                self.last_samples = (out[..., :3], alpha)
            return (*average_down(out, alpha, s), info)
        albedo = torch.sigmoid(self.colors)
        strength = torch.sigmoid(self.specular)[:, None]
        features = torch.stack([torch.cat([albedo, self.normals(quats, vm[2, :3]), strength], -1) for vm in viewmats])
        out, alpha, info = rasterization(means, quats, torch.exp(self.scales), torch.sigmoid(self.opacities),
                                         features, viewmats, Ks, width * s, height * s, **common)
        normal = F.normalize(out[..., 3:6], dim=-1)
        shaded = []
        for c, vm in enumerate(viewmats):
            diffuse, highlight = self.shading(normal[c], vm[0, :3], -vm[1, :3], vm[2, :3])
            shaded.append(out[c, ..., :3] * diffuse[..., None] + (out[c, ..., 6] * highlight)[..., None])
        if self.keep_samples:
            self.last_samples = (torch.stack(shaded), alpha)
        colors, alpha = average_down(torch.cat([torch.stack(shaded), out[..., 3:6], out[..., 7:8]], -1), alpha, s)
        self.last_normal = F.normalize(colors[..., 3:6], dim=-1)
        return torch.cat([colors[..., :3], colors[..., 6:7]], -1), alpha, info

    def rest_points(self, phase, viewmat_, K, width, height):
        """What each pixel shows at a phase, as a point of the rest pose (H, W, 3), with the opacity
        (H, W) and expected depth (H, W) there: the rest positions, rendered as colors."""
        s = self.supersample
        K = K.clone()
        K[:2] *= s
        means, quats = self.pose(phase)
        out, alpha, _ = rasterization(means, quats, torch.exp(self.scales), torch.sigmoid(self.opacities), self.means0,
                                      viewmat_[None], K[None], width * s, height * s, camera_model="ortho",
                                      render_mode="RGB+ED", packed=False)
        out, alpha = average_down(out, alpha, s)
        a = alpha[0, ..., 0]
        return out[0, ..., :3] / a.clamp(min=1e-6)[..., None], a, out[0, ..., 3] - DISTANCE

    def nodes_of(self, flat, where, part=None):
        """The nodes (P, bind) that points (P, 3) follow, with their weights (P, bind, 1): the nearest
        but the rigid parts', given where the nodes are (M, 3), weighted by closeness; a rigid part's
        points (part (...), -1 for none) follow its node alone."""
        free = len(self.centers) - int(self.parts.max()) - 1
        d, idx = torch.cat([torch.cdist(c, where[:free]) for c in torch.split(flat, 8192)]).topk(
            self.bind_idx.shape[1], largest=False)
        w = torch.exp(-d ** 2 / (2 * self.spacing ** 2)) + 1e-6
        if part is not None:
            part = part.reshape(-1)
            rigid = part >= 0
            idx[rigid] = (free + part[rigid])[:, None]
            w[rigid] = 1.0
        return idx, (w / w.sum(-1, keepdim=True))[..., None]

    def fit_parts(self, slot: int, goal):
        """Pose each rigid part's node at a slot by the rigid motion that best takes the part's Gaussians
        to where they should go (goal (G, 3)), weighted by opacity (Kabsch): a sword can turn half a turn
        between frames, far more than tracking turns a node by gradients."""
        n_parts = int(self.parts.max()) + 1
        free = len(self.centers) - n_parts
        with torch.no_grad():
            for k in range(n_parts):
                mine = self.parts == k
                c = self.centers[free + k]
                p, q = self.means0[mine] - c, goal[mine]
                w = torch.sigmoid(self.opacities[mine])[:, None]
                pm, qm = (w * p).sum(0) / w.sum(), (w * q).sum(0) / w.sum()
                u, _, vt = torch.linalg.svd(((p - pm) * w).T @ (q - qm))
                flip = torch.ones(3, device=p.device)
                flip[2] = torch.sign(torch.det(vt.T @ u.T))
                rot = vt.T @ torch.diag(flip) @ u.T
                # posed = rot (m - c) + c + move
                self.node_quats[slot, free + k] = quat_of_matrix(rot)
                self.node_moves[slot, free + k] = qm - rot @ pm - c

    def unpose_points(self, points, phase, part=None):
        """Points (..., 3) of the model posed at a phase, moved back to the rest pose: each by the
        inverse of its nearest nodes' poses, weighted by closeness to where those nodes are then (or a
        rigid part's, given which part each point is on). (The Gaussians' own per-frame corrections, a
        fraction of a pixel, are left out.)"""
        rot, move = self.node_pose(phase)
        posed = self.centers + move
        flat = points.reshape(-1, 3)
        idx, w = self.nodes_of(flat, posed, part)
        back = rot[idx] * torch.tensor([1.0, -1, -1, -1], device=rot.device)  # inverse rotations
        rest = (w * (quat_rotate(back, flat[:, None] - posed[idx]) + self.centers[idx])).sum(1)
        return rest.reshape(points.shape)

    def turn_at(self, rest, phase, part=None):
        """The blended rotation (..., 4) that the nodes near rest-pose points (..., 3) apply at a phase."""
        rot, _ = self.node_pose(phase)
        flat = rest.reshape(-1, 3)
        idx, w = self.nodes_of(flat, self.centers, part)
        turns = rot[idx]
        turn = F.normalize((w * same_hemisphere(turns, turns[:, :1])).sum(1), dim=-1)
        return turn.reshape(rest.shape[:-1] + (4,))

    def deform_points(self, rest, slot: int, nearest_gaussian=None, part=None):
        """Rest-pose points (..., 3) moved to a frame by the nodes, plus the per-frame correction of
        each point's nearest Gaussian (indices, if given)."""
        rot, move = self.node_pose(slot)
        flat = rest.reshape(-1, 3)
        idx, w = self.nodes_of(flat, self.centers, part)
        moved = (w * (quat_rotate(rot[idx], flat[:, None] - self.centers[idx]) + self.centers[idx] + move[idx])).sum(1)
        if nearest_gaussian is not None:
            moved = moved + self.residuals[slot][nearest_gaussian.reshape(-1)]
        return moved.reshape(rest.shape)

    def arap(self, slot: int):
        """As rigid as possible: where a node's pose puts each neighbouring node, against where that
        neighbour's own pose puts it (embedded deformation's regularizer), in node spacings."""
        rot, move = self.node_pose(slot)
        c, n = self.centers, self.links
        predicted = quat_rotate(rot[:, None].expand(-1, n.shape[1], -1), c[n] - c[:, None]) + c[:, None] + move[:, None]
        actual = c[n] + move[n]
        return (self.link_w * (predicted - actual).norm(dim=-1)).mean() / self.spacing

    def correction_cost(self, slot: int):
        """The per-frame corrections' size, and how much neighbouring Gaussians' differ (pixels squared)."""
        r = self.residuals[slot]
        return r.square().sum(-1).mean() + (r[self.gaussian_links] - r[:, None]).square().sum(-1).mean()

    def smoothness(self):
        """Node paths around the loop: squared second differences of translations and quaternions."""
        m = self.node_moves
        q = F.normalize(self.node_quats, dim=-1)
        accel = (m.roll(-1, 0) - 2 * m + m.roll(1, 0)).square().sum(-1).mean()
        qn, qp = same_hemisphere(q.roll(-1, 0), q), same_hemisphere(q.roll(1, 0), q)
        return accel + 100 * (qn - 2 * q + qp).square().sum(-1).mean()


class PixelCopier:
    """Colors a cell of the torus (a direction at a phase) with the artist's pixels. Each pixel's
    rest-pose point (MovingGaussians.rest_points) is moved to each nearby original frame, projected
    into its nearby directions, and takes the palette index there from one that sees it, as
    reproject.py does across directions alone: nearer frames and directions cost less, regions keep
    to one source, and shades are interpolated within the palette's ramps."""

    def __init__(self, model, sources, warp, ramps, slots: int):
        self.model, self.sources, self.warp, self.ramps, self.slots = model, sources, warp, ramps, slots

    def __call__(self, slot_phase, yaw, camera, own):
        """Palette indices (H, W) of the cell; `own` is the model's own colors, the fallback. With the
        model's lighting, each copied pixel is relit from its source's shading to this cell's, and
        sources that shade a point differently cost more (as reproject.py's shading cost)."""
        model, warp = self.model, self.warp
        right, up, forward, vm, K = camera
        h, w = own.shape
        rest, alpha, depth = model.rest_points(slot_phase, vm, K, w, h)
        if model.lit:
            model.rasterize(slot_phase, vm[None], K[None], w, h)
            normal = model.last_normal[0]
        solid = alpha >= 0.5
        if warp.smooth:
            depth = smooth_depth(depth, solid, warp.smooth)[0]

        def gap(a, b, period):
            d = abs(a - b) % period
            return min(d, period - d)

        angles = [gap(s["yaw"], yaw, 360.0) for s in self.sources]
        nearest_angle = max(min(angles), 1.0)
        costs = [a / nearest_angle + gap(s["slot"], slot_phase, self.slots) for s, a in zip(self.sources, angles)]
        chosen = sorted(range(len(self.sources)), key=lambda i: costs[i])[:6]
        # Each pixel's surface point, from the depth, moved back to the rest pose. (Rendering rest
        # positions as colors would give a wide Gaussian's center to every pixel it covers.) The
        # nearest Gaussian's per-frame correction is taken off here, and the source frame's added back.
        s0 = self.sources[0]
        scale = h // s0["indices"].shape[0]  # cells may be drawn larger than the originals
        posed = pixel_rays(h // scale, w // scale, s0["pivot"], s0["offset"], right, up, forward,
                           supersample=scale)[0] + depth[..., None] * forward
        rest = model.unpose_points(posed, slot_phase)
        near_gaussian = torch.zeros(solid.shape, dtype=torch.long, device=rest.device)
        part = None
        if solid.any():
            near_gaussian[solid] = nearest(rest[solid], model.means0)
            if (model.parts >= 0).any():
                # On a rigid part, a point follows the part's node, not the nodes nearest it; which
                # part, by the nearest Gaussian where the cell shows it, posed.
                means, _ = model.pose(slot_phase)
                near_posed = nearest(posed[solid], means)
                on_part = model.parts[near_posed] >= 0
                near_gaussian[solid] = torch.where(on_part, near_posed, near_gaussian[solid])
                part = torch.where(solid, model.parts[near_gaussian], torch.full_like(near_gaussian, -1))
            rest = model.unpose_points(posed - model.residual(slot_phase)[near_gaussian], slot_phase, part)
        points_by_slot, normals_by_slot = {}, {}
        if model.lit:
            here, _ = model.shading(normal, right, up, forward)
            turn_here = model.turn_at(rest, slot_phase, part)
        index, seen, shade, cost = [], [], [], []
        for i in chosen:
            s = self.sources[i]
            if s["slot"] not in points_by_slot:
                points_by_slot[s["slot"]] = model.deform_points(rest, s["slot"], near_gaussian, part)
                if model.lit:
                    # The surface's normal as it was in the source frame: turned by the nodes' motion.
                    relative = quat_multiply(model.turn_at(rest, s["slot"], part), turn_here * torch.tensor(
                        [1.0, -1, -1, -1], device=rest.device))
                    normals_by_slot[s["slot"]] = F.normalize(quat_rotate(relative, normal), dim=-1)
            idx, ok, lum = fetch(points_by_slot[s["slot"]], s, warp.tolerance, self.ramps)
            c = torch.full_like(depth, costs[i])
            if model.lit:
                there, _ = model.shading(normals_by_slot[s["slot"]], s["right"], s["up"], s["forward"])
                ratio = here / there.clamp(min=1e-3)
                lum = lum * ratio.clamp(0.5, 2.0)
                c = c + warp.shading * torch.log(ratio.clamp(min=1e-3)).abs()
            index.append(idx)
            seen.append(ok & solid)
            shade.append(lum)
            cost.append(c)
        index, seen, shade, cost = torch.stack(index), torch.stack(seen), torch.stack(shade), torch.stack(cost)
        inside = seen.any(0)
        for d in range(4):
            inside = inside & neighbour(solid, d, False)
        links = torch.stack([inside & neighbour(inside, d, False) & ((depth - neighbour(depth, d)).abs() < warp.tolerance)
                             for d in range(4)])
        labels = choose(cost, seen, links, warp.coherence)
        picked = labels >= 0
        out = torch.full_like(labels, -1)
        out[picked] = index.gather(0, labels.clamp(min=0)[None])[0][picked]
        lum = shade.gather(0, labels.clamp(min=0)[None])[0]
        out = torch.where(picked, self.ramps.nearest(out, lum), out)
        out = fill(out, solid, warp.fill)
        return torch.where(solid & (out < 0), own, torch.where(solid, out, torch.full_like(out, -1)))


def nearest(a, b):
    """For each row of a (Na, D), the index of the nearest row of b (Nb, D)."""
    return torch.cat([torch.cdist(chunk, b).argmin(-1) for chunk in torch.split(a, 4096)])


def surface_points(colors, alphas, origins, forward, color_scale: float = 60.0):
    """The surface that renders show, as points: for each pixel seen solid in each of C views, the point
    at its expected depth, with its color scaled into the same units (N, 6). colors (C, H, W, 4) hold
    premultiplied colors and expected depth, origins (C, H, W, 3) are the pixels' ray origins and
    forward (C, 3) the views' directions. Every pixel counts once, so a thin blade, made of many faint
    Gaussians, weighs as much as its pixels."""
    solid = alphas[..., 0] > 0.5
    points = origins + (colors[..., 3] - DISTANCE)[..., None] * forward[:, None, None]
    color = (colors[..., :3] / alphas.clamp(min=1e-6)).clamp(0, 1)
    return torch.cat([points, color_scale * color], -1)[solid]


def transport(x, y, rho: float = 1000.0, eps_start: float = 1024.0, eps_end: float = 4.0, iterations: int = 30):
    """Where each point of x (N, D) goes among the points of y (M, D) under unbalanced optimal
    transport with a squared-distance cost: its barycentric match (N, D). Unlike nearest neighbours,
    transport has to send each part somewhere with room for it, so a sword that swung far goes to where
    the sword is now, rather than to the body next to it. Solved by log-domain Sinkhorn iterations
    while the blur eps is annealed; rho is what creating or destroying mass costs, so that points
    without a counterpart (hidden in one frame, say) needn't go anywhere far."""
    cost = torch.cdist(x, y) ** 2 / 2
    log_a = torch.full((len(x),), -math.log(len(x)), device=x.device)
    log_b = torch.full((len(y),), -math.log(len(y)), device=x.device)
    f, g = torch.zeros_like(log_a), torch.zeros_like(log_b)
    eps = eps_start
    while True:
        tau = rho / (rho + eps)
        for _ in range(iterations):
            f = -tau * eps * torch.logsumexp(log_b + (g - cost) / eps, 1)
            g = -tau * eps * torch.logsumexp(log_a[:, None] + (f[:, None] - cost) / eps, 0)
        if eps <= eps_end:
            break
        eps = max(eps / 2, eps_end)
    return torch.softmax(log_a[:, None] + log_b + (f[:, None] + g - cost) / eps, 1) @ y


def follow(means, points, moves, k: int = 4):
    """Each Gaussian's share (G, 3) of a motion given at surface points (N, 3): the mean move of its k
    nearest points."""
    near = torch.cat([torch.cdist(c, points).topk(k, largest=False).indices for c in torch.split(means, 4096)])
    return moves[near].mean(1)


def sample_variation(rgb, alpha):
    """Total variation of samples' colors (C, h, w, 3), premultiplied, with their opacity (C, h, w, 1):
    the mean color jump (L1) between neighbouring samples where both are solid. As a prior, it favours
    flat patches of color between the edges the images demand, rather than each Gaussian a color of its
    own: a clean look at the samples' resolution (4x, sampled 4 x 4)."""
    u = rgb / alpha.clamp(min=0.25)
    solid = (alpha > 0.5).float()
    dy = (u[:, 1:] - u[:, :-1]).abs().sum(-1, keepdim=True) * solid[:, 1:] * solid[:, :-1]
    dx = (u[:, :, 1:] - u[:, :, :-1]).abs().sum(-1, keepdim=True) * solid[:, :, 1:] * solid[:, :, :-1]
    return (dy.sum() + dx.sum()) / solid.sum().clamp(min=1)


def coverage_variation(alpha):
    """Total variation of samples' coverage (C, h, w, 1), per solid sample: the outline's length against
    the area inside it. As a prior, it costs needles (much outline, little inside) more than a smooth
    outline."""
    dy = (alpha[:, 1:] - alpha[:, :-1]).abs().sum()
    dx = (alpha[:, :, 1:] - alpha[:, :, :-1]).abs().sum()
    return (dy + dx) / (alpha > 0.5).sum().clamp(min=1)


def color_smoothness(colors, neighbours):
    """The mean squared difference between each Gaussian's color (N, 3) and its neighbours' (N, k): as a
    prior, color varies smoothly between Gaussians, rather than each having its own. Along a thin part,
    a blade, the neighbours run along it."""
    return ((colors[:, None] - colors[neighbours]) ** 2).sum(-1).mean()


def neighbours_of(points, k: int):
    """For each point (N, 3), its k nearest other points (N, k)."""
    return torch.cat([torch.cdist(chunk, points).topk(k + 1, largest=False).indices[:, 1:]
                      for chunk in torch.split(points, 2048)])


def image_loss(colors, alphas, targets, masks, blur: int = 1, snap=None, keyed: bool = False):
    """Color error inside the silhouettes and silhouette error, at full size or averaged over blur x blur.
    At full size, as GaussianField.fit: with `snap` (the palette colors a pixel can snap to (K, 3) and a
    temperature), colors are fitted as they'll be snapped, so any color nearest the right palette color
    will do; with `keyed`, any opacity above a half is solid, and any below it transparent."""
    rgb, alpha = colors[..., :3], alphas[..., 0]
    solid = masks.float()
    if blur > 1:
        def down(x):
            return F.avg_pool2d(x.movedim(-1, 1) if x.dim() == 4 else x[:, None], blur).movedim(1, -1).squeeze(-1)
        rgb, alpha, targets, solid = down(rgb), down(alpha), down(targets * solid[..., None]), down(solid)
        return ((rgb - targets) ** 2).mean() + 0.5 * ((alpha - solid) ** 2).mean()
    if snap is None:
        loss = ((rgb - targets) ** 2)[masks].mean()
    else:
        palette, tau = snap
        color = rgb[masks] / alpha[masks].clamp(min=0.25)[:, None]  # snapped without the opacity
        classes = ((targets[masks][:, None] - palette) ** 2).sum(-1).argmin(1)  # each pixel's palette color
        loss = tau * F.cross_entropy(-((color[:, None] - palette) ** 2).sum(-1) / tau, classes)
    if keyed:
        alpha = torch.sigmoid((alpha - 0.5) * 12)  # past a half, little more pull either way
    return loss + 0.5 * F.binary_cross_entropy(alpha.clamp(1e-5, 1 - 1e-5), solid)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mpq", required=True, help="path to DIABDAT.MPQ")
    ap.add_argument("--preset", required=True, choices=sorted(PRESETS))
    ap.add_argument("--hide-direction", type=int, default=None, help="leave this direction out of every frame")
    ap.add_argument("--hide-frames", choices=["odd"], default=None, help="leave every other frame out")
    ap.add_argument("--nodes", type=int, default=256, help="how many nodes move the Gaussians")
    ap.add_argument("--lighting", default="phong", choices=["none", "phong"],
                    help="shade albedo with a light fixed to the camera (as fit.py), and relight copied pixels")
    ap.add_argument("--track-iters", type=int, default=800,
                    help="most iterations per frame while tracking, over its three stages of blur")
    ap.add_argument("--patience", type=int, default=50,
                    help="a stage of tracking ends once its image loss hasn't improved for this many iterations "
                         "(0 = every stage runs its full share)")
    ap.add_argument("--refine-iters", type=int, default=3000, help="iterations of the joint refinement")
    ap.add_argument("--arap", type=float, default=0.1, help="weight of the nodes' rigidity")
    ap.add_argument("--corrections", type=float, default=0.01,
                    help="with --refine all, the weight of the cost of per-frame corrections (0 = no corrections)")
    ap.add_argument("--matching", type=float, default=0.05,
                    help="weight of the pull toward where optimal transport takes the surface in each frame's "
                         "still (0 = images only)")
    ap.add_argument("--rematch", type=int, default=200, help="iterations between transports while tracking")
    ap.add_argument("--sinkhorn-iters", type=int, default=10,
                    help="Sinkhorn iterations per blur level of a transport (30 tracked no better)")
    ap.add_argument("--blurred-supersample", type=int, default=1,
                    help="samples per pixel side in tracking's blurred stages, where sub-pixel detail is blurred "
                         "away anyway (4 x 4 tracked no better, in twice the time)")
    ap.add_argument("--still-iters", type=int, default=1000,
                    help="iterations of the stills of frames other than the first, which only give the transport "
                         "its targets (0: fit.py's 2000, which did no better)")
    ap.add_argument("--refit-stills", action="store_true", help="fit the frames' stills again, even if saved")
    ap.add_argument("--supersample", type=int, default=4,
                    help="samples per pixel side: each pixel of the moving Gaussians the average of s x s (16 "
                         "gained nothing over 4)")
    ap.add_argument("--still-supersample", type=int, default=None,
                    help="samples per pixel side for the frames' stills (fit.py --supersample); by default as "
                         "--supersample, so that the moving Gaussians start from stills sampled alike")
    ap.add_argument("--refine", default="shape", choices=["colors", "shape", "all"],
                    help="what the joint refinement changes: the colors (and highlights) only; also the rest "
                         "shape, fitted to every frame through the tracked motion; or also the motion, the "
                         "opacities and per-frame corrections, which fit the known cells closer but copy worse")
    ap.add_argument("--tv", type=float, default=0.0,
                    help="in the refinement, weight of the samples' total variation (sample_variation): flat "
                         "patches of color between edges, for a clean look at the samples' resolution, 4x "
                         "(0: none; 0.005 suits the zombie)")
    ap.add_argument("--edges", default="black", choices=["black", "inside", "none"],
                    help="fit colors to the originals with their edges' share of the background they were drawn "
                         "over taken out (edges.py): redrawn over black, given an inside neighbour's color, or kept "
                         "('none'). Rendered larger, the model's edges then show no bluish rim. The copier keeps "
                         "the originals' edges: the sheet's new cells sit beside original ones")
    ap.add_argument("--outline-tv", type=float, default=0.0,
                    help="in the refinement, weight of the samples' coverage's total variation "
                         "(coverage_variation): smooth outlines, without needles (0: none)")
    ap.add_argument("--color-smooth", type=float, default=0.0,
                    help="in the refinement, weight of each Gaussian's albedo pulled toward its 8 nearest "
                         "Gaussians' (color_smoothness): even colors along thin parts (0: none)")
    ap.add_argument("--snap", type=float, default=0.0,
                    help="in the refinement, fit colors as they'll be snapped to the palette: cross-entropy over "
                         "its colors at this temperature (0: the squared distance to the pixel's palette color)")
    ap.add_argument("--keyed", action="store_true",
                    help="in the refinement, fit opacity as the sprites' 1-bit transparency (any above a half is "
                         "solid)")
    ap.add_argument("--rigid", action=argparse.BooleanOptionalAction, default=True,
                    help="find long, thin, straight parts in frame 0 (rigid_parts: a sword) and move each as one "
                         "rigid body, rather than bent by the several nodes its Gaussians would follow (the "
                         "default; --no-rigid bends them)")
    ap.add_argument("--skeleton", type=float, default=2.0,
                    help="after tracking, tie the nodes into pieces that move rigidly together (skeleton: no "
                         "node of a piece strays more than this many pixels from the piece's motion, in any "
                         "frame), then track each frame again, piece by piece (0: leave the nodes apart)")
    ap.add_argument("--load", default=None,
                    help="a saved motion.pt to score and draw again, instead of tracking and refining")
    ap.add_argument("--no-sheet", action="store_true", help="score, but skip the 16-direction sheet and GIF")
    ap.add_argument("--scale", type=int, default=1,
                    help="also draw the 16 directions by twice the frames this many times larger, as a GIF "
                         "(directions-<scale>x.gif)")
    ap.add_argument("--scale-colors", default="own", choices=["own", "copied"],
                    help="the larger cells' colors: the model's own, or copied pixels (from the originals with "
                         "their edges redrawn, as --edges)")
    ap.add_argument("--tag", default="", help="suffix for the output folder")
    ap.add_argument("--out", default="out")
    args = ap.parse_args()
    if args.still_supersample is None:
        args.still_supersample = args.supersample
    device = torch.device("cuda")
    t_start = time.time()

    preset = PRESETS[args.preset]
    count = frame_count(args.mpq, preset)
    frames = list(range(0, count, 2)) if args.hide_frames == "odd" else list(range(count))
    split = "all" if args.hide_direction is None else "holdout:%d" % args.hide_direction
    test = "" if args.hide_direction is None and args.hide_frames is None else (
        "-hide%d" % args.hide_direction if args.hide_direction is not None else "-hideodd")
    out_dir = Path(args.out) / ("%s-motion%s%s" % (args.preset, test, "-" + args.tag if args.tag else ""))
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Every fitted frame as a still; frame 0 calibrates the camera, and the others share it.
    def still(k, camera=None):
        iters = args.still_iters if k and args.still_iters else None
        tag = "motion-f%d%s%s%s%s" % (k, test, "-ss%d" % args.still_supersample if args.still_supersample != 1 else "",
                                      "-" + args.edges if args.edges != "none" else "", "-i%d" % iters if iters else "")
        folder = Path(args.out) / fit.run_name(args.preset, split, tag=tag, model="gaussians")
        if (folder / "scene.pt").exists() and not args.refit_stills:
            saved = Scene.load(folder / "scene.pt", args.mpq)
            if saved.supersample == args.still_supersample:  # else it was fitted otherwise
                return saved, folder
        argv = ["--mpq", args.mpq, "--preset", args.preset, "--split", split, "--frame", str(k), "--model",
                "gaussians", "--supersample", str(args.still_supersample), "--tag", tag, "--out", args.out,
                "--no-evaluate", "--edges", args.edges] + (["--iters", str(iters)] if iters else [])
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

    def model_indices(v, redraw=True):
        """A view's palette indices where the model is (-1 elsewhere: the background, a baked shadow), its
        edges redrawn under --edges (unless not to redraw)."""
        idx = np.where(masks_for([v], preset.shadows, device)[0].cpu().numpy() == 1, v.indices, -1)
        if args.edges == "none" or not redraw:
            return idx
        return (edges_over_black if args.edges == "black" else clean_edges)(idx, palette.cpu().numpy())

    def targets_of(k):
        views = [all_views[k][d] for d in train_dirs]
        masks = masks_for(views, preset.shadows, device)
        idx = [torch.as_tensor(model_indices(v), device=device).long().clamp(min=0) for v in views]
        return torch.stack([palette[i] for i in idx]), torch.stack([m == 1 for m in masks])

    origins = torch.stack([pixel_rays(h, w, pivot, offset, right[d], up[d], forward[d])[0] for d in train_dirs])

    def surface_of(colors, alphas):
        return surface_points(colors, alphas, origins, forward[dirs])

    parts = None
    if args.rigid:
        p = still_scene.field.params
        views0 = [all_views[0][d] for d in train_dirs]
        parts = rigid_parts(p["means"].detach(), p["opacities"].detach(), [m == 1 for m in masks_for(
            views0, preset.shadows, device)], viewmats[dirs], Ks[dirs], min_views=math.ceil(0.6 * len(train_dirs)))
        for k in range(int(parts.max()) + 1):
            print("rigid part %d: %d Gaussians" % (k, int((parts == k).sum())))
    model = MovingGaussians(still_scene.field, len(frames), nodes=args.nodes, lit=args.lighting != "none",
                            supersample=args.supersample, parts=parts)
    if args.load:
        saved = torch.load(args.load, map_location=device)["model"]
        saved.setdefault("parts", torch.full((len(model.means0),), -1, dtype=torch.long, device=device))
        if "node_group" in saved:
            model.tie(saved["node_group"])
        model.load_state_dict(saved)
    print("%d Gaussians, %d nodes %.1f pixels apart" % (len(model.means0), args.nodes, model.spacing))

    def only_slot(j):
        """Zero the gradients of every frame's node poses but slot j's."""
        for p in (model.node_quats, model.node_moves):
            keep = torch.ones(p.shape[0], device=device, dtype=torch.bool)
            keep[j] = False
            p.grad[keep] = 0

    # 2. Tracking, frame by frame (slot j holds frame frames[j]). Images only pull a Gaussian from a
    #    pixel or so away; a blade can swing tens of pixels between frames. So each Gaussian is also
    #    pulled to where optimal transport takes the surface around it, from the model as it is to the
    #    surface of the frame's own still, transported again every `rematch` iterations (as in ICP).
    still_surfaces = {}

    def still_surface(j):
        if j not in still_surfaces:
            with torch.no_grad():
                s = args.supersample  # the still sampled as the moving Gaussians are
                fine = Ks[dirs].clone()
                fine[:, :2] *= s
                colors, alphas, _ = stills[frames[j]].rasterize(viewmats[dirs], fine, w * s, h * s)
                still_surfaces[j] = surface_of(*average_down(colors, alphas, s))
        return still_surfaces[j]

    def transport_goal(j):
        """Where each Gaussian goes (G, 3) if it follows the surface around it, from the model posed in
        slot j to the surface of frame frames[j]'s still."""
        with torch.no_grad():
            here = surface_of(*model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)[:2])
            there = transport(here, still_surface(j), iterations=args.sinkhorn_iters)
            means, _ = model.pose(j)
            return means + follow(means, here[:, :3], there[:, :3] - here[:, :3])

    for j in range(1, 1 if args.load else len(frames)):  # a loaded model is tracked already
        t0 = time.time()
        with torch.no_grad():
            model.node_quats[j] = model.node_quats[j - 1]
            model.node_moves[j] = model.node_moves[j - 1]
        targets, masks = targets_of(frames[j])
        goal, jumped = None, ""
        opt = torch.optim.Adam([{"params": [model.node_moves], "lr": 0.1}, {"params": [model.node_quats], "lr": 0.01}])
        # Three stages, blurred by 4, 2 and 1 pixels. Each ends early once its image loss stops improving
        # (checked every 10 iterations), so that a frame that barely moves doesn't take as long as a swing.
        share, it = args.track_iters // 3, 0
        for stage, blur in enumerate((4, 2, 1)):
            best, stale = float("inf"), 0
            for step in range(share):
                if args.matching and it % args.rematch == 0:
                    model.supersample = args.supersample
                    goal = transport_goal(j)
                    if it == 0 and (model.parts >= 0).any():
                        # Where transport takes a rigid part, in one jump, if the images agree.
                        with torch.no_grad():
                            before = image_loss(*model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)[:2], targets, masks)
                            kept = model.node_quats[j].clone(), model.node_moves[j].clone()
                            model.fit_parts(j, goal)
                            after = image_loss(*model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)[:2], targets, masks)
                            if after > before:
                                model.node_quats[j], model.node_moves[j] = kept
                            else:
                                jumped = ", rigid parts jumped"
                model.supersample = args.supersample if blur == 1 else args.blurred_supersample
                colors, alphas, _ = model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)
                fit_loss = image_loss(colors, alphas, targets, masks, blur)
                loss = fit_loss + args.arap * model.arap(j)
                if goal is not None:
                    # The pull fades out over the stages as they'd run in full, leaving the images the
                    # last word; a last stage that ends early keeps up to a quarter of it.
                    means = model.last_means
                    fade = 1 - (stage + step / share) / 3
                    loss = loss + args.matching * fade * (means - goal).norm(dim=-1).mean()
                opt.zero_grad()
                loss.backward()
                only_slot(j)
                opt.step()
                it += 1
                if args.patience and step % 10 == 9:
                    value = fit_loss.item()
                    if value < best * (1 - 1e-3):
                        best, stale = value, 0
                    else:
                        stale += 10
                    if stale >= args.patience:
                        break
        print("tracked frame %d (%d of %d): loss %.5f, %d iterations%s (%.0fs)" % (
            frames[j], j, len(frames) - 1, loss.item(), it, jumped, time.time() - t0))
    model.supersample = args.supersample

    # With --skeleton, the nodes are then tied into the pieces they move as (skeleton), and each frame
    # is tracked again, piece by piece, from the pieces' fit to their nodes. Between frames a piece's
    # one rigid motion is interpolated, rather than each of its nodes' own.
    if args.skeleton and not args.load:
        groups = skeleton(model, len(frames), args.skeleton)
        model.tie(groups)
        sizes = torch.bincount(groups).tolist()
        print("skeleton: %d pieces (%d of more than one node); nodes per piece %s" % (
            len(sizes), sum(s > 1 for s in sizes), [s for s in sizes if s > 1]))
        for j in range(1, len(frames)):
            t0 = time.time()
            targets, masks = targets_of(frames[j])
            opt = torch.optim.Adam([{"params": [model.node_moves], "lr": 0.02}, {"params": [model.node_quats], "lr": 0.002}])
            best, stale = float("inf"), 0
            for step in range(args.track_iters // 3):
                colors, alphas, _ = model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)
                fit_loss = image_loss(colors, alphas, targets, masks)
                loss = fit_loss + args.arap * model.arap(j)
                opt.zero_grad()
                loss.backward()
                only_slot(j)
                opt.step()
                if args.patience and step % 10 == 9:
                    if fit_loss.item() < best * (1 - 1e-3):
                        best, stale = fit_loss.item(), 0
                    else:
                        stale += 10
                    if stale >= args.patience:
                        break
            print("tracked frame %d again, by pieces: loss %.5f, %d iterations (%.0fs)" % (
                frames[j], fit_loss.item(), step + 1, time.time() - t0))

    # 3. The rest shape and colors, refitted to every frame at once through the tracked motion: frame 0's
    #    still saw the model from 8 directions, but as parts move, the other frames show them from more.
    #    The motion stays as tracked, and the opacities as they were, so that nothing fades and every
    #    frame is the same shape moved. Refining the motion too (--refine all: the loop closed by the
    #    smoothness of the node paths, with the opacities and small per-frame corrections of each
    #    Gaussian) fits the known cells closer, but at the cost of consistency between frames, which
    #    copying pixels relies on; and a thin blade that's a pixel off in some frames fades out in all.
    all_targets = [targets_of(k) for k in frames]
    groups = [{"params": [model.colors], "lr": 0.01}]
    if model.lit:
        groups.append({"params": model.highlight_parameters(), "lr": 0.01})
    if args.refine != "colors":
        groups += [{"params": [model.means0], "lr": 0.005}, {"params": [model.quats0], "lr": 0.001},
                   {"params": [model.scales], "lr": 0.002}]
    if args.refine == "all":
        groups += [{"params": [model.node_moves], "lr": 0.02}, {"params": [model.node_quats], "lr": 0.002},
                   {"params": [model.opacities], "lr": 0.01}]
        if args.corrections:
            groups.append({"params": [model.residuals], "lr": 0.01})
    opt = torch.optim.Adam(groups)
    candidates = torch.tensor([0] + list(range(128, 255)), device=device)  # the indices sprites use
    snap = (palette[candidates], args.snap) if args.snap else None
    model.keep_samples = bool(args.tv or args.outline_tv)
    neighbours = None
    t0 = time.time()
    for it in range(0 if args.load else args.refine_iters):
        j = it % len(frames)
        targets, masks = all_targets[j]
        colors, alphas, _ = model.rasterize(j, viewmats[dirs], Ks[dirs], w, h)
        loss = image_loss(colors, alphas, targets, masks, snap=snap, keyed=args.keyed)
        if args.tv:
            loss = loss + args.tv * sample_variation(*model.last_samples)
        if args.outline_tv:
            loss = loss + args.outline_tv * coverage_variation(model.last_samples[1])
        if args.color_smooth:
            if it % 50 == 0:  # the rest shape moves as it's refined
                neighbours = neighbours_of(model.means0.detach(), 8)
            loss = loss + args.color_smooth * color_smoothness(torch.sigmoid(model.colors), neighbours)
        if args.refine == "shape":
            loss = loss + F.relu(model.scales - math.log(3.0)).square().mean()  # keep Gaussians small
        if args.refine == "all":
            loss = loss + args.arap * model.arap(j) + 0.01 * model.smoothness()
            if args.corrections:
                loss = loss + args.corrections * model.correction_cost(j)
        opt.zero_grad()
        loss.backward()
        opt.step()
        if it % 500 == 0 or it == args.refine_iters - 1:
            print("refine %5d  loss %.5f  (%.0fs)" % (it, loss.item(), time.time() - t0))
    model.keep_samples, model.last_samples = False, None

    # 4. Scores and pictures.
    per_frame = len(frames) / count  # model slots per animation frame
    results = {key: [] for key in ("fitted", "hidden_direction", "hidden_direction_copied", "hidden_frames",
                                   "hidden_frames_copied", "hidden_frames_repeat_previous")}
    shadow_scores = {"hidden_direction": [], "hidden_frames": []}
    hidden_cells = {}
    with torch.no_grad():
        def camera(d_yaw):
            r, u, f = (x[0] for x in camera_basis(torch.tensor([d_yaw], device=device), elevation))
            return r, u, f, viewmat(r, u, f), K

        def render(frame_phase, d_yaw):
            vm = camera(d_yaw)[3]
            colors, alphas, _ = model.rasterize(frame_phase * per_frame, vm[None], K[None], w, h)
            return quantize(colors[0, ..., :3], alphas[0, ..., 0], palette, candidates)

        # The originals the copier may take pixels from: every fitted frame in every fitted direction,
        # with the model's depth there for the visibility test.
        warp = Warp()
        sources = []
        for j, k in enumerate(frames):
            for d in train_dirs:
                r, u, f, vm, _ = camera(float(yaws[d]))
                _, alpha, depth = model.rest_points(j, vm, K, w, h)
                sources.append({"view": d, "slot": j, "yaw": float(yaws[d]), "right": r, "up": u, "forward": f,
                                "pivot": pivot, "offset": offset,
                                "indices": torch.as_tensor(model_indices(all_views[k][d], redraw=False),
                                                           device=device).long(),
                                "depth": source_depth(depth, alpha >= 0.5, warp)})
        copier = PixelCopier(model, sources, warp, Ramps(palette), len(frames))

        def copied(frame_phase, d_yaw, own=None):
            if own is None:
                own = render(frame_phase, d_yaw)
            return copier(frame_phase * per_frame, d_yaw, camera(d_yaw), own)

        # Shadows, made as the originals' were (shadow.py): a cell's own outline, squashed and sheared
        # about its direction's ground row, the lowest row of the direction's outline in frame 0 (an
        # original's where there is one, else the copied cell's). n counts the 16 directions from S.
        grounds = {}

        def ground_row(n):
            if n not in grounds:
                if n % 2 == 0 and n // 2 != args.hide_direction:
                    idx = torch.as_tensor(all_views[0][n // 2].indices, device=device).long()
                    grounds[n] = lowest_row((idx >= 0) & ~baked_shadow(idx))
                else:
                    grounds[n] = lowest_row(copied(0, sign * n * 22.5) >= 0)
            return grounds[n]

        def shadow_of(indices, n):
            return outline_shadow(indices >= 0, ground_row(n))

        def with_shadow(indices, n):
            """The cell as a sprite: its colors over its shadow (index 0)."""
            if not preset.shadows:
                return indices
            return torch.where(shadow_of(indices, n), torch.zeros_like(indices), indices)

        def shadow_match(k, d, indices):
            original = torch.as_tensor(all_views[k][d].indices, device=device).long()
            return float(iou(shadow_of(indices, 2 * d), baked_shadow(original)))

        def truth(k, d):
            v = all_views[k][d]
            idx = torch.as_tensor(v.indices, device=device).long()
            m = masks_for([v], preset.shadows, device)[0]
            return torch.where(m == 1, idx, torch.full_like(idx, -1))

        for k in range(count):
            for d in range(len(yaws)):
                own = render(k, float(yaws[d]))
                s = score(own, truth(k, d), palette)
                if d == args.hide_direction:
                    results["hidden_direction"].append(s)
                    cell = copied(k, float(yaws[d]), own)
                    results["hidden_direction_copied"].append(score(cell, truth(k, d), palette))
                    hidden_cells["f%d_d%d" % (k, d)] = cell.cpu().numpy().astype(np.int16)
                    if preset.shadows:
                        shadow_scores["hidden_direction"].append(shadow_match(k, d, cell))
                elif args.hide_frames and k % 2:
                    results["hidden_frames"].append(s)
                    cell = copied(k, float(yaws[d]), own)
                    results["hidden_frames_copied"].append(score(cell, truth(k, d), palette))
                    hidden_cells["f%d_d%d" % (k, d)] = cell.cpu().numpy().astype(np.int16)
                    if preset.shadows:
                        shadow_scores["hidden_frames"].append(shadow_match(k, d, cell))
                    results["hidden_frames_repeat_previous"].append(score(truth(k - 1, d), truth(k, d), palette))
                else:
                    results["fitted"].append(s)
        summary = {"preset": args.preset, "frames": count, "fitted_frames": frames, "directions": train_dirs,
                   "elevation_deg": math.degrees(float(elevation)), "gaussians": len(model.means0),
                   "nodes": args.nodes, "lighting": args.lighting, "seconds": time.time() - t_start}
        if model.lit:
            summary["light"] = {"direction_camera_space": F.normalize(model.light_dirs, dim=-1).tolist(),
                                "power": F.softplus(model.light_raw).tolist(),
                                "ambient": F.softplus(model.ambient_raw).item()}
            print("light (camera space):", json.dumps(summary["light"]))
        for key, rows in results.items():
            if rows:
                summary[key] = {m: float(np.mean([r[m] for r in rows])) for m in rows[0]}
                print(key, json.dumps({m: round(v, 3) for m, v in summary[key].items()}))
        if preset.shadows:
            for key, rows in shadow_scores.items():
                if rows:
                    summary[key + "_shadow_iou"] = float(np.mean(rows))
                    print(key, "shadow IoU %.3f" % summary[key + "_shadow_iou"])
        (out_dir / "metrics.json").write_text(json.dumps(summary, indent=2))
        if hidden_cells:  # the hidden cells as generated (copied pixels, no shadows), for a closer look
            np.savez_compressed(out_dir / "hidden.npz", **hidden_cells)

        # 16 directions by twice the frames: originals where they exist and were fitted (with their baked
        # shadows), copied pixels over generated shadows elsewhere.
        pal = (palette.cpu().numpy() * 255).round().astype(np.uint8)
        sheet = []
        for step in range(0 if args.no_sheet else 2 * count):
            column = []
            for n in range(16):
                known = n % 2 == 0 and step % 2 == 0 and n // 2 != args.hide_direction and step // 2 in frames
                if known:
                    column.append(all_views[step // 2][n // 2].indices.astype(np.int64))
                else:
                    cell = copied(step / 2, sign * n * 22.5)
                    column.append(with_shadow(cell, n).cpu().numpy())
            sheet.append(column)
        if sheet:
            write_sheet(sheet, pal, out_dir / "sheet.png")
            # Twice the frames at the game's speed: 25 ms each, which a GIF (in steps of 10 ms) shows as
            # 20 and 30 in turn.
            write_gif(sheet, pal, out_dir / "directions.gif", duration=[20, 30] * count)
        if args.scale > 1:
            # Larger, every cell is the model's: there are no originals at that size. One sample per
            # pixel, where that's the fit's own grid; copied pixels come from the originals with their
            # edges redrawn, as the colors were fitted, since a blended edge would show as a rim.
            S, fine = args.scale, model.supersample
            K_big = intrinsics(pivot, offset, device, S)
            model.supersample = max(1, fine // S)
            big_copier = PixelCopier(model, [dict(s, indices=torch.as_tensor(
                model_indices(all_views[frames[s["slot"]]][s["view"]]), device=device).long()) for s in sources],
                warp, Ramps(palette), len(frames))

            def big_cell(step, n):
                d_yaw = sign * n * 22.5
                r, u, f, vm, _ = camera(d_yaw)
                colors, alphas, _ = model.rasterize(step / 2 * per_frame, vm[None], K_big[None], w * S, h * S)
                own = quantize(colors[0, ..., :3], alphas[0, ..., 0], palette, candidates)
                if args.scale_colors == "own":
                    return own
                return big_copier(step / 2 * per_frame, d_yaw, (r, u, f, vm, K_big), own)

            big_grounds = {n: lowest_row(big_cell(0, n) >= 0) for n in range(16)}
            big = []
            for step in range(2 * count):
                column = []
                for n in range(16):
                    cell = big_cell(step, n)
                    if preset.shadows:
                        shade = outline_shadow(cell >= 0, big_grounds[n], scale=S)
                        cell = torch.where(shade, torch.zeros_like(cell), cell)
                    column.append(cell.cpu().numpy())
                big.append(column)
            model.supersample = fine
            write_gif(big, pal, out_dir / ("directions-%dx.gif" % S), scale=1, duration=[20, 30] * count, columns=4)
    torch.save({"model": model.state_dict(), "frames": frames}, out_dir / "motion.pt")
    print("wrote", out_dir, "(%.0fs)" % (time.time() - t_start))


if __name__ == "__main__":
    main()
