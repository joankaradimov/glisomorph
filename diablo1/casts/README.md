# Casts without their spells

A player's three casting animations, `plrgfx/<class>/<v>/<v>fm.cl2` (fire), `lm.cl2` (lightning) and
`qm.cl2` (magic), are one motion with three effects drawn over it (see [the overlays](../overlays/README.md)).
This folder holds the motion on its own, without any effect. It was made by combining the three casts:
where one cast's effect hides the body, another usually shows it. It's for fitting a model to the cast
(see `poc/`), and a body to draw an effect over again.

It was made from `DIABDAT.MPQ`, for the warrior with a sword (`wls`) only. The rest of this page
describes the file, where it puts the body, and how it was made, in enough detail to make it again.

## Contents

| Path | Contents |
|------|----------|
| `warrior/wls.cl2` | `wls`'s casting animation without its spells |
| `drift.tsv` | per frame and direction, the shift that moves the fire and magic casts, and their overlays, onto it |
| `README.md` | this page |

### The CL2 file

It's in the casts' own format (see [cl2.md](../docs/filespecs/cl2.md)): a sheet of 8 groups, the
directions in the game's order S, SW, W, NW, N, NE, E, SE, of 20 frames each, 96 pixels wide. The same
decoder reads it.

- **Pixels** are palette indices, as in the casts; every other pixel is transparent. Index 0 is the
  shadow, or black texture.
- **Anchoring** is the casts': a frame's bottom row is the cast frame's bottom row (`wls`'s casts are 96
  high). Frames are cut off above their topmost pixel, so heights vary.
- **The body** is where the lightning cast draws it. The fire and magic casts draw it elsewhere mid-cast:
  see [The drift](#the-drift).
- **The shadow** isn't the casts'. It's drawn by the rule in [shadow.py](../../poc/shadow.py): the body's
  outline in that frame and direction, squashed to a third of its height and sheared 0.26 pixels to the
  left per row, about a ground row, then moved a pixel right and 1.75 up. The ground row is the lowest
  row of the body in that direction's frame 0. As in the casts, the shadow runs off the canvas's left
  edge in frames 0–4 and 18–19, facing S, SW and SE. No body pixel touches an edge.

### drift.tsv

Tab-separated, one row per frame and direction:

| Column | Meaning |
|--------|---------|
| `class`, `variant` | `warrior`, `wls` |
| `frame` | 0–19 |
| `direction` | `S`, `SW`, `W`, `NW`, `N`, `NE`, `E` or `SE` |
| `dy`, `dx` | the shift, in pixels down and to the right, that moves the fire and magic casts onto this sprite |

To draw the fire or magic effect over this sprite, draw its overlay moved by that shift. The lightning
overlay needs none.

## The drift

The three casts draw one motion, but not in one place. In `wls`, the fire and magic casts line up with
each other, but they're drawn away from the lightning cast, further the further the direction is from
S. The gap grows over frames 2–9 and closes to a pixel by frame 19. From frame 9 to 15 it's 1 pixel
facing SW, 4 facing W, 7 facing NW, 9 facing N, 7–8 facing NE, 4–5 facing E and 2 facing SE, to the
left, and up to 2 pixels down or up. That's about 4.5 (1 − cos yaw) pixels to the left and 2 sin yaw
down, with the yaw counted from S toward W.

No motion does that. A body that moves shifts on screen, from one direction to the next, by a sinusoid
of the yaw that averages zero, so it can't move the picture 9 pixels facing N and none facing S. The 8
views of a fire or magic frame aren't one shape either. The visual hull carved from them with the
stand's camera covers only 0.8–0.9 of their pixels mid-cast. The stand's frames and the lightning
cast's get 0.99. Moved by about 4 pixels, the same in every direction, the fire and magic casts give
0.96–1.00. So the lightning cast is the one drawn where the camera sees the body, and this sprite
follows it.

Other variants drift otherwise. These were checked at one mid-cast frame:

| Variants | Drift |
|----------|-------|
| `wla` `whd` `wmh` `wht` | as `wls` |
| `wln` | the magic cast alone, by up to 10 pixels |
| `wlb` | the fire and magic casts, by a sinusoid that averages zero: a plain motion |
| `rls` | irregular, from direction to direction |
| `wmn`, `rlb` `rmd`, `sls` `smt` | none, or a pixel |

A variant whose fire and magic casts don't drift together would want each cast moved on its own in step
1 below.

## How it was made

Per frame and direction, the three casts were decoded and aligned by their bottom rows, as the game draws
them. Each cast's effect is the pixels of its overlay (its row of `../overlays/overlays.tsv`; for `wls`:
`warrior/fire-2`, `warrior/lightning-1` and `warrior/magic-1`).

