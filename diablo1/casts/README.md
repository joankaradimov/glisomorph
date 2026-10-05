# Casts without their spells

A player's three casting animations, `plrgfx/<class>/<v>/<v>fm.cl2` (fire), `lm.cl2` (lightning) and
`qm.cl2` (magic), are one motion with three effects drawn over it (see [the overlays](../overlays/README.md)).
This folder holds the motion on its own, without any effect. It was made by combining the three casts:
where one cast's effect hides the body, another usually shows it. It's for fitting a model to the cast
(see `poc/`), and a body to draw an effect over again.

It was made from `DIABDAT.MPQ`, for 16 of the warrior's 27 variants (see [The variants](#the-variants)
for which, and why not the others). The rest of this page describes the files, where they put the body,
and how they were made, in enough detail to make them again.

## Contents

| Path | Contents |
|------|----------|
| `warrior/<v>.cl2` | variant `<v>`'s casting animation without its spells, e.g. `warrior/wls.cl2` for the warrior in light armor with a sword |
| `drift.tsv` | per variant, frame and direction, the shift that moves each cast, and its overlay, onto it, and the casts left out |
| `README.md` | this page |

### The CL2 files

They're in the casts' own format (see [cl2.md](../docs/filespecs/cl2.md)): a sheet of 8 groups, the
directions in the game's order S, SW, W, NW, N, NE, E, SE, of 20 frames each, 96 pixels wide. The same
decoder reads them.

- **Pixels** are palette indices, as in the casts; every other pixel is transparent. Index 0 is the
  shadow, or black texture.
- **Anchoring** is the casts': a frame's bottom row is the cast frame's bottom row (the warrior's casts
  are 96 high). Frames are cut off above their topmost pixel, so heights vary.
- **The body** is where the variant's reference cast draws it: the cast that starts where the stand
  stands. The other casts draw it elsewhere in some variants: see [The drift](#the-drift).
- **The shadow** isn't the casts'. It's drawn by the rule in [shadow.py](../../poc/shadow.py): the body's
  outline in that frame and direction, squashed to a third of its height and sheared 0.26 pixels to the
  left per row, about a ground row, then moved a pixel right and 1.75 up. The ground row is the lowest
  row of the body in that direction's frame 0. As in the casts, the shadow runs off the canvas's left
  edge in some frames facing S, SW and SE. No body pixel touches an edge, but in `whs` and `whd`, frame 0
  facing SE, the sword's tip touches the left one, as it does in all three casts.

### drift.tsv

Tab-separated, one row per variant, frame and direction:

| Column | Meaning |
|--------|---------|
| `class`, `variant` | `warrior`, and the variant (`wln` ... `whh`) |
| `frame` | 0–19 |
| `direction` | `S`, `SW`, `W`, `NW`, `N`, `NE`, `E` or `SE` |
| `fm_dy`, `fm_dx`, `lm_dy`, `lm_dx`, `qm_dy`, `qm_dx` | the shift, in pixels down and to the right, that moves the fire, lightning and magic cast onto this sprite: 0 for the reference |
| `left_out` | the casts left out of this frame and direction, comma-separated (`fm`, `lm`, `qm`); empty if none |

To draw a cast's effect over this sprite, draw its overlay moved by that cast's shift.

## The drift

The three casts draw one motion, but not always in one place. In `wls`, the fire and magic casts line up
with each other, but they're drawn away from the lightning cast, further the further the direction is
from S. The gap grows over frames 2–9 and closes to a pixel by frame 19. From frame 9 to 15 it's 1 pixel
facing SW, 4 facing W, 7 facing NW, 9 facing N, 7–8 facing NE, 4–5 facing E and 2 facing SE, to the
left, and up to 2 pixels down or up. That's about 4.5 (1 − cos yaw) pixels to the left and 2 sin yaw
down, with the yaw counted from S toward W.

No motion does that. A body that moves shifts on screen, from one direction to the next, by a sinusoid
of the yaw that averages zero, so it can't move the picture 9 pixels facing N and none facing S. The 8
views of a fire or magic frame aren't one shape either. The visual hull carved from them with the
stand's camera covers only 0.8–0.9 of their pixels mid-cast. The stand's frames and the lightning
cast's get 0.99. Moved by about 4 pixels, the same in every direction, the fire and magic casts give
0.96–1.00. So the lightning cast is the one drawn where the camera sees the body. It's also the one
whose frame 0 lies where the stand's frame 0 does: their silhouettes match at 0.93, against 0.81 for
the fire cast and 0.80 for the magic one. A cast starts from the stand, so that's the cast the others
are laid onto, the reference, and it's not always the lightning cast:

| Variants | The casts |
|----------|-----------|
| `wls` `wld` `wla` `wlm` `wlh` `wlt`, `wms` `wmd` `wma` `wmm` `wmh` `wmt`, `whs` `whd` `wha` `whm` `whh` `wht` | as `wls`: the fire and magic casts drift together, up to 8–9 pixels, from the lightning cast, which is at the stand |
| `wlb` `wmb` `whb` | the fire and magic casts lie 3 pixels from the lightning cast in every frame, by a sinusoid of the yaw whose vertical part is 0.42 of its sideways one: the camera's foreshortening of a step aside. The lightning cast is at the stand (0.98 against 0.60 in `wlb`) |
| `wln` `wlu` | the fire and lightning casts lie up to 14 pixels from the magic cast (`wlu`: 15), all through. The magic cast is at the stand (0.83 against 0.37 in `wln`) |
| `wmu` | the magic cast lies 14 pixels from the other two, which are at the stand |
| `wmn` `whn` `whu` | within 2 pixels |

## How it was made

Per variant, frame and direction, the three casts were decoded and aligned by their bottom rows, as the
game draws them. Each cast's effect is the pixels of its overlay (its row of `../overlays/overlays.tsv`;
for `wls`: `warrior/fire-2`, `warrior/lightning-1` and `warrior/magic-1`).

