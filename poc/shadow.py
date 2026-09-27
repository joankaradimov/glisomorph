"""Baked shadows, and how new cells get theirs.

Diablo's character sprites carry their own shadow: solid palette index 0 on the ground, beside the
character. It isn't cast in 3D. Each one is the sprite's own outline in that direction, squashed to
a third of its height and sheared to the left, about a ground row (outline_shadow):

- a pixel h rows above the ground row goes to h/3 rows above it, and 0.26 h pixels to the left
  (then one pixel right and 1.75 up);
- the ground row is fixed for each direction of an animation: the lowest row of the outline in its
  first frame. When the feet move, the ground doesn't.

This reproduces the originals' shadows at 0.94 intersection over union for the warrior, rogue,
zombie and skeleton, and their walks and the warrior's attack, one rule for all. No 3D light comes
close (see Shadows in README.md). So a shadow says nothing about the shape that its own sprite
doesn't, and new cells get theirs by the same rule.
"""

import torch

from poc.reproject import neighbour

SQUASH = 1 / 3            # of the height above the ground row
SHEAR = 0.26              # pixels to the left per row of height
OFFSET = (1.0, -1.75)     # pixels right and down, after the squash and shear


def lowest_row(outline: torch.Tensor):
    """The lowest row (H, W bool) that the outline reaches, or None if it's empty: where a first frame's
    outline puts its direction's ground row."""
    rows = torch.nonzero(outline.any(1))
    return float(rows.max()) if len(rows) else None


def outline_shadow(outline: torch.Tensor, ground) -> torch.Tensor:
    """The shadow (H, W bool) that a sprite with this outline (H, W bool) carries, about the given
    ground row (see the module's docstring). It isn't drawn where the outline is: the sprite covers
    it. No shadow without a ground row."""
    shadow = torch.zeros_like(outline)
    if ground is None:
        return shadow
    ys, xs = torch.nonzero(outline, as_tuple=True)
    height = ground - ys.float()
    x = torch.round(xs + OFFSET[0] - SHEAR * height).long()
    y = torch.round(ground + OFFSET[1] - SQUASH * height).long()
    inside = (x >= 0) & (x < outline.shape[1]) & (y >= 0) & (y < outline.shape[0])
    shadow[y[inside], x[inside]] = True
    return shadow & ~outline


def baked_shadow(indices: torch.Tensor) -> torch.Tensor:
    """An original's shadow (H, W) bool: its index-0 pixels, without the black ones inside the model,
    which are part of its texture. The shadow lies on the ground, so it touches the background."""
    zero = indices == 0
    region = torch.zeros_like(zero)
    reach = indices < 0
    while True:
        grown = region | zero & (neighbour(reach, 0, False) | neighbour(reach, 1, False)
                                 | neighbour(reach, 2, False) | neighbour(reach, 3, False))
        if torch.equal(grown, region):
            return region
        region, reach = grown, grown


def iou(pred, target):
    """Intersection over union of masks (..., H, W) with a target (H, W)."""
    inter = (pred & target).sum((-2, -1)).float()
    union = (pred | target).sum((-2, -1)).float()
    return inter / union.clamp(min=1)
