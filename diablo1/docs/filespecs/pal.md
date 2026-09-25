# PAL: palettes

Every Diablo graphic is 8-bit and palette-indexed. A PAL file is the palette itself.

## Format

768 bytes: 256 entries of `R, G, B`, one byte each, using the full 0–255 range. It's not 6-bit VGA.
There's no header and no alpha. Transparency lives in the sprite encoding ([CL2](cl2.md), [CEL](cel.md))
as skip runs, never as a palette entry.

Index 0 is black. In sprites it's mostly the drop shadow, drawn as opaque black pixels. DevilutionX's
`ClxDrawOutlineSkipColorZero` describes index 0 as "usually shadows" and leaves it out when outlining
a sprite.

## Which palettes exist

| Path                                     | Used for                                                        |
|------------------------------------------|-----------------------------------------------------------------|
| `levels/towndata/town.pal`               | the town                                                        |
| `levels/l{n}data/l{n}_{v}.pal`           | dungeon type `n` (1 cathedral, 2 catacombs, 3 caves, 4 hell); the game picks variant `v` from 1–4 at random for each level |
| `levels/l1data/l1_2.pal`, `levels/l2data/l2_2.pal`, `levels/l3data/l3pfoul.pal`, `levels/l3data/l3pwater.pal` | fixed palettes for some quest levels |
| `nlevels/l5data/l5base.pal`              | Hellfire crypt (in `hellfire.mpq`)                              |
| `nlevels/l6data/l6base{1..5}.pal`        | Hellfire nest (in `hellfire.mpq`)                               |
| `gendata/cut*.pal`, `nlevels/cutl5.pal`, `nlevels/cutl6.pal` | loading screens                               |
| `ui_art/diablo.pal`, `ui_art/hellfire.pal` | DevilutionX's menus; these ship in `devilutionx.mpq`, not the game MPQs |

The level palettes are loaded by `LoadRndLvlPal` in DevilutionX's `Source/engine/palette.cpp`. The rest
are loaded in `Source/interfac.cpp`, `Source/levels/setmaps.cpp` and `Source/quests.cpp`.

## Layout

The 23 level palettes (town, the 16 dungeon variants, and the 6 Hellfire ones) are **identical at
index 0 and at indices 128–255**, and differ at 1–127:

- **1–127** are level colors, used by dungeon tiles.
- **128–255** are shared colors, used by sprites. Monsters, players and items look the same on every
  level. Every pixel of every player, monster and missile frame (141,975 frames) is 0 or 128–254, and so
  is every pixel of the sampled towner and item sprites.

So any level palette renders sprites correctly. Use `town.pal` as the default.

The light tables (`MakeLightTable` in `Source/engine/light_tables.cpp`) treat the palette as runs of
shades, called ramps:

| Indices | Ramps                    |
|---------|--------------------------|
| 0–127   | 8 ramps of 16 shades     |
| 128–159 | 4 ramps of 8 shades      |
| 160–255 | 6 ramps of 16 shades     |

Within a ramp, the lowest index is the brightest. Light level `k`, from 0 (full light) to 15 (black),
darkens a pixel by moving it `k` steps toward the ramp's end, or `k/2` steps in 8-shade ramps. Past the
end it becomes 0 (black).

In `town.pal`, luminance falls strictly from the first to the last entry of every ramp in 128–239.
240–255 does too, except for 255, which is pure white. The light tables special-case index 255, and
the sampled sprites never use it.

## Color cycling

Some levels animate part of the level range by rotating palette entries every frame or two
(`Source/engine/palette.cpp`, `Source/diablo.cpp`):

| Level type     | Rotated indices              |
|----------------|------------------------------|
| caves (L3)     | 1–31                         |
| Hellfire crypt | 1–15 and 16–31               |
| Hellfire nest  | 1–8 and 9–15                 |
| hell (L4)      | none; it animates its light tables instead |

Sprites don't use these indices, so cycling never affects them.

## Notes for glisomorph

- Interpolated frames are computed in RGB, but the result has to go back to palette indices. Keep it
  in 128–254 so the sprite still looks the same on every level.
- Lighting and TRN recoloring ([trn.md](trn.md)) both work on indices, ramp by ramp. A pixel that's
  mapped to the nearest color by RGB alone can end up in a different ramp from its neighbours. It then
  darkens differently, or doesn't get recolored with the rest of the monster. Choosing the ramp from
  the source frames first, and only then the shade, avoids both problems.

## Checked against the game data

The shared range was found by comparing all 23 level palettes, extracted from the retail
`DIABDAT.MPQ` and `hellfire.mpq`. The sprite index usage comes from decoding every player, monster and
missile CL2 file (see [cl2.md](cl2.md#checked-against-the-game-data)), plus `towners/animals/cow.cel`
and `items/armor2.cel`.