1. **The reference.** It's the cast whose frame 0 matches the stand's frame 0 best, averaged over the
   8 directions: their silhouettes' intersection over union (opaque pixels other than index 0), counted
   outside the cast's effect grown by a pixel. The stand (`<v>as.cl2`) is drawn as the game draws it,
   bottom-aligned and centred. A cast without an overlay, whose effect can't be told from the body, is
   the reference only if it's nearer the stand than the others by 0.05.
2. **Laying on.** Each other cast is moved onto the reference, per frame and direction, by the shift
   (up to 16 pixels each way) whose silhouette overlaps the reference's most, as intersection over
   union, counted where neither's effect, grown by a pixel, is. A shift is taken only if it beats no
   shift by 0.01. Counting the pixels that agree, background included, picks no shift, since a shift
   moves pixels off the canvas.
3. **Matching.** How well a cast laid on matches the reference is the same intersection over union, but
   of the silhouettes' solid parts: opened by a pixel, so specks and lines under 3 pixels wide don't
   count. They're mostly an effect's sparks, particles and arcs that its overlay missed. Where a cast
   matches worse than 0.65, its shift is the nearest frame's that matches, in the same direction. Then
   each shift is replaced by the median over 5 frames (fewer at the first and last two), since a drift
   changes smoothly. Where a cast still matches worse than 0.65, it's left out of that frame and
   direction: its effect has a cloud its overlay lacks, or it's drawn in another pose.
4. **A cast without an overlay** counts only where another cast shows the body too, within a pixel;
   its other pixels are taken for its effect. Its background always counts, since an effect only adds
   pixels, and its colors come last in step 8.
5. **Shadows.** Each cast's baked shadow counts as background. That's its index-0 pixels that touch the
   background near where the shadow rule puts the shadow ([shadow.py](../../poc/shadow.py)'s
   `baked_shadow`, told that the body and its shadow may go on under the effect).
6. **Free casts.** A cast is free at a pixel outside its effect grown by a pixel, since an effect's edge
   is blended with what's under it. Where only one cast is free, it counts only at least 3 pixels from
   its own effect: an effect's dim edges reach past its overlay.
7. **Body or background.** It's body where at least as many free casts show the body as show the
   background, so thin parts survive a tie.
8. **Colors.** They come from two casts that agree (the same index, or colors within 24 in every RGB
   channel), both outside their effects as drawn. The pairs are tried in this order: lightning and magic,
   then fire and magic, then fire and lightning, since the fire cast's body is lit differently all
   through. Otherwise the color comes from the free cast whose effect is farthest, whose light falls
   there least.
9. **Single casts.** A pixel that only one cast shows is kept only within 2 pixels of pixels that two
   casts agree on. Elsewhere it's often an effect that its overlay missed, a spark, showing where the
   other casts' effects hide the view. A cast that draws no effect in that frame and direction has no
   sparks, and neither does the only cast left: they're kept.
