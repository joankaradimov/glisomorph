"""A variant's casting animation without its spells, cleaned in 2D from its three casts.

The players' fire, lightning and magic casts (plrgfx/<class>/<v>/<v>{fm,lm,qm}.cl2) are one motion with
three effects drawn over it (diablo1/overlays), each also lighting the body its own way. Where one cast's
effect hides the body, the others usually show it. Per frame and direction:

1. The fire and magic casts are moved onto the lightning cast, by the shift (up to SHIFT pixels) that best
   matches their silhouettes. In the armed warriors (wls, wla, whd, wmh, wht) they line up with each
   other as drawn, but mid-cast they drift from the lightning cast in a way no motion explains: about
   4.5 (1 - cos yaw) pixels to the left and 2 sin yaw down (yaw from S toward W), up to 9 facing N.
   Their 8 views are then one shape no longer (their visual hull covers about 0.85 of what they show,
   against 0.99 for the stand), while the lightning cast's are, with the stand's camera. (Other
   variants drift otherwise: wln's magic cast alone, wlb's casts by a motion. They'd want each cast
   moved on its own.)
2. Each cast's baked shadow counts as background: the shadow is drawn again at the end.
3. A cast is free at a pixel outside its effect grown by a pixel (an effect's blended edge). Where only
   one cast is free, it's trusted only where its own effect is at least LONE pixels away (an effect's dim
   edges reach past its overlay).
4. Body where at least as many free casts show the body as the background: thin parts survive a tie.
5. Its color: two casts that agree on it (exactly, or within TAU in every channel), outside their effects
   as drawn (effects never agree with each other, so their edges needn't be kept out); else the free
   cast whose effect is farthest (its light falls there least).
6. A cast alone is trusted only next to the body two casts agree on: an effect the overlay missed (a
   spark) shows where the other casts' effects hide the view.
7. Pixels no cast settles are filled from their neighbours, and pieces apart from the body are dropped.
8. The shadow is drawn by the rule (shadow.py), about each direction's ground row, the cleaned frame 0's.
"""

from functools import lru_cache

import numpy as np
import torch

from poc.shadow import baked_shadow, lowest_row, outline_shadow
from poc.views import CASTS, Preset, View, _grown, _shifted, load_views, spell_overlay

TAU = 24     # palette colors this close in every channel (0-255) agree
SHIFT = 10   # how far the fire and magic casts may drift from the lightning cast
LONE = 3     # how far a cast alone must be from its own effect
FAR = 40     # distances to effects are counted up to this


def _distance(mask: np.ndarray) -> np.ndarray:
    """Chessboard distance (H, W) to the nearest True pixel, up to FAR."""
    out = np.full(mask.shape, FAR, np.int16)
    out[mask] = 0
    reached = mask
    for r in range(1, FAR):
        grown = _grown(reached)
        if (grown == reached).all():
            break
        out[grown & ~reached] = r
        reached = grown
    return out


def _components(mask: np.ndarray) -> np.ndarray:
    """8-connected components of a bool mask (H, W): labels 1.., 0 outside."""
    labels = np.zeros(mask.shape, np.int32)
    n = 0
    for y, x in zip(*np.nonzero(mask)):
        if labels[y, x]:
            continue
        n += 1
        labels[y, x] = n
        stack = [(y, x)]
        while stack:
            a, b = stack.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    yy, xx = a + dy, b + dx
                    if 0 <= yy < mask.shape[0] and 0 <= xx < mask.shape[1] and mask[yy, xx] and not labels[yy, xx]:
                        labels[yy, xx] = n
                        stack.append((yy, xx))
    return labels


def _drift(idx: np.ndarray, effect: np.ndarray) -> tuple[int, int]:
    """The shift (dy, dx) that lays the fire and magic casts (idx[0], idx[2], as drawn) onto the lightning
    cast (idx[1]), both at once: their silhouettes' IoU where no effect is, grown by a pixel. (Counting
    the pixels that agree, background too, would favour no shift: a shift moves pixels out of view.)
    Index 0 is left out, a baked shadow mostly."""
    grown = [_grown(e) for e in effect]
    target = idx[1] > 0
    best, shift = -1.0, (0, 0)
    for sy in range(-SHIFT, SHIFT + 1):
        for sx in range(-SHIFT, SHIFT + 1):
            inter = union = 0
            for c in (0, 2):
                keep = ~grown[1] & ~_shifted(grown[c], sy, sx, True)
                a, b = _shifted(idx[c] > 0, sy, sx, False) & keep, target & keep
                inter += int((a & b).sum())
                union += int((a | b).sum())
            if inter / max(union, 1) > best:
                best, shift = inter / max(union, 1), (sy, sx)
    return shift


