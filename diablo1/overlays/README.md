# Spell overlays

A player casting a spell shows its effect: flames, lightning arcs, a cloud. The game doesn't draw the
effect separately. It's baked into the casting animations, one set per armor and weapon variant:
`plrgfx/<class>/<v>/<v>fm.cl2` (fire), `lm.cl2` (lightning) and `qm.cl2` (magic). This folder holds
the effects on their own, separated from the bodies. They're for taking the effect out of a cast before
fitting a model to the body, and for drawing it again over new frames.

They were extracted from `DIABDAT.MPQ` and `hfmonk.mpq` (the monk). The rest of this page describes
what's here, the effects themselves, and how they were made, in enough detail to make them again.

## Contents

| Path | Contents |
|------|----------|
| `<class>/<spell>-<n>.cl2` | one overlay: the effect of `<spell>` (`fire`, `lightning`, `magic`) shared by a render group of `<class>`'s variants (see [Render groups](#render-groups)); `<n>` numbers the class's groups for that spell from 1, largest first, skipping groups without an overlay |
| `overlays.tsv` | which overlay goes with each of the 324 casts (4 classes × 27 variants × 3 spells) |
| `README.md` | this page |

The classes are `warrior`, `rogue`, `sorcerer` and `monk`. Their sprite folders are `plrgfx/warrior`,
`plrgfx/rogue` and `plrgfx/sorceror` (sic) in `DIABDAT.MPQ`, and `plrgfx/monk` in `hfmonk.mpq`.

### The CL2 files

They're in the casts' own format (see [cl2.md](../docs/filespecs/cl2.md)), so the same decoder reads
them, given the class's cast width.

| Class    | Width | Frames |
|----------|------:|-------:|
| warrior  | 96    | 20     |
| rogue    | 96    | 16     |
| sorcerer | 128   | 12     |
| monk     | 114   | 18     |

The widths are the `lightning`, `fire` and `magic` columns of `assets/txtdata/classes/<class>/sprites.tsv`
in DevilutionX, and the frame counts are `castingFrames` in `animations.tsv`.

- **Pixels** are the casts' palette indices; every other pixel is transparent. They're all in the
  shared sprite range (128–253 occur), so any of the game's palettes shows them; the town palette was
  used here.
- **Anchoring** is the casts': a frame's bottom row is the cast frame's bottom row. So an overlay frame
  drawn at a cast frame's position lands on its effect. Frames are cut off above their topmost effect
  pixel, so heights vary. A frame with no effect is one transparent row.
