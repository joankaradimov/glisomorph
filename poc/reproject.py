"""Color a new view with the original sprites' pixels, using the reconstruction only for geometry.

For each pixel of the new view, the field gives the visible surface point. That point is projected
into the known directions, and takes the palette index of one that can see it (its depth there
matches). Colors therefore come straight from the artist's pixels: no blending and no
re-quantization.

Done pixel by pixel, that speckles: the field's depth is noisy at the scale of a pixel, so
neighbouring pixels fetch from scattered places, and they switch between directions at random.
`Warp` keeps the warp coherent:
- *Smoothing:* depth maps are replaced by robust local plane fits that stop at depth edges, so
  neighbouring pixels on one surface fetch neighbouring source pixels.
- *Costs:* each direction that sees a point has a cost. Farther directions cost more, and so do
  directions that shade the surface differently (the light turned with the camera).
- *Coherence:* inside a surface, neighbouring pixels also pay for using different directions, so
  that regions copy one direction each. Thin parts, a pixel or two wide, choose pixel by pixel.
"""

from dataclasses import dataclass

import torch
import torch.nn.functional as F


@dataclass
class Warp:
    """Settings of `reproject`. Warp.plain() fetches every pixel on its own, from the nearest direction
    that sees it."""
    depth: str = "median"     # which depth the field reports: "median" (half the opacity) or "expected"
    smooth: int = 2           # radius of the plane fits that smooth depth maps; 0 = depth as rendered
    coherence: float = 0.5    # cost of switching direction between neighbouring pixels inside a surface
    shading: float = 3.0      # cost of fetching a surface from a direction that shades it differently
                              # (it needs smoothing: the normals come from the plane fits)
    # The light, in camera space (x right, y up, z toward the camera). It turned with the camera, so each
    # direction lights a surface differently. Fits with a lighting model find about this for Diablo 1.
    light: tuple = (0.4, 0.75, 0.5)
    tolerance: float = 2.0    # how far (pixels) a point may be from a direction's depth and still be seen
    fill: int = 4             # pixels that no direction sees take a neighbour's color, up to this far in

    @classmethod
    def plain(cls) -> "Warp":
        return cls(depth="expected", smooth=0, coherence=0.0, shading=0.0, fill=0)


def _windows(x: torch.Tensor, radius: int) -> torch.Tensor:
    """(H, W) -> (K, H, W): x at every offset of a (2r+1) x (2r+1) window, row by row; 0 off the image."""
    k = 2 * radius + 1
    h, w = x.shape
    return F.unfold(F.pad(x[None, None], (radius,) * 4), k).view(k * k, h, w)


def _offsets(radius: int, device):
    """Row and column offsets (K, 1, 1) matching `_windows`."""
    r = torch.arange(-radius, radius + 1, device=device, dtype=torch.float32)
    rows, cols = torch.meshgrid(r, r, indexing="ij")
    return rows.reshape(-1, 1, 1), cols.reshape(-1, 1, 1)