1. **Alignment.** The fire and magic casts are moved together onto the lightning cast. The shift is
   searched up to 10 pixels each way, and it's the one whose silhouettes (opaque pixels other than index
   0) overlap most, as intersection over union. The overlap is counted only where no cast's effect is,
   grown by a pixel. Counting the pixels that agree, background included, picks no shift, since a shift
   moves pixels off the canvas.
2. **Shadows.** Each cast's baked shadow counts as background. That's its index-0 pixels that touch the
   background near where the shadow rule puts the shadow ([shadow.py](../../poc/shadow.py)'s
   `baked_shadow`, told that the body and its shadow may go on under the effect).
3. **Free casts.** A cast is free at a pixel outside its effect grown by a pixel, since an effect's edge
   is blended with what's under it. Where only one cast is free, it counts only at least 3 pixels from
   its own effect: an effect's dim edges reach past its overlay.
4. **Body or background.** It's body where at least as many free casts show the body as show the
   background, so thin parts survive a tie.
5. **Colors.** They come from two casts that agree (the same index, or colors within 24 in every RGB
   channel), both outside their effects as drawn. The pairs are tried in this order: lightning and magic,
   then fire and magic, then fire and lightning, since the fire cast's body is lit differently all
   through. Otherwise the color comes from the free cast whose effect is farthest, whose light falls
   there least.
6. **Single casts.** A pixel that only one cast shows is kept only within 2 pixels of pixels that two
   casts agree on. Elsewhere it's often an effect that its overlay missed, a spark, showing where the
   other casts' effects hide the view.
7. **Gaps.** Pixels that none of this settles take the most common value among their settled
   neighbours, growing inward. Pieces farther than 2 pixels from the largest one are dropped.
8. **Shadow.** It's drawn by the rule (see [The CL2 file](#the-cl2-file)).

Of the body's pixels, 78.8% are where two casts agree, 19.5% come from one cast, and 1.7% are filled in
step 7. Nothing is filled in frames 0–2 and 17–19. The most is 6.9%, in frame 14, where all three
effects are large.

[poc/casts.py](../../poc/casts.py) does this, and the preset `warrior-cast` in `poc/views.py` loads
it. The file was written as the overlays are (see
[Writing the files](../overlays/README.md#writing-the-files)).

## What didn't work

- **Moving the lightning cast onto the magic cast, by up to 2 pixels,** scored by the pixels that agree.
  It favoured no shift, and the drift is longer anyway, so mid-cast frames mixed bodies from different
  places. They showed two blades side by side, and their 8 views were no shape: a visual hull covered
  0.61–0.67 of them in frames 8–14. A model fitted to them lost the raised sword.
- **Leaving the gaps unknown, or using the fire and magic casts alone,** helped little while the casts
  were misaligned.

## Limits

- **The effects' light.** Where one cast alone shows the body (19.5% of its pixels), its colors carry
  that cast's effect's light.
- **Gaps** are filled from neighbours' colors: 1.7% of the body is a guess.
- **The shadow** is the rule's, which matches the casts' at about 0.94 intersection over union, not the
  artist's.
- **The lightning overlay** (`warrior/lightning-1`) holds strips of the body, mostly in frames 3–8 and
  15–18, because the drift fooled the overlays' body test too. The lightning cast counts as hidden
  there, and the other two casts show the body instead.
- **One variant:** `wls`.

## Checked

- **It decodes back exactly** with [sprites.py](../sprites.py) to the frames that were encoded.
- **Each frame is one shape.** The visual hull carved from a frame's 8 directions, with the stand's
  camera, covers 0.98–1.00 of their pixels, as for the stand's own frames (0.99).
- **A model fits it.** `poc/motion.py`'s model of the stand and this cast together matches it at 0.93
  silhouette intersection over union and 40% exact pixels (the stand: 0.95 and 50%). Each frame's own
  still matches it at 0.99.
- **Looked at:** every frame in every direction.
