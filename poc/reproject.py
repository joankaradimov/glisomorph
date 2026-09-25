"""Color a new view with the original sprites' pixels, using the reconstruction only for geometry.

For each pixel of the new view, the field gives the visible surface point. That point is projected
into the known directions, nearest first, and takes the palette index of the first one that can
see it (its depth there matches). Colors therefore come straight from the artist's pixels: no
blending and no re-quantization.
"""

import torch


def reproject(points, valid, target_yaw, sources, tolerance: float = 2.0):
    """Palette indices (H, W), -1 where transparent or where no source sees the point.

    points: (H, W, 3) surface points of the new view; valid: (H, W) bool.
    sources: list of dicts with keys yaw, indices (h, w) long tensor (-1 = not model),
    depth (h, w), right, up, forward, pivot, offset.
    """
    out = torch.full(valid.shape, -1, dtype=torch.long, device=points.device)
    todo = valid.clone()

    def angle(s):
        d = abs(s["yaw"] - target_yaw) % 360
        return min(d, 360 - d)

    for s in sorted(sources, key=angle):
        if not todo.any():
            break
        p = points[todo]
        h, w = s["indices"].shape
        col = torch.floor(p @ s["right"] + s["pivot"][0] + s["offset"][0]).long()
        row = torch.floor(s["pivot"][1] + s["offset"][1] - p @ s["up"]).long()
        inside = (col >= 0) & (col < w) & (row >= 0) & (row < h)
        col, row = col.clamp(0, w - 1), row.clamp(0, h - 1)
        index = s["indices"][row, col]
        seen = inside & (index >= 0) & ((p @ s["forward"] - s["depth"][row, col]).abs() < tolerance)
        where = todo.nonzero(as_tuple=True)
        picked = (where[0][seen], where[1][seen])
        out[picked] = index[seen]
        todo[picked] = False
    return out