def smooth_depth(depth: torch.Tensor, valid: torch.Tensor, radius: int, sigma: float = 1.0, iterations: int = 3):
    """Robust local plane fits to a depth map: smoothed depth, and its slopes per column and per row,
    each (H, W).

    At each pixel, a plane is fitted to the valid depths within `radius`, weighted by distance and by
    how well each depth agrees with the plane so far (a Gaussian of width `sigma` pixels). Depths of
    another surface, across an edge, get almost no weight, so edges stay sharp. Pixels that aren't
    valid themselves are filled from valid neighbours; NaN where there are none.
    """
    rows, cols = _offsets(radius, depth.device)
    near = torch.exp(-(rows ** 2 + cols ** 2) / (2 * radius ** 2))
    z = _windows(torch.where(valid, depth, torch.zeros_like(depth)), radius)
    ok = _windows(valid.float(), radius) * near
    # Start from each pixel's own depth, or, where it has none, from the median of its valid neighbours.
    median = torch.where(ok > 0, z, torch.full_like(z, float("nan"))).nanmedian(0).values
    plane = torch.where(valid, depth, median)
    slope_c = torch.zeros_like(depth)
    slope_r = torch.zeros_like(depth)
    for _ in range(iterations):
        guess = plane + slope_c * cols + slope_r * rows                    # (K, H, W)
        wt = ok * torch.exp(-((z - guess) / sigma) ** 2 / 2)
        wt = torch.nan_to_num(wt)
        dz = torch.nan_to_num(z - plane)                                    # fit residuals: better conditioned
        s = wt.sum(0)
        sc, sr = (wt * cols).sum(0), (wt * rows).sum(0)
        scc, scr, srr = (wt * cols * cols).sum(0), (wt * cols * rows).sum(0), (wt * rows * rows).sum(0)
        ridge = 1e-3 * s + 1e-6  # a plane with too few neighbours in one direction stays flat that way
        m = torch.stack([torch.stack([s + 1e-6, sc, sr], -1),
                         torch.stack([sc, scc + ridge, scr], -1),
                         torch.stack([sr, scr, srr + ridge], -1)], -2)      # (H, W, 3, 3)
        v = torch.stack([(wt * dz).sum(0), (wt * dz * cols).sum(0), (wt * dz * rows).sum(0)], -1)
        fit = torch.linalg.solve(m, v)
        some = s > 1e-4
        plane = torch.where(some, plane + fit[..., 0], plane)
        slope_c = torch.where(some, fit[..., 1], slope_c)
        slope_r = torch.where(some, fit[..., 2], slope_r)
    return plane, slope_c, slope_r


def source_depth(depth: torch.Tensor, valid: torch.Tensor, warp: Warp) -> torch.Tensor:
    """The depth map of a known direction, as `reproject` should see it: smoothed like the new view's,
    with pixels the field doesn't cover (`valid` False) filled from their neighbours."""
    if not warp.smooth:
        return depth
    return smooth_depth(depth, valid, warp.smooth)[0]


def neighbour(x: torch.Tensor, direction: int, outside=0) -> torch.Tensor:
    """x (..., H, W) at each pixel's right, left, lower or upper neighbour (direction 0-3); `outside`
    off the image."""
    out = torch.full_like(x, outside)
    if direction == 0:
        out[..., :, :-1] = x[..., :, 1:]
    elif direction == 1:
        out[..., :, 1:] = x[..., :, :-1]
    elif direction == 2:
        out[..., :-1, :] = x[..., 1:, :]
    else:
        out[..., 1:, :] = x[..., :-1, :]
    return out


def fetch(points: torch.Tensor, source: dict, tolerance: float):
    """Palette index (...) at the points' (..., 3) projections into a known direction, and whether that
    direction sees them."""
    h, w = source["indices"].shape
    col = torch.floor(points @ source["right"] + source["pivot"][0] + source["offset"][0]).long()
    row = torch.floor(source["pivot"][1] + source["offset"][1] - points @ source["up"]).long()
    inside = (col >= 0) & (col < w) & (row >= 0) & (row < h)
    col, row = col.clamp(0, w - 1), row.clamp(0, h - 1)
    index = source["indices"][row, col]
    seen = inside & (index >= 0) & ((points @ source["forward"] - source["depth"][row, col]).abs() < tolerance)
    return index, seen


def choose(cost: torch.Tensor, seen: torch.Tensor, links: torch.Tensor, coherence: float, iterations: int = 10):
    """A source per pixel (H, W), -1 where none sees it.

    Each pixel starts with its cheapest source among those that see it. Then iterated conditional
    modes evens the choice out: a pixel pays `coherence` for each linked neighbour (links: (4, H, W),
    to the right, left, lower and upper neighbour) that uses another source. Pixels are updated in a
    checkerboard, half at a time, so that neighbours don't flip back and forth together.
    """
    n, h, w = cost.shape
    cost = torch.where(seen, cost, torch.full_like(cost, float("inf")))
    labels = cost.argmin(0)
    if coherence > 0 and n > 1:
        links = links.float()
        degree = links.sum(0)
        yy, xx = torch.meshgrid(torch.arange(h, device=cost.device), torch.arange(w, device=cost.device),
                                indexing="ij")
        parity = (yy + xx) % 2
        for _ in range(iterations):
            for p in (0, 1):
                onehot = F.one_hot(labels, n).permute(2, 0, 1).float()
                agree = sum(neighbour(onehot, d) * links[d] for d in range(4))
                energy = cost + coherence * (degree - agree)
                labels = torch.where(parity == p, energy.argmin(0), labels)
    return torch.where(seen.any(0), labels, torch.full_like(labels, -1))