- **Directions** come in three layouts (the `directions` column of `overlays.tsv`):

  | `directions` | File | Meaning |
  |--------------|------|---------|
  | `same`    | a frame list (one group) | the effect is the same in every direction; use these frames for all 8 |
  | `each`    | a sheet of 8 groups, in the game's order S, SW, W, NW, N, NE, E, SE | the effect differs by direction |
  | `shifted` | a sheet of 8 groups | one effect, drawn a few pixels to the side in some directions (two of the rogue's fires) |

### overlays.tsv

Tab-separated, one row per class, variant and spell:

| Column | Meaning |
|--------|---------|
| `class` | `warrior`, `rogue`, `sorcerer` or `monk` |
| `variant` | the sprite folder: class letter (`w`, `r`, `s`, `m`), armor (`l` light, `m` medium, `h` heavy) and weapon (`n` none, `u` shield, `s` sword, `d` sword and shield, `b` bow, `a` axe, `m` mace, `h` mace and shield, `t` staff), as in DevilutionX's `ArmourChar` and `WepChar` (`Source/player.h`) |
| `cast` | `fm` (fire), `lm` (lightning) or `qm` (magic): the sprite is `plrgfx/<class>/<variant>/<variant><cast>.cl2` |
| `overlay` | the overlay's path in this folder, empty if there's none |
| `directions` | `same`, `each` or `shifted` (see above) |
| `shared_by` | how many variants share the overlay (its render group's size) |
| `frames` | frames in the overlay |
| `pixels` | effect pixels in the file, all frames and groups |

Five casts have no overlay: the warrior's lightning in `wlb`, `wmb`, `whn`, `whu` and `whb`. Each of them
is a render group of its own, and the warrior's armed lightning differs by direction, so no two
samples of a pixel could be compared (see [Limits](#limits)).

### What an overlay holds, and what it doesn't

An overlay holds the effect where its render group's samples agree: beside the body and in front of
it. It doesn't hold:

- **See-through parts over the body.** The monk's clouds and glows, the rogue's red haze and the fire
  rings' dim inner haze blend with whatever body is behind them. Each variant's pixels differ there, so
  no consensus forms. Over empty ground they're in the overlay.
- **Parts the body always hides.** Where the body covers the effect in every sample, nothing of it
  was ever drawn.
- **The effect's light on the body.** In some variants, the fire cast's body is shaded differently from
  the other two casts' all through, even before any flame shows. That's on the body's pixels.

To take an effect out of a cast, treat every opaque overlay pixel as effect, even where its index
differs from the cast's. The same render still varies a little from one variant to the next: 57% to
97% of an overlay's pixels equal its variants' pixels, and at least 70% for nine casts in ten (see
[Checked against the game data](#checked-against-the-game-data)). A fit should still expect the
see-through parts and the light to be off. To draw an effect, draw the overlay after the body, at the
cast frame's position.

## The effects

Each class has its own three effects. None is shared between classes, and their frame counts differ,
so nothing lines up across classes either. The frames in the tables are those where a file has at
least 5% of its busiest frame's pixels.

### Warrior (20 frames)

- **Fire:** a fireball forms in the hands (frame 1), opens into a ring of flame around the body (3–12),
  and spreads into flame wings that die down (13–18). The same in every direction.
- **Lightning:** a ring flashes on the ground (8), then arcs crackle around and over the body (9–15,
  brightest at 12). The armed variants have different arcs in every direction. In light and medium
  armor, the unarmed and shield-only variants have one set of arcs for all directions.
- **Magic:** a trail of sparks spirals out from the feet, around and up the body (1–19). The same in
  every direction.

| File | Directions | Variants | Frames |
|------|------------|----------|--------|
| `fire-1` | same | wln wlu wlb wla wlm wlh wlt wmn wmu wms wmd wmb wma wmm wmh wmt whs whd whb wha whm whh wht | 1–18 |
| `fire-2` | same | wls wld | 1–16 |
| `fire-3` | same | whn | 1–17 |
| `fire-4` | same | whu | 1–16 |
| `lightning-1` | each | wls wld wla wlm wlh wlt | 8–15 |
| `lightning-2` | each | wms wmd wma wmm wmh wmt | 8–15 |
| `lightning-3` | each | whs whd wha whm whh wht | 8–15 |
| `lightning-4` | same | wln wlu | 9–14 |
| `lightning-5` | same | wmn wmu | 9–14 |
| `magic-1` | same | wlu wls wld wlb wla wlm wlh wlt wms wmd wmb wma wmm wmh wmt | 1–19 |
| `magic-2` | same | whs whd whb wha whm whh wht | 1–19 |
| `magic-3` | same | wmn wmu | 1–19 |
| `magic-4` | same | wln | 0–19 |
| `magic-5` | same | whn | 1–19 |
| `magic-6` | same | whu | 1–19 |

Render groups draw their effect in their own colors. `lightning-1`'s arcs (armed, light armor) are
bluish, the other lightning groups' are white with red edges, and the unarmed variants' sparks
(`magic-4` and `magic-5`) are blue.

### Rogue (16 frames)

- **Fire:** flames rise from the hands (2–4) into a ring with flame wings around the body (5–12), then
  break up (13–15). The same in every direction, except that `rls` and `rld` draw it to the side in
  some directions.
- **Lightning:** arcs around the body (9–14). The same in every direction. `rhb`'s lightning flashes
  twice, in frames 3–7 and 9–14; the first flash is in its sprite as well.
- **Magic:** a pale blue cloud gathers at the feet (3) and grows around the legs (to 15). The same in
  every direction.

| File | Directions | Variants | Frames |
|------|------------|----------|--------|
| `fire-1` | same | rln rla rlm rmu rmb rmm | 2–15 |
| `fire-2` | same | rlb rmn rmd rmh | 2–15 |
| `fire-3` | same | rlu rlt rmt | 2–15 |
| `fire-4` | same | rlh rma | 2–14 |
| `fire-5` | same | rhu rht | 1–15 |
| `fire-6` | same | rhd rha | 1–15 |
| `fire-7` | same | rhm rhh | 1–15 |
| `fire-8` | shifted | rls | 3–15 |
| `fire-9` | shifted | rld | 3–15 |
| `fire-10` | same | rms | 3–15 |
| `fire-11` | same | rhn | 1–15 |
| `fire-12` | same | rhs | 2–15 |
| `fire-13` | same | rhb | 1–15 |
| `lightning-1` | same | rln rlu rls rld rlb rlm rlt rmn rmu rms rmd rmb rmm rmh rmt | 9–14 |
| `lightning-2` | same | rhn rhu rhs rht | 9–14 |
| `lightning-3` | same | rla rma | 9–14 |
| `lightning-4` | same | rhm rhh | 9–14 |
| `lightning-5` | same | rlh | 9–14 |
| `lightning-6` | same | rhd | 9–14 |
| `lightning-7` | same | rhb | 3–14 |
| `lightning-8` | same | rha | 9–14 |
| `magic-1` | same | rln rlu rld rlb rlm rlh rlt rmn rmu rms rmd rmb rmm rmh rmt | 3–15 |
| `magic-2` | same | rhn rhu rhs rht | 3–15 |
| `magic-3` | same | rls rla | 1–14 |
| `magic-4` | same | rhd rha | 3–15 |
| `magic-5` | same | rhm rhh | 3–15 |
| `magic-6` | same | rma | 3–15 |
| `magic-7` | same | rhb | 4–15 |

The two shifted fires, compared with where direction S draws them:

- **`fire-8` (`rls`):** 4 pixels to the right in NW and N, 4 to the right and 1 down in NE and E, and
  3 to the right in SE.
- **`fire-9` (`rld`):** 2 pixels to the left in every direction but S.

### Sorcerer (12 frames)

- **Fire:** a column of flame rises from the feet (2) and engulfs the body (6–9), then thins out (10).
  The same in every direction.
- **Lightning:** blue arcs rise from the ground around the body (4–10). The same in every direction.
- **Magic:** a swirling sphere of blue and white mist around the body (1–11, fullest at 6). The same in
  every direction.

| File | Directions | Variants | Frames |
|------|------------|----------|--------|
| `fire-1` | same | slh smn sms smd smb smm smh shu shs shd shb shm | 2–10 |
| `fire-2` | same | slu sls sma smt sha sht | 2–10 |
| `fire-3` | same | sln sld slb sla slt | 2–10 |
| `fire-4` | same | smu shn shh | 1–10 |
| `fire-5` | same | slm | 1–11 |
| `lightning-1` | same | all but slb | 4–10 |
| `lightning-2` | same | slb | 4–10 |
| `magic-1` | same | slb smn smu sms smd smb smh shn shu shs shd shb shm shh | 1–11 |
| `magic-2` | same | sls sla slh slt sma smt sha sht | 1–11 |
| `magic-3` | same | sln slu | 1–11 |
| `magic-4` | same | sld | 1–10 |
| `magic-5` | same | slm | 1–11 |
| `magic-6` | same | smm | 1–11 |

### Monk (18 frames)

The monk's effects differ in every direction, and they follow the weapon. The three armors of one
weapon share a render, while the weapons' poses differ. His three casts are also three different
motions: the weapon moves differently in each.

- **Fire:** an orange glow at the feet (3) rises over the body as a pale fiery aura (to 17).
- **Lightning:** a column of white and blue lightning around the body (2–15, brightest at 10).
- **Magic:** a white cloud billows from the feet over the whole body (0–17).

| File | Directions | Variants | Frames |
|------|------------|----------|--------|
| `fire-1` | each | mln mmn mhn | 3–16 |
| `fire-2` | each | mlu mmu mhu | 3–17 |
| `fire-3` | each | mls mms mhs | 3–16 |
| `fire-4` | each | mld mmd mhd | 3–17 |
| `fire-5` | each | mlb mmb mhb | 3–17 |
| `fire-6` | each | mla mma mha | 3–17 |
| `fire-7` | each | mlm mmm mhm | 3–17 |
| `fire-8` | each | mlh mmh mhh | 3–16 |
| `fire-9` | each | mlt mmt mht | 3–16 |
| `lightning-1` | each | every monk but the unarmed (`m?n`) and bow (`m?b`) variants | 2–15 |
| `lightning-2` | each | mln mmn mhn | 2–15 |
| `lightning-3` | each | mlb mmb mhb | 2–15 |
| `magic-1` | each | mln mmn mhn | 1–17 |
| `magic-2` | each | mlu mmu mhu | 0–17 |
| `magic-3` | each | mls mms mhs | 0–17 |
| `magic-4` | each | mld mmd mhd | 0–17 |
| `magic-5` | each | mlb mmb mhb | 0–17 |
| `magic-6` | each | mla mma mha | 0–17 |
| `magic-7` | each | mlm mmm mhm | 0–17 |
| `magic-8` | each | mlh mmh mhh | 0–17 |
| `magic-9` | each | mlt mmt mht | 0–17 |

## What the casts are made of

These findings shaped the method.

- **Render groups.** A class's 27 variants fall into a few groups that share one render of an effect.
  Within a group, most effect pixels have the same palette index in every variant; between groups, the
  effect has the same design but other pixels. In the sorcerer's fire, for example, variants agree on
  71–89% of the pixels they both show as effect within a group, and on 26–56% between groups.
- **Bodies don't agree.** The variants' bodies differ: other armor, other weapon, other dither. In the
  frames checked with no effect yet, no body pixel had the same index in 20 or more of the 27 variants.
  A typical body pixel's most common index was shared by 6–8 of them.
- **The effect is often flat.** In most groups the effect is the same image in all 8 directions, while
  the body turns under it: 54–94% of direction S's effect pixels have the same index in the other seven.
  The warrior's armed lightning (25–30%) and all of the monk's effects (6–17%) differ by direction
  instead.
- **A variant's three casts don't share one body.** In frames with no effect yet, the fire, lightning
  and magic casts of one variant have the same index in 7% to 86% of their body pixels, typically about
  half.
  - Some casts are drawn a pixel or more apart.
  - Others differ by a dither or a shade, and in some variants the fire cast's body is shaded
    differently throughout.
  - The monk's three casts are different motions altogether.

  So subtracting one cast from another doesn't isolate an effect. Comparing them within a pixel and a
  few shades of color does tell body from effect, for every class but the monk.
- **The effects are bright.** Flames, arcs and glowing clouds are lighter than the body they cover.
  The body test relies on it.

## How they were made

Per class, all three casts of all 27 variants were decoded. Each pixel of each cast then has
27 × 8 samples per frame: variants by directions.

The tools needed are the MPQ reader in [blizzard_common](../../blizzard_common/mpq.py), the CL2
decoder in [sprites.py](../sprites.py), and a CL2 writer. The repository has no writer;
[Writing the files](#writing-the-files) describes it.

### Samples

1. **Decode** each cast sheet (8 groups) with the class's width. Keep the class's frame count `n`.
   Three casts have one frame more (`wln` and `wmd` lightning, `rhu` magic), and it's dropped.
2. **Align** frames by their bottom-left corner, as the game draws them: pad each one at the top to the
   tallest frame among the class's casts. One warrior sheet (`wmt` lightning) is 128 high, so the
   warrior's canvas is 96 × 128.
3. **Colors** come from the town palette (`levels/towndata/town.pal`). Luminance is
   `0.299 R + 0.587 G + 0.114 B`, with channels 0–255.

### The body test

A sample is a pixel of one cast `T` of one variant, direction and frame. The other two casts of the same
variant, direction and frame, `T′` and `T″`, show the same body, once laid onto it (see
[Laying the casts on](#laying-the-casts-on); except the monk's: see
[The monk's weapons](#the-monks-weapons)). A sample counts as **effect** if all three of these hold:

- It's opaque and not index 0. Index 0 is the baked shadow, or black texture.
- **It isn't near a body pixel:** no pixel within one (the 3 × 3 neighbourhood) in `T′` or `T″` is
  within 24 of it in every RGB channel. This catches the casts' one-pixel offsets, dithers and tints.
- **It's brighter than the body there:** its luminance exceeds by more than 24 the darker of two
  values, the brightest luminance within one pixel in `T′` and the same in `T″` (transparent counts as
  0). Taking the darker of the two copes with the other cast showing its own effect at that spot.

Everything else is body, shadow or background.

### Laying the casts on

The three casts don't always draw the body in the same place. In the armed warriors, the fire and magic
casts are drawn up to 9 pixels away from the lightning cast mid-cast (see
[the casts](../casts/README.md#the-drift)), and some other variants' casts sit a pixel or a few apart
all through. Compared where they're drawn, strips of the lightning cast's own body passed the body test
as effect. So the method runs twice:

1. **A first pass** runs everything on this page on the casts as drawn.
2. **Laying on.** For each variant, direction and frame, and each pair of its casts, try every shift
   (dy, dx) with |dy| and |dx| up to 12. Score it by the intersection over union of the two casts'
   silhouettes (opaque pixels other than index 0), counted only where neither cast's first-pass
   overlay is, grown by a pixel. Take the best shift if it beats no shift by 0.01, and if the two then
   match at 0.65 or better. Then, per variant and direction, replace each shift by the median over 5
   frames (fewer at the first and last two), since a real drift changes smoothly from frame to frame.
3. **A second pass** runs the body test with the other two casts laid onto the tested one, then the
   consensus, the offsets and the pooling below, in the first pass's render groups.

The monk's three casts are different motions, which no shift lays onto each other, so he keeps the
first pass. So is `rhb`'s magic cast, mid-cast: no shift matches it at 0.65, and it stays as drawn
there. Laid on, the warrior's fire and lightning casts move apart in 59% of his cells, and his
lightning and magic casts in 70%, by up to 12 pixels; the rogue's and sorcerer's casts in 1% to 10%,
mostly by a pixel or two.

### Render groups

For two variants `a` and `b` of one class and cast, their agreement is the share of samples with the
same index. It's counted over every direction, frame and pixel where both have an effect sample.
Groups form by **average linkage**:

1. Start with every variant alone.
2. Merge the two groups whose variants agree most on average (the mean over all pairs across the two),
   while that mean is above **0.6**.

Single linkage (merge when any pair agrees) chained different renders into one group, and so did a
threshold of 0.5. The groups are numbered by size, largest first, then by their first variant in the
order armor `l`, `m`, `h` and weapon `n u s d b a m h t`. The numbering skips groups that end up empty.

### Consensus

The pool for a pixel is the group's samples at that pixel, either per direction or across directions
(see Pooling). Among the pool's effect samples, take the most common index `m` and its count `c`. Keep
`m` if all of these hold:

- `c` ≥ half of the pool's effect samples;
- `c` ≥ a quarter of the pool's samples, effect or not;
- `c` ≥ 2;
- in a pool of 8 samples or fewer, `c` ≥ min(4, ⌈pool / 2⌉).

Otherwise the pixel is transparent. The floors keep body pixels out. On their own, a pair of
samples that both pass the body test by chance would agree among a hundred others that don't.

### Directions and offsets

1. **Offsets.** For each direction `d` of a group, try every shift (dy, dx) with |dy| and |dx| up to 4.
   Pick the one that makes the most of its effect samples equal to direction S's at the same pixel,
   over the group's variants and every frame. Use it only if it gives at least 1.5 times as many equal
   samples as no shift. This finds the rogue's `rls` and `rld` fires; every other group gets none.
2. **Flatness.** Build the consensus per direction, with the group's variants as the pool. Flatness is
   the share of direction S's kept pixels that have the same index in each other direction, moved by
   its offset, over all frames. A group of one variant has too few samples per direction to measure
   this; it takes the larger of its own and the class's largest group's flatness.
3. **Pooling.** If flatness is at least 0.5, move each direction's samples by its offset. Then build
   the consensus over variants × 8 directions, and give each direction that overlay moved back by its
   offset. Otherwise, keep the per-direction consensus.

Pooling is what makes single variants work. Their body turns from one direction to the next while a
flat effect stays put, so 8 directions are 8 samples.

### The monk's weapons

The monk's three casts are different motions, so the body test compares unrelated pixels, and his
weapon passes as effect. His render groups are the three armors of one weapon, which all carry that
weapon, so the consensus keeps it. But his nine weapon groups share one effect design while their
weapons and poses differ.

So for the monk only, a pixel of a group's overlay is kept only with support from the other groups.
At least a third of them (3 of 8 for fire and magic, 1 of 2 for lightning) must have an overlay pixel
within 2 pixels of it, in the same frame and direction, and within 48 of it in every RGB channel.
Without the color condition, the white cloud next to an axe kept its brown shaft. This removed 4–7% of
the monk's overlay pixels: the axe and mace heads, sword blades and shafts. It isn't used for the other
classes, where the body test works and renders can legitimately differ from group to group: random
lightning arcs, `rhb`'s extra flash.

### Writing the files

- A group whose overlay is empty in every frame gets no file; its variants get an empty `overlay`.
- A flat group with no offsets is written as a frame list of one direction's frames (`same`). Others are
  written as a sheet of 8 (`each` if they weren't pooled, `shifted` if they were).
- Each frame is cut to the rows from its topmost opaque pixel down to the bottom. A frame with nothing
  left keeps one transparent row.
- The encoding follows [cl2.md](../docs/filespecs/cl2.md#writing-cl2).
  - Rows go from the bottom, and every run stays inside its row.
  - Transparent runs are skips of up to 127. Three or more equal pixels make a fill of up to 63;
    others make literals of up to 65.
  - The frame header holds the offsets of rows 32, 64, 96 and 128, counted from the bottom (0 when the
    frame is shorter).

## What didn't work

- **Pixel-exact matches between casts** as the body test. The casts' bodies differ by dithers and
  tints, so body pixels passed as effect and bled into the overlays: the sorcerer's robe, the
  monk's trousers, the warrior's boots.
- **Agreement among the effect samples alone,** without the floors. A few body samples that pass the
  test agree by chance where the body sits in every direction, such as the feet.
- **The body test alone for a single variant** whose effect differs by direction. It keeps the bow, a
  red sword and helmet highlights. Those five warrior lightnings are left without an overlay.
- **The monk's plain body colors** as a body test. His stand and walk animations use every white,
  gray and blue in his lightning and magic, and 39% of his fire's pixels are in their colors too.
- **One overlay per spell for all classes.** Every class has its own effects.
- **Laying the casts on without a match test.** Where an effect covers nearly the whole body (the
  sorcerer's flame column, `rhb`'s magic mid-cast), what's left of the silhouettes matches somewhere
  at random, by up to the search's 12 pixels. Those shifts changed some of the rogue's and sorcerer's
  overlays by up to 28%; with the test, by 6% at most.
- **Render groups formed again after laying on.** The medium armor's unarmed and shield-only magic
  (`wmn`, `wmu`) then joined `magic-1`, though only 55–58% of its pixels equal their casts'. The
  second pass keeps the first pass's groups.

## Limits

- **Translucent parts and parts behind the body** are missing (see
  [What an overlay holds](#what-an-overlay-holds-and-what-it-doesnt)). Where the monk's white cloud
  passes over his skin or trousers, a few pink or blue pixels of cloud blended with the body are kept.
- **Five casts have no overlay:** the warrior's lightning in `wlb`, `wmb`, `whn`, `whu` and `whb`.
- **Three casts lose their last frame:** `wln` and `wmd` lightning (21 frames) and `rhu` magic (17)
  have one more frame than the overlay.
- **Staffs light up.** In the staff variants' lightning (`wlt`, `wmt`), the staff passes the body
  test, lit by the arcs, and some of the arcs differ from the rest of their group's: their overlays
  cover the least of their own casts' effect samples (77% and 50%).
- **Specks.** A few pixels of noise sit in frames before and after an effect. A few gray specks of
  the axe head remain in the monk's axe magic (`magic-6`), frames 2–4.
- **Thresholds are judged by eye.** The two 24s of the body test, the 0.6 linkage, the 0.5 flatness,
  the floors, the monk's support and laying on's 0.65 match were tuned on these sprites by looking at
  the overlays, against bleeding and gaps. There's no ground truth.

## Checked against the game data

- **Every file decodes back exactly.** Each was decoded with [sprites.py](../sprites.py) after
  writing, and gives exactly the frames that were encoded.
- **Overlays against their casts.** For each of the 319 casts with an overlay, two shares were measured
  over every direction and frame:
  - *Equal:* the share of the overlay's pixels with the same index as the cast at the same place.
  - *Covered:* the share of the cast's own effect samples (the body test's, on the casts laid on) that
    the overlay covers.

  | Class    | Cast | Equal: median, lowest | Covered: median, lowest |
  |----------|------|----------------------:|------------------------:|
  | warrior  | fire      | 76%, 71% | 84%, 81% |
  | warrior  | lightning | 88%, 75% | 91%, 50% |
  | warrior  | magic     | 91%, 71% | 97%, 56% |
  | rogue    | fire      | 70%, 65% | 82%, 57% |
  | rogue    | lightning | 80%, 69% | 89%, 41% |
  | rogue    | magic     | 82%, 59% | 82%, 66% |
  | sorcerer | fire      | 83%, 61% | 91%, 86% |
  | sorcerer | lightning | 83%, 75% | 92%, 79% |
  | sorcerer | magic     | 79%, 71% | 95%, 86% |
  | monk     | fire      | 95%, 89% | 84%, 71% |
  | monk     | lightning | 86%, 57% | 84%, 72% |
  | monk     | magic     | 94%, 93% | 92%, 86% |

  The lowest coverage figures come from casts whose body test keeps extra pixels, not from gaps in the
  overlay. One is `rls`'s lightning: that cast doesn't line up with its other two, and only 7–9% of
  their body pixels are equal in frame 0. Others are `wmt`'s lightning (see Limits: its staff) and
  `wlu`'s magic. The monk's coverage is lower by design, since his body test also passes his weapon.
  The equal share is never 100%, even within a render group: variants differ a little in dither and
  in what shows through.
- **The second pass against the first.** Laying the casts on changed 36 of the 77 files.
  - The armed warriors' lightning (`lightning-1` to `-3`) lost 26–30% of its pixels. In frames 3–7
    and 16–17, where the first pass's were 85–98% strips of the body, a few pixels are left, and in
    frame 12 the share of body fell from 12–19% to 1–4%.
  - In `lightning-1` and `-2`, the overlays now cover 83–95% of the effect samples of five of each
    group's six casts, against 72–88%; the staff variant's the least (see Limits).
  - The warrior's unarmed lightning (`lightning-4` and `-5`) changed by 23% and 12% of its pixels.
    Every other file changed by 7% at most.
- **Looked at:** every file's frames, facing SW, were drawn and inspected for bleeding and gaps,
  along with the variants' casts for a sample of groups.
