"""A variant's casting animation without its spells, cleaned in 2D from its three casts.

The players' fire, lightning and magic casts (plrgfx/<class>/<v>/<v>{fm,lm,qm}.cl2) are one motion with
three effects drawn over it (diablo1/overlays), each also lighting the body its own way. Where one cast's
effect hides the body, the others usually show it. Per frame and direction:

1. The casts are laid onto one of them, the reference: the one whose frame 0 lies where the stand's frame
   0 does, since a cast starts from the stand. The others don't always draw the body there. In the armed
   warriors (wls, wla, whd, ...) the reference is the lightning cast, and mid-cast the fire and magic
   casts drift from it, together, in a way no motion explains: about 4.5 (1 - cos yaw) pixels to the left
   and 2 sin yaw down (yaw from S toward W), up to 9 facing N. Their 8 views are then one shape no longer
   (their visual hull covers about 0.85 of what they show, against 0.99 for the stand), while the
   lightning cast's are, with the stand's camera. In wln and wlu the reference is the magic cast, and the
   other two lie up to 14 pixels away all through. Each other cast is moved by the shift (up to SHIFT
   pixels) whose silhouette matches the reference's best where neither's effect is, if it beats no shift
   by MARGIN; then by the median of its shifts over WINDOW frames, since a drift changes smoothly. How well
   it matches is measured on the silhouettes' solid parts, without specks and thin lines: an effect's
   sparks, particles and arcs that its overlay missed. Where it doesn't match even at MATCH, its shift is
   the nearest frame's that does; and if it still doesn't match there (its effect has a cloud its overlay
   lacks, or it's drawn in another pose), it's left out.
2. A cast without an overlay (the warrior's lightning in wlb, wmb, whb, whn and whu) shows its effect as
   body. It's the reference only if it's nearer the stand than the others by PLAIN (in the bows, whose
   fire and magic casts lie 3 pixels away all through). Its pixels count only where another cast shows
   the body too (its background always counts: an effect only adds pixels), and its colors come last.
3. Each cast's baked shadow counts as background: the shadow is drawn again at the end.
4. A cast is free at a pixel outside its effect grown by a pixel (an effect's blended edge). Where only
   one cast is free, it's trusted only where its own effect is at least LONE pixels away (an effect's dim
   edges reach past its overlay).
5. Body where at least as many free casts show the body as the background: thin parts survive a tie.
6. Its color: two casts that agree on it (exactly, or within TAU in every channel), outside their effects
   as drawn (effects never agree with each other, so their edges needn't be kept out); else the free
   cast whose effect is farthest (its light falls there least).
7. A cast alone is trusted only next to the body two casts agree on: an effect the overlay missed (a
   spark) shows where the other casts' effects hide the view. A cast that draws no effect there, or the
   only cast left, is trusted.
8. Pixels no cast settles are filled from their neighbours, and pieces apart from the body are dropped.
9. The shadow is drawn by the rule (shadow.py), about each direction's ground row, the cleaned frame 0's.
"""

from functools import lru_cache

import numpy as np
import torch

from poc.shadow import baked_shadow, lowest_row, outline_shadow
from poc.views import CASTS, Preset, View, _grown, _shifted, frame_count, load_views, spell_overlay

TAU = 24       # palette colors this close in every channel (0-255) agree
SHIFT = 16     # how far a cast may lie from the reference
MARGIN = 0.01  # how much better than no shift a shift must match
MATCH = 0.65   # how well a cast, laid on, must match the reference to be used
WINDOW = 5     # frames in the median of a cast's shifts
PLAIN = 0.05   # how much nearer the stand a cast without an overlay must be to be the reference
LONE = 3       # how far a cast alone must be from its own effect
FAR = 40       # distances to effects are counted up to this
STAND = 96     # the stand's width: the warrior's, rogue's and sorcerer's (diablo1/docs/filespecs/sprite-metadata.md)

AGREED, ONE, FILLED = 1, 2, 3  # how a cleaned pixel was settled: two casts agree, one cast, its neighbours


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


def _iou(a: np.ndarray, b: np.ndarray, keep: np.ndarray) -> np.ndarray:
    """Intersection over union of bool masks a and b (..., H, W), counted where keep is."""
    return (a & b & keep).sum((-2, -1)) / np.maximum(((a | b) & keep).sum((-2, -1)), 1)


def _reference(mpq_path: str, path: str, width: int, solid: np.ndarray, effect: np.ndarray,
               overlaid: tuple[bool, ...]) -> tuple[int, np.ndarray]:
    """The cast whose frame 0 lies where the stand's frame 0 does, and per cast how well: their silhouettes'
    IoU outside its effect, as drawn (bottom-aligned and centred, each at its own width), averaged over the
    directions. A cast without an overlay, whose effect can't be told from the body, is the reference only
    if it's nearer the stand than the others by PLAIN. `solid` (3, 8, H, W) is the casts' frame 0 but
    index 0, `effect` its effects grown by a pixel."""
    views, _ = load_views(mpq_path, Preset(path.format("as"), STAND, "sheet", 0, True), grown=False)
    h, x = solid.shape[-2], (width - STAND) // 2
    stand = np.zeros(solid.shape[1:], bool)
    for d, v in enumerate(views):
        rows = min(h, v.shape[0])
        stand[d, h - rows:, x:x + STAND] = v.indices[-rows:] > 0
    scores = _iou(stand[None], solid, ~effect).mean(1)
    return int((scores - PLAIN * ~np.array(overlaid)).argmax()), scores


