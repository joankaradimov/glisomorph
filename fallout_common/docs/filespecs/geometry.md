# Geometry: hexes, floor tiles and the projection

Fallout and Fallout 2 put everything that moves or blocks on a **hex grid**, and draw the ground and
roofs from a separate grid of **square tiles**, each covering 2×2 hexes. Neither grid is stored in a
file of its own: the layout below is fixed in the engine, and [MAP](map.md) files only fill it in. Both
games use exactly the same geometry; every number on this page is identical in `fallout1-ce` and
`fallout2-ce`.

This page matters for glisomorph because sprites come in 6 directions, and blending between them needs
their angles on the ground, not on the screen.

## Summary

- Hex grid: 200×200 per elevation, 3 elevations. A hex is drawn in a 32×16 box.
- Neighbor hexes are (±32, 0) and (±16, ±12) pixels apart on screen.
- The 6 directions, in file and rotation order, are **NE, E, SE, SW, W, NW**. On the ground they're
  60° apart: NE 60°, E 0°, SE 300°, SW 240°, W 180°, NW 120° (counter-clockwise from screen-right, seen
  from above). On screen, the diagonals sit at ±36.87° from horizontal, not ±60°.
- The grid implies an **orthographic camera looking down 25.66° below the horizon**
  (sin = √3/4), with ground "north" pointing straight up the screen. The art agrees to within about
  half a degree: walk cycles give 25.3°, round objects 26.1°, and 30° is ruled out. Vertical heights
  would shrink by cos 25.66° = 0.901 (not checked on the art). See
  [the derivation](#what-3d-projection-this-implies) and [the measurements](#checked-against-the-game-data).
- No direction faces the camera. E and W are exactly side-on; SE and SW are 30° either side of facing the
  viewer.
- A sprite's bottom-center sits on the hex center, shifted by the FRM's per-direction offset and the
  object's accumulated per-frame shifts. The frame's bottom row is on that point, as the code says,
  not one pixel above it, as the wiki says.
- Walk and run cycles don't cover a whole number of hexes. The engine moves the critter to the next
  hex whenever its running offset reaches a hex step, and carries the rest over.

## The hex grid

Each elevation has 200×200 = 40,000 hexes (`HEX_GRID_WIDTH`, `HEX_GRID_HEIGHT` in `map_defs.h`). A hex
number is

```
tile = row * 200 + column        # 0 <= tile < 40000
```

**Column 0 is at the east (screen right)**, and column numbers grow westward. Every formula in the
engine starts by mirroring the column: `x = 199 − column`. Using `x` makes the math read left to right.

The hex is drawn in a 32×16 box; its center is at (16, 8) inside the box. The engine's grid overlay
(`tileInit`) outlines it with the points (16, 0), (31, 4), (31, 12), (16, 15), (0, 12), (0, 4): a
**pointy-top hex** with vertical left and right sides. So east and west neighbors share a vertical edge,
and are straight left and right on screen.

How the numbering walks across the screen:

| Step             | From an even column | From an odd column |
|------------------|---------------------|--------------------|
| column + 1       | W: (−32, 0)         | SW: (−16, +12)     |
| row + 1          | SE: (+16, +12)      | SE: (+16, +12)     |

A "row" of hex numbers therefore zigzags W, SW, W, SW toward the lower left, (−48, +12) per two columns.
Rows stack toward the lower right. On the ground these two directions are at right angles (210° and
300°), which is why 2×2 blocks of hexes make rectangles.

Edge hexes (row 0 or 199, column 0 or 199) are valid, but movement stops there (`tileIsEdge`).

### Hex to screen

`fallout2-ce: src/tile.cc`, `tileToScreenXY`. In a fixed frame where the hex box of column 199, row 0 is
at (0, 0), the box's top-left corner is

```
x  = 199 - column
sx = 16*row + 48*(x // 2) + 32*(x % 2)
sy = 12*row - 12*(x // 2)
```

and its center is at (sx + 16, sy + 8). This was checked against the engine's own function, ported and
compared on 20,000 random pairs of hexes; it agrees exactly. (The engine's version uses C division,
which truncates toward zero, and patches odd columns separately. The result is the same as the floor
division above.)

The engine works relative to the hex at the screen center (`tileSetCenter`). It rounds that hex's `x`
down to an even number (moving the anchor 32 px left), and puts the anchor's box at
`((window_width − 32) / 2, (window_height − 16) / 2)`. Elevation is ignored: every elevation uses the
same mapping.

### Screen to hex

`tileFromScreenXY` cuts the screen into 12-px bands and 64-px cells, then looks up a 32×16 mask to pick
one of 5 hexes. An equivalent, easier method: hex centers form a lattice spanned by E = (32, 0) and
SE = (16, 12). In those axial coordinates a hex is `q = x`, `s = row − x // 2`. Convert a screen point
into fractional (q, s), round with ordinary cube rounding for pointy-top hexes, and convert back. Cube
rounding works on any affine image of a regular hex grid, so it needs no knowledge of the camera.

```python
import math

def hex_center(tile: int) -> tuple[int, int]:
    """Screen position of a hex center, in the fixed frame described above."""
    row, column = divmod(tile, 200)
    x = 199 - column
    return 16 * row + 48 * (x // 2) + 32 * (x % 2) + 16, 12 * row - 12 * (x // 2) + 8

def hex_at(px: float, py: float) -> int:
    """Hex under a screen point (same frame). Ties on the hex border may differ from the game."""
    s = (py - 8) / 12
    q = (px - 16 - 16 * s) / 32
    cq, cs, cr = q, s, -q - s
    rq, rs, rr = round(cq), round(cs), round(cr)
    dq, ds, dr = abs(rq - cq), abs(rs - cs), abs(rr - cr)
    if dq > ds and dq > dr:
        rq = -rs - rr
    elif ds > dr:
        rs = -rq - rr
    x, row = rq, rs + math.floor(rq / 2)
    return row * 200 + (199 - x)
```

## The six directions

`Rotation` in `fallout2-ce: src/obj_types.h`. Objects store a rotation 0–5, and critter FRMs store their
6 directions in the same order (see [FRM](frm.md)).

| Rotation | Name | Tile delta, even column | Tile delta, odd column | Screen offset | Screen angle | Ground angle |
|----------|------|-------------------------|------------------------|---------------|--------------|--------------|
| 0        | NE   | −1                      | −201                   | (+16, −12)    | 36.87°       | 60°          |
| 1        | E    | +199                    | −1                     | (+32, 0)      | 0°           | 0°           |
| 2        | SE   | +200                    | +200                   | (+16, +12)    | −36.87°      | 300°         |
| 3        | SW   | +201                    | +1                     | (−16, +12)    | −143.13°     | 240°         |
| 4        | W    | +1                      | −199                   | (−32, 0)      | 180°         | 180°         |
| 5        | NW   | −200                    | −200                   | (−16, −12)    | 143.13°      | 120°         |

"Even column" means the raw column number (`tile % 200`), not the mirrored `x`. Angles are
counter-clockwise from screen-right, with screen y pointing up for the angle; the screen offsets use
screen y pointing down.

- Tile deltas: `_dir_tile`, filled in `tileInit`; used by `tileGetTileInDirection`.
- Screen offsets: `_off_tile` and `dword_51D984` in `tile.cc`. Walking uses them: `_object_move`
  (`animation.cc`) adds each frame's offset to the object's running offset and, once that reaches the
  step in either axis, moves the object to the neighbor hex and subtracts the step. The art doesn't
  fit the steps exactly: a cycle covers a fractional number of hexes (2.16 for the male walk), so the
  rest carries over, and on the diagonals the art climbs slightly less than the grid (y/x = 0.739, not
  0.75), so the critter drifts off the hex line by a few pixels on a long straight walk until the
  path ends. See [Checked](#checked-against-the-game-data).
- A diagonal step is 20 px on screen, a horizontal one 32 px, but on the ground both are one hex.
- The ground angles follow from the projection below. They're what glisomorph should interpolate in.

**The game's own angle buckets are screen-based.** `tileGetRotationTo` turns the screen vector between
two hexes into an angle and cuts it into 60° sectors centered on screen angles 60°, 0°, −60°, and so on,
as if hexes were regular on screen. The true neighbor directions are at ±36.87°. This only affects which
way a critter turns to face something; it says nothing about the art.

## Floor and roof tiles

Each elevation has a 100×100 grid of square tiles (`SQUARE_GRID_WIDTH`, `SQUARE_GRID_HEIGHT`). Like
hexes, square columns are mirrored: `X = 99 − column`.

Which hexes a square holds depends on who asks:

- **The code** pairs square `row * 100 + column` with hex rows `2·row`, `2·row + 1` and hex columns
  `2·column`, `2·column + 1` (`tile / 200 / 2` and `tile % 200 / 2` in `objectSetLocation`, which
  hides the roof over the player).
- **On screen** the square's image covers the centers of the same rows but of hex columns
  `2·column + 1` and `2·column + 2`, one column further west. It isn't centered on them either: the four
  centers form a diamond whose middle is 8 px left of and 4 px below the middle of the tile's
  parallelogram. (Checked with the engine's functions, ported, on 6,000 random squares and screen
  centers.)

`squareTileToScreenXY` puts the floor tile's image top-left at

```
sx = 48*X + 32*row - 16
sy = -12*X + 24*row - 2
```

in the same fixed frame as the hexes above. Roofs (`squareTileToRoofScreenXY`) use the same position,
96 px higher. Elevation is ignored here too.

So one square column step is (−48, +12) on screen and one square row step is (+32, +24). The tile art is
80×36: the parallelogram with corners (0, 12), (48, 0), (80, 24) and (32, 36) inside the image. Its area,
1,536 px², is exactly four 32×16 hexes (384 px² each), as it should be. The tiles' opaque pixels fill
that parallelogram, with a one-pixel overlap along its upper-left edge.

A floor tile is drawn if bit 0 of its 4-bit flag field is clear. Roof bit 0 is set and cleared at run
time to hide the roof the player stands under (`tile_fill_roof`). The fields are described in
[map.md](map.md#tiles).

## What 3D projection this implies

The files contain no camera, so this is a model, not a fact from the code. It assumes the art was
rendered with an **orthographic camera** looking at a flat ground plane, with no roll.

**Setup.** Put the ground x axis along screen-right; that's always possible for a camera without roll.
Let the camera look down at angle φ below the horizon. Then a ground vector (gx, gy), with gy pointing
away from the viewer, lands on screen at (gx, −gy·sin φ), and a vertical height h lands at
(0, −h·cos φ). One screen pixel horizontally is one ground unit.

**Assume the hexes are regular on the ground.** The E neighbor is (32, 0) on screen, so the hex spacing
is 32 units. The NE neighbor must then be at ground (16, 16√3) = (16, 27.71), and on screen it's
(16, −12). So

```
sin φ = 12 / 27.71 = √3 / 4 = 0.4330      →      φ = 25.66°
```

**Cross-check 1: the hex box.** A regular pointy-top hex 32 units wide is 64/√3 = 36.95 tall, with its
side corners 9.24 above and below the center. Squashed by √3/4 that's exactly 16 px tall, with the side
corners at ±4 px, matching the 32×16 box and the outline points at y = 4 and y = 12. Nothing was fitted
to get this.

**Cross-check 2: the floor tiles, from a different assumption.** Assume nothing about hexes, only that a
floor tile's two edges are at right angles on the ground. The edges are (48, −12) and (32, 24) on
screen, so on the ground they're (48, 12/k) and (32, −24/k) with k = sin φ. Perpendicular means
48·32 = (12/k)(24/k), so k² = 288/1536 = 3/16 and k = √3/4 again.

With that k, the tile edges are 55.43 and 64 units long, at ground angles 30° and −60°: the tiles are
rectangles with sides in ratio √3 : 2, not squares. That's what 2×2 hexes of a regular grid cover.

**The camera, then:**

| Quantity                          | Value                                          |
|-----------------------------------|------------------------------------------------|
| Elevation below the horizon       | φ = asin(√3/4) = 25.66° (64.34° from straight down) |
| Ground squash on screen y         | sin φ = 0.4330                                 |
| Height squash on screen y         | cos φ = √13/4 = 0.9014                         |
| View direction on the ground      | 90°: straight up the screen, halfway between NE and NW |
| Hex spacing                       | 32 units (= 32 px horizontally)                |
| Roof offset, 96 px                | 106.5 units of height, about 3.3 hex spacings  |

The three axes (the two floor-tile edges and vertical) shrink by three different amounts (0.893, 0.625
and 0.901), which is why the community calls the projection *trimetric*.

**Measured on the art**, the ground squash sin φ comes out between 0.427 and 0.44 (25.3°–26.1°): 0.427
from the diagonal walk and run cycles, about 0.44 from round objects seen from above. The grid's 0.433
lies between the two, and 30° (0.5) fits nothing. The ground angles hold too: a diagonal cycle moves
0.496 of the E cycle's distance across the screen, cos 60.25°. Use 25.66°. Details are in
[Checked](#checked-against-the-game-data).

The height numbers rest on one more assumption: that objects were rendered in the same space as the
ground grid. That isn't checked yet; it would take an object of known proportions, such as a
cube-shaped crate aligned with the grid, or a sphere.

## Elevation

A map has up to 3 elevations (`ELEVATION_COUNT`), each a separate 200×200 hex grid and 100×100 tile
grid. They aren't stacked on screen: the engine shows one elevation at a time with the same mapping, and
stairs, ladders and elevators move objects between them. "Elevation" is a floor number, not a height.
Roofs are the only vertical offset in the tile system.

## Anchoring a sprite to its hex

`objectGetRect` and `_obj_render_object` in `fallout2-ce: src/object.cc` (the same in
`fallout1-ce: src/game/object.cc`):

```
X = hex_box_x + 16 + frm.x_offset[rotation] + obj.x
Y = hex_box_y +  8 + frm.y_offset[rotation] + obj.y
left   = X - width // 2
bottom = Y                      # top = Y - height + 1
```

- The frame's **bottom row** and **horizontal center** (rounded down for odd widths) sit on the hex
  center (hex box + (16, 8)).
- `frm.x_offset/y_offset[rotation]` is the FRM's per-direction offset (`artGetRotationOffsets`).
- `obj.x`, `obj.y` is the object's pixel offset from its hex. As an animation advances, the engine adds
  each frame's own shift (`artGetFrameOffsets`, through `_obj_offset`). MAP files store these two
  fields too (see [map.md](map.md#object-record)); they're normally 0 for an object at rest.
- Objects with tile −1 (in an inventory, or interface items) are drawn at their stored screen position
  instead.

So to line up frames for comparison, align the point (left + width // 2, bottom) after applying the
direction offset and the summed frame shifts. Frame and direction offsets are specified in
[FRM](frm.md).

What the art shows (numbers in [Checked](#checked-against-the-game-data)):

- **Frames are cropped tight.** A critter's bottom row is opaque in nearly every stand frame. It holds
  the feet and the shadow drawn on the ground under the critter, in the darkest greys (mostly index
  207, which also shades bodies). The floating eye bot (`mafeye`) has only its shadow there, below a
  gap.
- **The shifts put the body on the hex.** For humans the lowest pixel lands 2–5 px below the hex
  center, and the body's centroid within 2.5 px of it horizontally, in all six directions.
- **The bottom row is on the anchor**, as the code has it. Frames can't show this among themselves,
  since the two rules move every frame by the same pixel; art placed against the grid can. The hex
  cursor `msef000.frm` (32×16, shift (0, 7)) covers its hex's box exactly with
  `top = Y − height + 1`, and would stick out one pixel above it with the wiki's `top = Y − height`.

## Compared with Diablo

| | Diablo 1 | Fallout 1 and 2 |
|---|---|---|
| Ground grid | squares, drawn as 2:1 diamonds | regular hexes (plus √3:2 rectangles for floors) |
| Camera elevation | 30° (sin = 1/2) | 25.66° (sin = √3/4) |
| Camera yaw | grid axes at ±45° to the screen | E–W hex axis along the screen |
| Directions | 8, 45° apart, S facing the camera | 6, 60° apart, none facing the camera |
| Sprite anchor | `x = width/2`, 16 px above the bottom row | `x = width/2` at the bottom row, plus per-direction and per-frame offsets |

See [diablo1/docs/AGENTS.md](../../../diablo1/docs/AGENTS.md#what-matters-for-glisomorph). In both games,
interpolate in ground angle, not screen angle.

## Checked against the game data

Checked on 2026-10-03 against the US releases of both games (`critter.dat` and `master.dat`), with an
FRM reader written from [frm.md](frm.md). Fallout 2 repeats most of Fallout 1's critters (of the
critter `.frm` files both have, 2,463 are byte-identical and 16 differ), so the two games aren't
independent samples. The engine's own functions were ported and compared too: `tileToScreenXY`
against the formula above on 20,000 random pairs of hexes, and `tileSetCenter`, `tileToScreenXY` and
`squareTileToScreenXY` together on 6,000 random squares (see [Floor and roof tiles](#floor-and-roof-tiles)).

**Walk and run cycles.** The sum of a cycle's frame offsets, in screen pixels:

| File | Frames | E | NE | Hexes per cycle, E |
|------|-------:|---|----|-------------------:|
| `hmjmpsab`, male walk   | 8  | (69, 0)  | (34, −25) | 2.16 |
| `hfjmpsab`, female walk | 8  | (60, 0)  | (30, −22) | 1.88 |
| `hmjmpsat`, male run    | 10 | (128, 0) | (64, −47) | 4.00 |
| `maclawab`, deathclaw   | 8  | (102, 0) | (51, −39) | 3.19 |
| `mamantab`, mantis      | 8  | (28, 0)  | (14, −10) | 0.88 |
| `masratab`, rat         | 5  | (14, 0)  | (7, −5)   | 0.44 |

- **No cycle is whole.** None of the 143 unarmed walks (`ab`: 53 in Fallout 1, 90 in Fallout 2) adds
  up to whole hex steps in all six directions, and E and W are never a multiple of 32. Three critters
  (`masphn`, `naghul`, `nmbonc`) step exactly one hex on the diagonals, but 33 px in E. The 85 runs
  (`at`) are whole in E and W more often (38 of 170, like the 128 px above) but never on the
  diagonals: the male run's NE is 4 hexes in x and 47 of 48 px in y. The 413 armed walks behave like
  the unarmed ones.
- **The directions are one animation turned.** The four diagonals have the same |x| and |y|, and W
  mirrors E, in every walk and run but eight, which are off by 1–6 px somewhere (walks `hmmetlab`,
  `malieuab`, `nmlosrab`, `nmovr2ab`, `navgulab`; runs `hmmaxxat`, `nfpeasat`, `maroboat`).
- **The step rule copes.** Simulating `_object_move`: the critter changes hex whenever its running
  offset reaches a step and keeps the rest, so `hmjmpsab` moves 2 or 3 hexes per cycle as its extra
  5 px build up. On the diagonals one axis gets there first (usually x: y/x averages 0.739 against the
  grid's 0.75), so a sideways lag builds up instead: over 20 hexes, 6 px for the median walk or run,
  26 px at worst (`nmfattab`, `nmfattat`). It's dropped when the path ends and the critter is put on
  its hex.

**Camera elevation**, as k = sin φ:

| Measurement | k | φ |
|-------------|---|---|
| Diagonal walk and run cycles, \|y\| / (√3 · \|x\|), pooled over 98 distinct cycle sums | 0.427 (95%: 0.422–0.431) | 25.3° (25.0–25.5°) |
| Round objects at least 80 px wide (7), ellipse arcs | 0.440 ± 0.004 | 26.1° ± 0.2° |
| `tanktop.frm`, a flat tank lid, 208 × 92 px: height over width | 0.442, or 0.433 with a 2 px rim | 26.2° |
| `magun2aa`, the plasma turret's base, 40 px wide, six directions | 0.448–0.464 | 26.6–27.6° |
| The grid, above | 0.433 | 25.66° |
| For comparison: Diablo's camera | 0.5 | 30° |

- **The cycles.** A diagonal cycle covers half the E cycle's x (pooled 0.496, cos 60.25°), as turning
  one walk by 60° should; its |y| = (√3/2)·L·k then gives k. The interval treats the 98 distinct cycle
  sums as independent, but armor variants of one body share an animation, so it's too narrow.
- **The round objects**, fitted with a = half the silhouette's width: `encl49` (base, 126 px) 0.429,
  `gektank1` (base, 113 px) 0.455, `firepit` (base, 91 px) 0.438, `fsdome` (base, 104 px) 0.429,
  `tempsf03` (rim of a pool, 105 px) 0.446 and 0.449, `vosb000` (top disc, 81 px) 0.444, and `tanktop`
  0.452 (far rim) and 0.420 (near rim). Anti-aliased edge pixels kept opaque would raise k by about
  0.5 / a, which is why the small turret base reads high.
- **Not 30°.** A 208 px circle would be 104 px tall at 30°; the tank lid is 92.

**Floor tiles.** 2,951 of Fallout 2's tiles and 1,600 of Fallout 1's are 80×36 with one frame. Most
(2,155 and 1,105) share one opaque mask: the parallelogram (0, 12), (48, 0), (80, 24), (32, 36), with
1,522 of its 1,536 pixel centers, plus 76 pixels of overlap along the upper-left edge. Its edges slope
1:4 and 3:4. The blank tile `grid001.frm` outlines the same shape. This shows the art matches the
engine's tile placement; it doesn't test the camera, which is derived from these same edges.

**Walls** run along the floor tiles' edges. Of the pieces 16 or 32 px wide with a straight bottom edge
(692), the 16 px ones drop 11–12 px (3:4) or rise 4 px (1:4) across their width, and nearly all the
32 px ones rise 8 px (1:4).

**Anchoring.**

- Stand frames (`aa`, frame 0) are cropped tight: the bottom row is opaque in 568 of 576 directions in
  Fallout 2 and 340 of 348 in Fallout 1. The exceptions (`masrat` SW and NW, `reserv`: 13, 3 and 5
  empty rows) have larger shifts that make up for them.
- With the code's rule the lowest pixel lands below the hex center by the shift's y: 4 px median, 2 to
  13 px for 90% of Fallout 2's directions, 2–5 px for humans, up to 24 px for big monsters whose claws
  reach toward the viewer (`mascrp`, `mathng`). Fallout 1's Master (`mamstr`), which covers several
  hexes, is shifted (−32, −48).
- Humans' body centroid is within 2.5 px of the hex center horizontally in all six directions
  (`hmjmps`, `hfjmps`, `hmwarr`, `hmcmbt`, `hfprim`, `nmvalt`, `nfvalt`).
- The one-pixel question, settled by interface art. The code puts a mouse cursor's hotspot at
  (w/2 − shift_x, h − 1 − shift_y) (`gameMouseSetCursor`), and the shifts put that point exactly on the
  drawn tip or center: `stdarrow.frm` (0, 0), `crsshair.frm` (10, 10), `plus.frm` (8, 8),
  `scrnorth.frm` (15, 0), `scrsouth.frm` (16, 25). With h in place of h − 1 every hotspot would be a
  pixel low, `scrsouth`'s off the image. The hex cursor `msef000.frm` lands exactly on its hex's 32×16
  box with the code's rule, and the scroll-blocker hex `block2.frm` (31×14, shift (0, 6)) sits with one
  pixel above and below it in the box only with the code's rule.

Not checked: the height squash (cos φ), the European and UK releases, and objects as placed on real
maps.

## Sources

- `fallout2-ce` (commit e97087b): `src/tile.cc` (`tileInit`, `tileSetCenter`, `tileToScreenXY`,
  `tileFromScreenXY`, `tileGetTileInDirection`, `tileGetRotationTo`, `squareTileToScreenXY`,
  `squareTileToRoofScreenXY`, `tileRenderFloorsInRect`, `tile_fill_roof`), `src/map_defs.h`,
  `src/obj_types.h` (`Rotation`), `src/object.cc` (`objectGetRect`, `_obj_render_object`,
  `_obj_offset`, `objectSetLocation`), `src/animation.cc` (`_object_move`, the walk step),
  `src/game_mouse.cc` (`gameMouseSetCursor`, `gameMouseObjectsInit`, `_gmouse_3d_move_to`).
- `fallout1-ce` (commit 0609bcf): `src/game/tile.cc` and `src/game/object.cc`, which have the same
  constants.
- The projection and direction angles are derived on this page; the measurements are from the US
  releases' art (see [Checked](#checked-against-the-game-data)).
