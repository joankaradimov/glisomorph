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


def outline_shadow(outline: torch.Tensor, ground, scale: float = 1.0) -> torch.Tensor:
    """The shadow (H, W bool) that a sprite with this outline (H, W bool) carries, about the given
    ground row (see the module's docstring). It isn't drawn where the outline is: the sprite covers
    it. No shadow without a ground row. For a sprite drawn `scale` times larger, the offset grows
    with it (the squash and shear are ratios)."""
    shadow = torch.zeros_like(outline)
    if ground is None:
        return shadow
    ys, xs = torch.nonzero(outline, as_tuple=True)
    height = ground - ys.float()
    x = torch.round(xs + scale * OFFSET[0] - SHEAR * height).long()
    y = torch.round(ground + scale * OFFSET[1] - SQUASH * height).long()
    inside = (x >= 0) & (x < outline.shape[1]) & (y >= 0) & (y < outline.shape[0])
    shadow[y[inside], x[inside]] = True
    return shadow & ~outline


def baked_shadow(indices: torch.Tensor, margin: int = 3, search: int = 12, hidden=None) -> torch.Tensor:
    """An original's shadow (H, W) bool: its index-0 pixels, without the black ones inside the model,
    which are part of its texture. The shadow lies on the ground, so it touches the background; and it's
    where the shadow rule (outline_shadow) puts it, within `margin` pixels. Black texture that reaches
    the model's edge touches the background too (a strap across the back, a belt): fitted as shadow, the
    model would be transparent there.

    The rule's ground row is the lowest row of the animation's first frame, which one cell doesn't know:
    in a walk, the feet leave the ground. It's the row, within `search` of the cell's lowest, whose
    shadow best matches the index-0 pixels that touch the background. That's the first frame's ground
    row in all 856 cells of the warrior's, rogue's, zombie's and skeleton's animations in views.py.

    `hidden` (H, W) bool is what a spell's effect drawn over a cast hides (masks_for): the shadow may
    go on under it, and so may the body, whose hidden parts cast shadow too. Hidden pixels themselves
    are never shadow."""
    zero = indices == 0
    reach = indices < 0
    if hidden is not None:
        zero, reach = zero & ~hidden, reach | hidden
    region = torch.zeros_like(zero)
    while True:
        grown = region | zero & (neighbour(reach, 0, False) | neighbour(reach, 1, False)
                                 | neighbour(reach, 2, False) | neighbour(reach, 3, False))
        if torch.equal(grown, region):
            break
        region, reach = grown, grown
    body = (indices >= 0) & ~region
    outline = body
    if hidden is not None:
        body = body & ~hidden
        outline = body | hidden
    lowest = lowest_row(body)
    if lowest is None:
        return region
    shadows = [outline_shadow(outline, lowest + d) for d in range(-search, search + 1)]
    rule = max(shadows, key=lambda s: float(iou(s, region))).float()[None, None]
    near = torch.nn.functional.max_pool2d(rule, 2 * margin + 1, stride=1, padding=margin)[0, 0] > 0
    return region & near


def iou(pred, target):
    """Intersection over union of masks (..., H, W) with a target (H, W)."""
    inter = (pred & target).sum((-2, -1)).float()
    union = (pred | target).sum((-2, -1)).float()
    return inter / union.clamp(min=1)