def fill(indices: torch.Tensor, wanted: torch.Tensor, steps: int) -> torch.Tensor:
    """Pixels in `wanted` without an index (-1) take a neighbour's, growing inwards one pixel per step."""
    out = indices.clone()
    for _ in range(steps):
        missing = wanted & (out < 0)
        if not missing.any():
            break
        before = out.clone()
        for d in range(4):
            other = neighbour(before, d, -1)
            take = missing & (other >= 0)
            out = torch.where(take, other, out)
            missing &= ~take
    return out


def _angle(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def reproject(target: dict, sources: list[dict], warp: Warp):
    """Palette indices (H, W), -1 where transparent or where no source sees the point, and the view
    of the source each index came from (H, W), -1 where none.

    target: origins (H, W, 3) on the plane through the world origin, depth (H, W) along forward (the
    kind `warp.depth` names), solid (H, W) bool, yaw, right, up and forward.
    sources: view, yaw, indices (h, w) long (-1 = not the model), depth (h, w) from `source_depth`,
    right, up, forward, pivot and offset.
    """
    solid = target["solid"]
    sources = sorted(sources, key=lambda s: _angle(s["yaw"], target["yaw"]))
    depth = target["depth"]
    if warp.smooth:
        depth, slope_c, slope_r = smooth_depth(depth, solid, warp.smooth)
    points = target["origins"] + depth[..., None] * target["forward"]
    fetched = [fetch(points, s, warp.tolerance) for s in sources]
    index = torch.stack([f[0] for f in fetched])                                  # (S, H, W)
    seen = torch.stack([f[1] for f in fetched]) & solid

    # Nearer directions cost less, in units of the nearest one's angle; ties are broken in order.
    angles = [_angle(s["yaw"], target["yaw"]) for s in sources]
    cost = torch.stack([torch.full_like(depth, a / max(angles[0], 1.0)) for a in angles])
    if warp.shading and warp.smooth:
        # How differently each direction shades the surface: the log of the change in diffuse shading,
        # with ambient light as strong as the direct light (as fits with a lighting model find). The
        # normals come from the plane fits' slopes (a row goes down).
        normal = F.normalize(-target["forward"] + slope_c[..., None] * target["right"]
                             - slope_r[..., None] * target["up"], dim=-1)
        light = F.normalize(torch.tensor(warp.light, device=depth.device, dtype=depth.dtype), dim=0)

        def shade(right, up, forward):
            return 1 + torch.relu(normal @ (light[0] * right + light[1] * up - light[2] * forward))

        here = shade(target["right"], target["up"], target["forward"])
        for k, s in enumerate(sources):
            cost[k] += warp.shading * torch.log(shade(s["right"], s["up"], s["forward"]) / here).abs()
    # Coherence links neighbours inside a surface: both seen, both with four solid neighbours, and
    # about as deep. A part a pixel or two wide has no inside; there, each pixel's own best direction
    # is the better guess.
    inside = seen.any(0)
    for d in range(4):
        inside = inside & neighbour(solid, d, False)
    links = torch.stack([inside & neighbour(inside, d, False)
                         & ((depth - neighbour(depth, d)).abs() < warp.tolerance) for d in range(4)])
    labels = choose(cost, seen, links, warp.coherence)

    picked = labels >= 0
    out = torch.full_like(labels, -1)
    out[picked] = index.gather(0, labels.clamp(min=0)[None])[0][picked]
    views = torch.tensor([s["view"] for s in sources], device=labels.device)
    origin = torch.where(picked, views[labels.clamp(min=0)], torch.full_like(labels, -1))
    return out, origin