def _clean_direction(idx: np.ndarray, effect: np.ndarray, rgb_of: np.ndarray) -> np.ndarray:
    """One direction: the three casts' indices (3, H, W) and effects as drawn (3, H, W), fire and magic
    already moved. The cleaned indices (H, W), without a shadow (steps 2-7 of the module's docstring)."""
    blocked = np.stack([_grown(e) for e in effect])
    for c in range(3):
        shade = baked_shadow(torch.as_tensor(idx[c]).long(), hidden=torch.as_tensor(blocked[c])).numpy()
        idx[c][shade] = -1
    far = np.stack([_distance(e) for e in effect])
    rgb = rgb_of[idx.clip(0)]
    h, w = idx.shape[1:]
    out = np.full((h, w), -1, np.int16)
    settled = np.zeros((h, w), bool)
    agreed = np.zeros((h, w), bool)
    free = ~blocked
    free &= ~((free.sum(0) == 1)[None] & (far < LONE))
    opaque = free & (idx >= 0)
    body = free.any(0) & (opaque.sum(0) >= (free & (idx < 0)).sum(0))
    settled |= free.any(0) & ~body
    for i, j in ((1, 2), (0, 2), (0, 1)):  # lightning and magic first: the fire cast's body is lit apart
        near = np.abs(rgb[i] - rgb[j]).max(-1) <= TAU
        take = ~effect[i] & ~effect[j] & (idx[i] >= 0) & (idx[j] >= 0) & ~settled & ((idx[i] == idx[j]) | near)
        out[take] = idx[i][take]
        settled |= take
        agreed |= take
    take = body & ~settled
    pick = np.where(opaque, far, -1).argmax(0)
    out[take] = np.take_along_axis(idx, pick[None], 0)[0][take]
    lone = take & (opaque.sum(0) == 1) & ~_grown(_grown(agreed))
    settled |= take & ~lone
    out[lone] = -1
    unknown = ~settled
    while unknown.any():  # the most common value among settled neighbours, growing inward
        votes = {}
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy or dx:
                    value, known = _shifted(out, dy, dx, -1), _shifted(~unknown, dy, dx, False)
                    for v in np.unique(value[unknown & known]):
                        votes.setdefault(int(v), np.zeros((h, w), np.int16))
                        votes[int(v)] += (value == v) & known & unknown
        if not votes:
            break
        values = np.array(list(votes))
        counts = np.stack([votes[v] for v in values])
        fill = unknown & (counts.max(0) > 0)
        out[fill] = values[counts.argmax(0)][fill]
        unknown &= ~fill
    pieces = _components(out >= 0)
    if pieces.max() > 0:
        largest = np.bincount(pieces[pieces > 0]).argmax()
        near_body = _grown(_grown(pieces == largest))
        for p in np.unique(pieces[(pieces > 0) & (pieces != largest)]):
            if not (near_body & (pieces == p)).any():
                out[pieces == p] = -1
    return out


@lru_cache(maxsize=None)
def _cleaned(mpq_path: str, path: str, width: int, frame: int, pivot) -> tuple[np.ndarray, np.ndarray]:
    """Frame `frame` of the casts at `path` (with "{}" for fm, lm, qm): cleaned indices (8, H, W) without
    shadows, and the palette."""
    loaded = [load_views(mpq_path, Preset(path.format(c), width, "sheet", frame, True, pivot), grown=False)
              for c in CASTS]
    palette = loaded[0][1]
    rgb_of = (palette * 255).round().astype(np.int16)
    h = max(v.shape[0] for vs, _ in loaded for v in vs)
    out = []
    for d in range(len(loaded[0][0])):
        idx = np.full((3, h, width), -1, np.int16)
        effect = np.zeros((3, h, width), bool)
        for c, (vs, _) in enumerate(loaded):  # bottom-aligned, as the game draws them
            idx[c, h - vs[d].shape[0]:] = vs[d].indices
            if vs[d].ignore is not None:
                effect[c, h - vs[d].shape[0]:] = vs[d].ignore
        dy, dx = _drift(idx, effect)
        for c in (0, 2):
            idx[c], effect[c] = _shifted(idx[c], dy, dx, -1), _shifted(effect[c], dy, dx, True)
        out.append(_clean_direction(idx, effect, rgb_of))
    return np.stack(out), palette


def effect_pixels(preset: Preset) -> list[int]:
    """How many pixels the three casts' effects cover in each frame, over every direction: where they
    cover much, the cleaned frame is more reconstruction than original."""
    counts: list[int] = []
    for c in CASTS:
        overlay = spell_overlay(preset.path.format(c), preset.width)
        if overlay is None:
            continue
        for k in range(len(overlay[0])):
            n = sum(sum(p is not None for p in group[k].pixels) for group in overlay) * (8 // len(overlay))
            counts[k:k + 1] = [(counts[k] if k < len(counts) else 0) + n]
    return counts


def clean_casts(mpq_path: str, preset: Preset) -> tuple[list[View], np.ndarray]:
    """The views of frame preset.frame of a variant's casts (preset.path with "{}" for fm, lm, qm),
    cleaned of their spells, with shadows drawn by the rule; and the palette."""
    cleaned, palette = _cleaned(mpq_path, preset.path, preset.width, preset.frame, preset.pivot)
    first, _ = _cleaned(mpq_path, preset.path, preset.width, 0, preset.pivot)
    h, w = cleaned.shape[1:]
    views = []
    for d in range(len(cleaned)):
        indices = cleaned[d].copy()
        ground = lowest_row(torch.as_tensor(first[d] >= 0))
        indices[outline_shadow(torch.as_tensor(indices >= 0), ground).numpy()] = 0
        pivot = preset.pivot or (w / 2, h - 16)
        views.append(View(yaw=d * 360 / len(cleaned), indices=indices, pivot=pivot))
    return views, palette