def _solid(mask: np.ndarray) -> np.ndarray:
    """A bool mask (..., H, W) opened by a pixel: specks and lines under 3 pixels wide are gone."""
    return _grown(~_grown(~mask))


def _matches(ref: np.ndarray, cast: np.ndarray, ref_effect: np.ndarray, effect: np.ndarray,
             shift: np.ndarray) -> np.ndarray:
    """How well a cast, moved by its shift (F, 8, 2), matches the reference, per frame and direction: their
    solid parts' IoU where neither's effect is. An effect's sparks, particles and arcs that its overlay
    missed are specks and thin lines; the body, a pose apart, or a cloud of mist isn't."""
    ref, cast = _solid(ref), _solid(cast)
    match = np.zeros(ref.shape[:2])
    for k, d in np.ndindex(*ref.shape[:2]):
        dy, dx = shift[k, d]
        match[k, d] = _iou(ref[k, d], _shifted(cast[k, d], dy, dx, False),
                           ~ref_effect[k, d] & ~_shifted(effect[k, d], dy, dx, True))
    return match


def _lay_on(ref: np.ndarray, cast: np.ndarray, ref_effect: np.ndarray, effect: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per frame and direction, the shift (dy, dx) that lays a cast onto the reference (step 1), and how well
    it matches there (_matches): `ref` and `cast` (F, 8, H, W) are pixels but index 0 (a baked shadow
    mostly), and their effects are grown by a pixel. The shift is the one whose silhouettes' IoU, where
    neither's effect is, is highest. (Counting the pixels that agree, background too, would favour no
    shift: a shift moves pixels out of view.)"""
    best = np.full(ref.shape[:2], -1.0)
    shift = np.zeros(ref.shape[:2] + (2,), np.int64)
    for dy in range(-SHIFT, SHIFT + 1):
        for dx in range(-SHIFT, SHIFT + 1):
            iou = _iou(ref, _shifted(cast, dy, dx, False), ~ref_effect & ~_shifted(effect, dy, dx, True))
            if (dy, dx) == (0, 0):
                unmoved = iou
            better = iou > best
            best[better], shift[better] = iou[better], (dy, dx)
    shift[best <= unmoved + MARGIN] = 0  # no better than none
    # where it doesn't match anyway, the shift is unknown: the nearest frame's that matches, in that direction
    known = _matches(ref, cast, ref_effect, effect, shift) >= MATCH
    for d in range(ref.shape[1]):
        good = np.nonzero(known[:, d])[0]
        for k in np.nonzero(~known[:, d])[0]:
            shift[k, d] = shift[good[np.abs(good - k).argmin()], d] if len(good) else 0
    n = len(shift)
    half = [min(WINDOW // 2, k, n - 1 - k) for k in range(n)]  # centred, narrower at the first and last frames
    shift = np.stack([np.median(shift[k - half[k]:k + half[k] + 1], 0) for k in range(n)]).round().astype(np.int64)
    return shift, _matches(ref, cast, ref_effect, effect, shift)


@lru_cache(maxsize=None)
def _layout(mpq_path: str, path: str, width: int, pivot):
    """A variant's three casts (`path` with "{}" for fm, lm, qm), all frames, and how they're laid on:
    their indices (3, F, 8, H, W), bottom-aligned as the game draws them; their effects as drawn
    (3, F, 8, H, W), and whether each has an overlay; each frame's height (its tallest cast's); the
    reference cast, and per cast how well its frame 0 matches the stand's; per cast, frame and direction,
    the shift (dy, dx) that lays it onto the reference and how well it matches there (step 1; the
    reference's are 0 and 1); and the palette."""
    n = frame_count(mpq_path, Preset(path.format(CASTS[0]), width, "sheet"))
    views = {}
    for c in CASTS:
        for k in range(n):
            views[c, k], palette = load_views(mpq_path, Preset(path.format(c), width, "sheet", k, True, pivot),
                                              grown=False)
    heights = np.array([max(v.shape[0] for c in CASTS for v in views[c, k]) for k in range(n)])
    h = heights.max()
    idx = np.full((3, n, 8, h, width), -1, np.int16)
    effect = np.zeros((3, n, 8, h, width), bool)
    for (c, k), vs in views.items():
        for d, v in enumerate(vs):
            idx[CASTS.index(c), k, d, h - v.shape[0]:] = v.indices
            if v.ignore is not None:
                effect[CASTS.index(c), k, d, h - v.shape[0]:] = v.ignore
    overlaid = tuple(spell_overlay(path.format(c), width) is not None for c in CASTS)
    solid, grown = idx > 0, _grown(effect)
    ref, at_stand = _reference(mpq_path, path, width, solid[:, 0], grown[:, 0], overlaid)
    shift = np.zeros((3, n, 8, 2), np.int64)
    match = np.ones((3, n, 8))
    for c in range(3):
        if c != ref:
            shift[c], match[c] = _lay_on(solid[ref], solid[c], grown[ref], grown[c])
    return idx, effect, overlaid, heights, ref, at_stand, shift, match, palette


def _clean_direction(idx: np.ndarray, effect: np.ndarray, rgb_of: np.ndarray,
                     overlaid: tuple[bool, ...]) -> tuple[np.ndarray, np.ndarray]:
    """One direction: the three casts' indices (3, H, W) and effects (3, H, W), laid on, a cast left out
    all effect, and which casts have an overlay. The cleaned indices (H, W) without a shadow (steps 3-8 of
    the module's docstring), and how each pixel was settled (AGREED, ONE, FILLED; 0 for background)."""
    blocked = np.stack([_grown(e) for e in effect])
    for c in range(3):
        shade = baked_shadow(torch.as_tensor(idx[c]).long(), hidden=torch.as_tensor(blocked[c])).numpy()
        idx[c][shade] = -1
    far = np.stack([_distance(e) for e in effect])
    rgb = rgb_of[idx.clip(0)]
    h, w = idx.shape[1:]
    out = np.full((h, w), -1, np.int16)
    how = np.zeros((h, w), np.int8)
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
        out[take], how[take] = idx[i][take], AGREED
        settled |= take
        agreed |= take
    take = body & ~settled
    # a cast without an overlay may show its effect over the body: its color comes last
    pick = np.where(opaque, np.where(np.array(overlaid)[:, None, None], far, 0), -1).argmax(0)
    out[take], how[take] = np.take_along_axis(idx, pick[None], 0)[0][take], ONE
    if (~effect.all((1, 2))).sum() > 1:  # with one cast left, there's nothing to agree with
        sparks = np.array([e.any() for e in effect])[pick]  # a cast that draws no effect here has no sparks
        lone = take & (opaque.sum(0) == 1) & ~_grown(_grown(agreed)) & sparks
        settled |= take & ~lone
        out[lone], how[lone] = -1, 0
    else:
        settled |= take
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
        how[fill & (out >= 0)] = FILLED
        unknown &= ~fill
    pieces = _components(out >= 0)
    if pieces.max() > 0:
        largest = np.bincount(pieces[pieces > 0]).argmax()
        near_body = _grown(_grown(pieces == largest))
        for p in np.unique(pieces[(pieces > 0) & (pieces != largest)]):
            if not (near_body & (pieces == p)).any():
                out[pieces == p], how[pieces == p] = -1, 0
    return out, how


@lru_cache(maxsize=None)
def _cleaned(mpq_path: str, path: str, width: int, frame: int, pivot) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Frame `frame` of the casts at `path` (with "{}" for fm, lm, qm): cleaned indices (8, H, W) without
    shadows, how each pixel was settled (8, H, W), and the palette."""
    every, effects, overlaid, heights, _, _, shift, match, palette = _layout(mpq_path, path, width, pivot)
    rgb_of = (palette * 255).round().astype(np.int16)
    h = heights[frame]
    out, how = [], []
    for d in range(every.shape[2]):
        idx, effect = every[:, frame, d, -h:].copy(), effects[:, frame, d, -h:].copy()
        for c in range(3):
            dy, dx = shift[c, frame, d]
            idx[c], effect[c] = _shifted(idx[c], dy, dx, -1), _shifted(effect[c], dy, dx, True)
            if match[c, frame, d] < MATCH:
                effect[c] = True  # left out
        kept = [c for c in range(3) if not effect[c].all()]
        for c in kept:
            if not overlaid[c] and len(kept) > 1:  # its effect: whatever no other cast shows (step 2)
                shown = np.zeros(effect[c].shape, bool)
                for o in kept:
                    if o != c:
                        shown |= (idx[o] > 0) & ~_grown(effect[o])
                effect[c] = (idx[c] > 0) & ~_grown(shown)
        o, settled = _clean_direction(idx, effect, rgb_of, overlaid)
        out.append(o)
        how.append(settled)
    return np.stack(out), np.stack(how), palette


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
    cleaned, _, palette = _cleaned(mpq_path, preset.path, preset.width, preset.frame, preset.pivot)
    first, _, _ = _cleaned(mpq_path, preset.path, preset.width, 0, preset.pivot)
    h, w = cleaned.shape[1:]
    views = []
    for d in range(len(cleaned)):
        indices = cleaned[d].copy()
        ground = lowest_row(torch.as_tensor(first[d] >= 0))
        if ground is not None:
            ground += h - first.shape[1]  # both frames are drawn from their bottom row
        indices[outline_shadow(torch.as_tensor(indices >= 0), ground).numpy()] = 0
        pivot = preset.pivot or (w / 2, h - 16)
        views.append(View(yaw=d * 360 / len(cleaned), indices=indices, pivot=pivot))
    return views, palette