10. **Gaps.** Pixels that none of this settles take the most common value among their settled
    neighbours, growing inward. Pieces farther than 2 pixels from the largest one are dropped.
11. **Shadow.** It's drawn by the rule (see [The CL2 files](#the-cl2-files)).

Over the 16 variants, 80.8% of the body's pixels are where two casts agree, 17.7% come from one cast,
and 1.55% are filled in step 10. The most filled is 9.7% of a frame, in frame 12 of `whd` and `wha`,
where all three effects are large.

[poc/casts.py](../../poc/casts.py) does this, and the preset `warrior-cast` in `poc/views.py` loads
`wls`. The files were written as the overlays are (see
[Writing the files](../overlays/README.md#writing-the-files)).

## The variants

A variant is here if each of its frames is one shape, nearly as much as its casts are, and its frames
look clean. The visual hull carved from a frame's 8 directions, with the stand's camera, must cover at
least 0.95 of their pixels, or no less than (within 0.01) its reference cast's own frame does, as drawn,
with its effect unknown. And frames 10, 12 and 13, where the effects are largest, must show no blobs or
remnants of an effect in any direction.

| Variant | Reference (its frame 0 at the stand) | Largest shift: fire, lightning, magic | Cells left out | Agree / one / filled | Most filled (frame) | Hull coverage, lowest (frame) | The reference cast's own, lowest |
|---|---|---|---|---|---|---|---|
| `wln` | magic (0.83) | 14, 14, 0 | 6 | 79.6 / 19.8 / 0.6% | 2.5% (11) | 0.979 (14) | 0.957 |
| `wls` | lightning (0.93) | 9, 0, 9 | 0 | 80.9 / 18.3 / 0.8% | 4.1% (11) | 0.980 (12) | 0.986 |
| `wld` | lightning (0.92) | 9, 0, 9 | 0 | 72.5 / 26.5 / 1.0% | 5.1% (13) | 0.974 (12) | 0.987 |
| `wla` | lightning (0.82) | 9, 0, 9 | 0 | 80.0 / 18.6 / 1.4% | 8.5% (12) | 0.957 (12) | 0.985 |
| `wlm` | lightning (0.88) | 9, 0, 9 | 0 | 81.3 / 17.4 / 1.3% | 8.2% (12) | 0.964 (12) | 0.984 |
| `wlh` | lightning (0.88) | 9, 0, 9 | 0 | 79.5 / 19.0 / 1.6% | 8.6% (12) | 0.961 (12) | 0.987 |
| `wms` | lightning (0.90) | 9, 0, 9 | 0 | 83.5 / 14.9 / 1.6% | 8.8% (12) | 0.966 (12) | 0.977 |
| `wmd` | lightning (0.93) | 9, 0, 9 | 0 | 80.9 / 17.2 / 1.9% | 9.0% (12) | 0.978 (12) | 0.979 |
| `wma` | lightning (0.84) | 9, 0, 9 | 0 | 80.4 / 17.8 / 1.8% | 9.3% (12) | 0.953 (12) | 0.977 |
| `wmm` | lightning (0.89) | 9, 0, 9 | 0 | 83.2 / 15.3 / 1.5% | 8.7% (12) | 0.968 (12) | 0.976 |
| `wmh` | lightning (0.86) | 9, 0, 9 | 0 | 85.6 / 12.8 / 1.6% | 8.4% (12) | 0.978 (12) | 0.978 |
| `whs` | lightning (0.84) | 9, 0, 9 | 0 | 82.7 / 15.6 / 1.7% | 8.1% (12) | 0.973 (12) | 0.983 |
| `whd` | lightning (0.83) | 9, 0, 9 | 0 | 78.3 / 19.7 / 2.0% | 9.7% (12) | 0.973 (12) | 0.985 |
| `wha` | lightning (0.85) | 9, 0, 9 | 0 | 82.0 / 16.1 / 1.9% | 9.7% (12) | 0.966 (12) | 0.983 |
| `whm` | lightning (0.90) | 9, 0, 9 | 0 | 80.4 / 17.8 / 1.8% | 8.2% (12) | 0.977 (12) | 0.981 |
| `whh` | lightning (0.91) | 9, 0, 9 | 0 | 81.5 / 16.5 / 2.0% | 9.3% (12) | 0.980 (12) | 0.985 |

The others aren't here:

| Variants | Why |
|----------|-----|
| `wlb` `wmb` `whb` `whn` `whu` | Their lightning cast has no overlay (see the overlays' [Limits](../overlays/README.md#limits)), and its arcs can't always be told from the body. In `wmb` and `whb` arcs and blobs are left mid-cast. In `whn` and `whu` frames 12–14 are less one shape than the casts (0.83–0.90 hull coverage, against 0.96–1.00). `wlb` comes closest: small blobs at the bow's lower tip in frame 13. |
| `wlt` `wmt` `wht` | Their lightning overlays miss many of the arcs around the staff (see *Staffs light up* in the overlays' Limits). Mid-cast (frames 10–15) they're less one shape than the casts (0.81–0.94 hull coverage, against 0.91–0.99), and facing E, where the other two casts don't match the lightning cast and are left out, the body breaks up. |
| `wlu` `wmn` `wmu` | In frames 12–13 they're less one shape than their reference cast as drawn: 0.93–0.95 hull coverage, against 0.96–0.99. They look clean but for a few red blobs on `wlu`'s shield. |

## What didn't work

- **Moving the lightning cast onto the magic cast, by up to 2 pixels,** scored by the pixels that agree.
  It favoured no shift, and the drift is longer anyway, so mid-cast frames mixed bodies from different
  places. They showed two blades side by side, and their 8 views were no shape: a visual hull covered
  0.61–0.67 of them in frames 8–14. A model fitted to them lost the raised sword.
- **Leaving the gaps unknown, or using the fire and magic casts alone,** helped little while the casts
  were misaligned.
- **Moving the fire and magic casts together onto the lightning cast,** this page's first method, made
  for `wls`. In `wln` and `wlu` the magic cast is the one at the stand, and in `wmu` it's the one that
  lies apart.
- **A shift of none where a cast doesn't match.** In `wlu` the fire and lightning casts lie 14 pixels
  away all through, but from frame 13 they matched worse than 0.65, held down by the magic cast's
  particles that its overlay misses. Unmoved, they were left out, the magic cast was left alone, and the
  gaps in it were filled: 30% of frame 16.
- **Matching the silhouettes as they are.** An effect's sparks, particles and arcs that its overlay
  misses left good casts out, and a cast alone with its effect: the lightning cast in 36 of `wlu`'s
  cells, and both others in some of the staffs'.
- **The lightning cast as the reference in `whn` and `whu`,** nearer the stand by 0.002 and 0.01 only:
  without an overlay, its arcs left the other two out in 22 to 80 cells.
- **A cast without an overlay that never decides alone.** Its background didn't count either where it
  was the only free cast, and where the other casts' effects hid the view, the gaps were filled with the
  body's colors: blobs around `wlb`'s bow, 4.8% of its body filled, against 2.9%.
- **Every single cast checked against the body two casts agree on.** In `wmu`, frames 3 and 4, its
  magic cast left out, the fire cast's ring hid the hips, so the lightning cast's were dropped, though
  it draws no effect yet. Cut off from the body, the legs were dropped with them.

## Limits

- **The effects' light.** Where one cast alone shows the body (17.7% of its pixels), its colors carry
  that cast's effect's light.
- **Gaps** are filled from neighbours' colors: 1.55% of the body is a guess, up to 9.7% of a frame.
- **The shadow** is the rule's, which matches the casts' at about 0.94 intersection over union, not the
  artist's.
- **16 variants of one class.** Those of the warrior's left out want better overlays (see
  [The variants](#the-variants)); the rogue and the sorcerer haven't been made.

## Checked

- **They decode back exactly** with [sprites.py](../sprites.py) to the frames that were encoded.
- **Each frame is one shape,** as [The variants](#the-variants) has it: the visual hull carved from its
  8 directions, with the `wls` stand's camera, covers 0.95–1.00 of their pixels. That camera fits every
  variant's stand: its frames get 0.99–1.00, but `wmh`'s 0.89.
- **A model fits `wls`.** `poc/motion.py`'s model of the stand, walk, attack, hit and this cast together
  matches it at 0.93 silhouette intersection over union and 40% exact pixels (the stand, in the same
  model: 0.95 and 47%), and each frame's own still at 0.99. It was fitted to the first `wls.cl2`, made
  with the fire and magic casts moved together: 4% of its pixels differ from this one's, where a cast
  lies a pixel apart in 25 of its 160 cells (the same hull coverage, 0.992, and 81% of the pixels where
  two casts agree).
- **Looked at:** every frame of `wls`; every variant's frames 10, 12 and 13, in every direction; frames
  across the cast of `wlb` and `wlu`; and the worst frames of those left out.
