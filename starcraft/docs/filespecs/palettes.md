# Palettes, remap tables and draw functions

StarCraft draws in 8-bit color. A GRP pixel is a palette index; what color it becomes depends on the
map's tileset, the player who owns the unit, and the image's **draw function**. This page covers what
a sprite reader needs. The terrain side, and much more measurement, is in random-map-generator's
`docs/starcraft/` notes (`wpe_palette.md`, `pcx_color_remaps.md`, `grp_images.md`), which this
summarizes.

## The palette: the tileset's .wpe

`tileset/<name>.wpe` is 256 entries of 4 bytes: red, green, blue, and a padding byte (1,024 bytes).
The game has no separate unit palette: everything on the map draws through the tileset's table.

Comparing the eight tilesets' tables splits it three ways:

| Entries | |
|---------|-|
| 0, 14–199, 255 | the same in every tileset. Units, player colors and every remap table use these |
| 1–13 | the terrain's color cycle (water, lava); the game rotates runs of it |
| 200–254 | the tileset's own colors; 248–254 also cycle on badlands, jungle, desert, ice and twilight |

So a unit looks the same on every tileset, and its pixels never cycle. The exceptions are a few
GRPs that draw in 200–245 on purpose, the doodads under `unit/thingy/tileset/` above all, and some
that do it by accident (an eighth of the siege tank's pixels).

`tileset/<name>-nc.wpe`, where it exists, is the same table with the cycled entries blanked; StarEdit
draws through it.

Interface screens (`glue/pal*/`) have palettes of their own; they don't matter for sprites.

## Player color: indices 8–15

A unit GRP stores its team-colored pixels as **indices 8 to 15**, a ramp from bright to dark. Before
drawing, the game replaces index `8 + s` with shade `s` of the owner's row in `game/tunit.pcx`: a
128 × 1 indexed PCX, 16 players × 8 shades, every value in the shared range.

In a viewer that uses `tunit.pcx`'s own palette, those pixels come out as a ramp of magentas, which
is why ripped StarCraft sprites look purple. In a tileset's `.wpe`, entries 8–13 are water, so a
sprite drawn without the remap looks wrong in another way.

The other game-wide tables in `game/`, `tselect.pcx`, `tminimap.pcx`, `thpbar.pcx`, `twire.pcx`
and `tblink.pcx`, recolor selection circles, minimap dots, hit point bars, wireframes and blinking
the same way.

## Draw functions

The `images.dat` draw function says how an image's pixels reach the screen:

| # | Draw function | Images | Pixels |
|--:|---------------|-------:|--------|
| 0 | normal | 546 | palette indices, 8–15 player colored |
| 1 | normal, not drawn for hallucinations | 28 | as 0 |
| 2–4 | cloaking, cloaked, decloaking | 0 | half-transparent through `trans50.pcx`, fading in or out; the game sets these on cloaked units |
| 5–7 | the same, PyMS's "vision" set | 0 | not drawn by OpenBW |
| 8 | EMP shockwave | 1 | shifts the pixels behind it: each sprite pixel is a distance to copy from |
| 9 | remapped | 145 | a lookup in the table the remapping field picks: glows, explosions, fire |
| 10 | shadow | 230 | silhouette only: darkens the pixels behind |
| 11 | hit point bar | 1 | |
| 12 | warp-in texture | 0 | the warp texture's frame, cut to the image's shape; `warpoverlay` picks the frame |
| 13 | selection circle | 20 | |
| 14 | player color override | 1 | the flag on the beacon |
| 15 | hidden, size rectangle only | 1 | |
| 16 | hallucination | 0 | set by the game |
| 17 | warp flash | 26 | the shape lights up what's behind through one row of `ofire.pcx`; all 26 are Protoss units' GRPs, for warping in |

### Remapping (draw function 9)

The remapping field picks one of the tileset's own lookup tables, under `tileset/<name>/`:

| Remapping | Table | Images |
|----------:|-------|-------:|
| 1 | `ofire.pcx`, orange fire | 66 |
| 2 | `gfire.pcx`, green fire | 13 |
| 3 | `bfire.pcx`, blue fire | 50 |
| 4 | `bexpl.pcx`, blue explosion | 15 |
| 5 | per PyMS the cloak's own; OpenBW loads `trans50.pcx` there | 1 |

Each table is 256 wide, one row per sprite index: the drawn color is
`table[sprite index − 1][color already on screen]`. So these images are **additive or translucent
lookups, not colors**: a glow's pixel is a brightness, and the result depends on what's behind it.
Interpolating such an image has to treat its indices as intensities, and never mix it into an opaque
one.

### Shadows (draw function 10)

A shadow image's pixel values are ignored: each covered screen pixel is replaced through row 18 of
the tileset's `dark.pcx` (256 × 32, 32 levels of darkness). Only the shape counts.

Unlike Diablo 1, the shadow isn't baked into the unit's frames, and unlike Diablo II, the game
doesn't project it. Each unit's iscript adds a separate shadow image under itself (`imgul`), and it
comes in three kinds:

| Kind | Units | Of 54 shadows |
|------|-------|--------------:|
| the unit's own GRP, drawn by function 10, following the unit's frame | flyers, 42 pixels lower; the SCV, drone, probe and vulture, 7 lower; the defiler, 3 | 22 |
| a hand-drawn shadow GRP that follows the unit's frame (`followmaingraphic`) | the infantry, the legged zerg and protoss units, the reaver, goliath and siege tank, the critters: `terran/tmaShad.grp` for the marine | 24 |
| a hand-drawn shadow GRP with its own script | the power-ups a worker carries: mineral chunks, gas, the data disk, Kerrigan's egg | 8 |

All 46 shadows that follow their unit run the same script, 275, which copies the unit's frame and
mirroring every tick. The offsets are the `imgul` arguments in the unit's Init script.

A shadow that follows the unit shows the frame the unit shows, so in-between frames for a unit need
in-between frames for its hand-drawn shadow too, made the same way.

## Checked against the game data

Checked on the MPQs of a 2017 classic install:

- The image counts per draw function and per remapping, over all 999 images of `images.dat`.
- The three kinds of shadow, by following each turning image's Init script to the function-10 images
  it adds with `imgul`, and comparing GRPs, offsets and scripts.
- The marine and the mutalisk, rendered through badlands' `.wpe` with player 1's `tunit.pcx` row:
  the team colors come out red, and nothing else looks off.
- The palette split, the remap tables' ranges and the table sizes were measured by
  random-map-generator over all eight tilesets.
- The draw functions' meanings, the lookup order of the remap tables and the shadow's `dark.pcx` row
  are from the sources, not checked here. Functions 11 and 13–16 are drawn by the interface, outside
  OpenBW's image drawing.

## Sources

- random-map-generator, `docs/starcraft/`: `wpe_palette.md`, `pcx_color_remaps.md`, `grp_images.md`.
- PyMS (MIT): the draw function and remapping names (`Data/DrawList.txt`, `Data/Remapping.txt`).
- OpenBW (`ui/ui.h`, image drawing; no license, read only): what functions 0–4, 8, 9, 10, 12 and 17
  do, `dark.pcx` row 18, and the tables it loads.
