# The .dat tables: from a unit to its frames

StarCraft's game data is a set of fixed-size tables under `arr/`. Four of them link a unit to what's
drawn:

```
units.dat    a unit: hit points, weapons, ... and its flingy
 └─ flingy.dat   how it moves and turns, and its sprite
     └─ sprites.dat   a drawn object at one place on the map, and its main image
         └─ images.dat    a GRP, how it's drawn, its iscript, its overlays
```

A sprite can hold several images at once: the unit, its shadow under it, a muzzle flash, fire when
damaged. The iscript adds and removes them (see [iscript.md](iscript.md)). Brood War's tables are in
`BrooDat.mpq`, some patched in `patch_rt.mpq`.

## Layout

Every table is a set of **parallel arrays**: all entries' first field, then all entries' second
field, and so on, with no header. Some fields cover only a range of entries; the array then holds
just those. All values are little-endian. The game reads Brood War's tables: `units.dat`,
`flingy.dat` and `weapons.dat` from `patch_rt.mpq`, the others from `BrooDat.mpq`.

| File | Entries | Bytes |
|------|--------:|------:|
| `units.dat` | 228 | 19,876 |
| `flingy.dat` | 209 | 3,135 |
| `sprites.dat` | 517 | 3,229 |
| `images.dat` | 999 | 37,962 |
| `weapons.dat` | 130 | 5,460 |

StarCraft's own tables, in `StarDat.mpq`, have the same layouts with fewer entries: 755 images,
353 sprites, 184 flingies and 100 weapons. Its `units.dat` has the same 228 units but is 684 bytes
(3 a unit) shorter, so Brood War's has a field or two more.

Names: unit `n`'s is the string at index `n` of `rez/stat_txt.tbl` (Terran Marine is unit 0). File
paths are in `arr/images.tbl`, counting from 1 (see [Strings](#strings)).

## images.dat

| Field | Size | |
|-------|------|-|
| GRP | u32 | the GRP's path in `images.tbl`, counting from 1, relative to `unit/` |
| graphics turns | u8 | 1: the GRP has 17-frame direction steps ([grp.md](grp.md#directions)) |
| clickable | u8 | |
| use full iscript | u8 | |
| draw if cloaked | u8 | |
| draw function | u8 | how pixels are drawn; see [palettes.md](palettes.md#draw-functions) |
| remapping | u8 | lookup table for draw function 9; see [palettes.md](palettes.md#draw-functions) |
| iscript | u32 | the script ID in `iscript.bin` |
| shield overlay | u32 | `images.tbl` path of an LO* file, or 0 |
| attack overlay | u32 | the same |
| damage overlay | u32 | the same |
| special overlay | u32 | the same |
| landing dust overlay | u32 | the same |
| lift-off dust overlay | u32 | the same |

The 999 images name 833 distinct GRPs; 159 images turn. Shadows are images of their own (draw
function 10), added under the unit by `imgul`.

## sprites.dat

| Field | Size | Entries |
|-------|------|---------|
| image | u16 | all 517 |
| health bar width | u8 | 130–516 |
| unknown | u8 | all |
| visible | u8 | all |
| selection circle image | u8 | 130–516 |
| selection circle vertical offset | u8 | 130–516 |

Entries 0–129 have no health bar or selection circle: no unit's flingy uses them. They're the
sprites of effects, missiles and doodads.

## flingy.dat

| Field | Size | |
|-------|------|-|
| sprite | u16 | |
| top speed | u32 | in 1/256 pixel per tick |
| acceleration | u16 | |
| halt distance | u32 | |
| turn radius | u8 | how far the facing turns per tick, in 256ths of a circle |
| iscript mask | u8 | |
| movement control | u8 | 0 flingy.dat, 1 partially mobile / weapon, 2 iscript |

Speeds are in 1/256 pixel per tick (OpenBW's `setflspeed`). 44 units with movement control 2 walk
by the iscript's `move` opcodes, frame by frame, and 41 of them have a speed of 1 here, unused: the
infantry, the legged zerg and protoss units, the goliath, the siege tank, the reaver and the
critters. For them the walking speed and the animation are the same thing, which matters if
in-between frames are added: positions have to be interpolated with the frames. Flyers and the
hovering workers and vulture have control 0 and a real speed (see [iscript.md](iscript.md#timing)).

## units.dat

The table has over 50 fields; these are the ones about drawing, at their offsets:

| Offset | Field | Size | Entries |
|-------:|-------|------|---------|
| 0 | flingy | u8 | 228 |
| 228 | subunit 1 | u16 | 228; 228 means none |
| 684 | subunit 2 | u16 | 228 |
| 1140 | infestation | u16 | 106–201 |
| 1332 | construction image | u32 | 228; an `images.dat` row |
| 2244 | starting direction | u8 | 228; 32 means random |

A **subunit** is a second unit drawn as part of this one: the siege tank's turret (unit 6 on unit 5),
the goliath's guns. Each turns on its own, with its own sprite and images.

## LO* overlay offsets

`images.dat`'s overlay fields name small files of per-frame offsets. What each field names in the
data:

| Field | Images | Files |
|-------|-------:|-------|
| shield | 583 | `.los`: where shield hits flash |
| attack | 13 | `.loa`, `.log`, `.lol`, `.lox`: where a muzzle flash or missile starts |
| damage | 54 | `.lof`: where fire and blood go when damaged |
| special | 15 | `.lol` (engine glows, the tank's gun), `.loo` (where the SCV and probe carry minerals), `.los` (gas-building smoke), `.loa`, `.lob` |
| landing dust | 12 | `.lou` (Terran buildings and dropships), `.lob` (zerg births) |
| lift-off dust | 10 | `.lod` |

The extensions are naming habits rather than formats, and the sources name them inconsistently
(staredit.net reads `.lod` as landing and `.lou` as lift-off, the reverse of the fields the files sit
in). Every one has the same layout:

| Offset | Size | Field |
|-------:|------|-------|
| 0 | u32 | frame count, usually the same as the image's GRP |
| 4 | u32 | offsets per frame |
| 8 | u32 × frames | offset of each frame's list, from the start of the file |

Each list is that many pairs of `s8 x, s8 y`, relative to the image's center. Frames can share a
list. The list is indexed by the frame actually drawn, so for a turning image frame `base + d` holds
direction d, and when the frame is drawn mirrored, x is negated (OpenBW, `get_image_lo_offset`).

## Strings

A `.tbl` is a u16 count, a u16 offset per string, then the NUL-terminated strings. `arr/*.tbl` hold
paths, `rez/*.tbl` text. The `images.dat` fields count from 1: a value of `n` names the table's
`n`th string, at index `n − 1`, and 0 names none. `rez/stat_txt.tbl` holds unit, weapon and upgrade
names; unit `n`'s is at index `n`. random-map-generator's `tbl_string_tables.md` has the counts per
archive.

## Checked against the game data

Checked on the MPQs of a 2017 classic install:

- Every file size in the table above, and that `images.dat`'s fields fill its 37,962 bytes exactly.
  StarCraft's entry counts are its files' sizes divided by the bytes an entry takes.
- `flingy.dat`'s and `sprites.dat`'s fields add up to the file sizes.
- The chain, for the marine, zergling, zealot, mutalisk and vulture: unit → flingy → sprite → image
  ends at their GRPs (the marine: flingy 78, sprite 235, image 239, `terran/marine.grp`).
- The `units.dat` offsets above: the siege tank's subunit is the tank turret, the command center's
  construction image is `TBldLrg.grp`, and starting directions are 0, 32 or in between.
- Every LO* file `images.dat` names reads with the layout above: every frame's list fits in the file.
  84 of the 96 distinct files have the frame count of a GRP whose image uses them.
- Which files each overlay field holds, from the data; the order of the fields agrees with OpenBW's
  reader.
- That no unit's flingy uses sprites 0–129, and the 44 walkers with their speeds.
- The meaning of the unchecked fields (clickable, use full iscript, the movement control values,
  flingy.dat's units, units.dat beyond the fields listed) is from the sources.

## Sources

- PyMS (MIT): `FileFormats/DAT/*.py` for every field, `FileFormats/LO.py` for LO* files.
- Chkdraft (MIT) for `images.dat`; OpenBW (`data_loading.h`, `load_offsets`,
  `get_image_lo_offset`; read only) for the field order, LO* files and their slots.
- [staredit.net's "Modding Files Overview"](https://wiki.staredit.net/wiki/Modding_Files_Overview)
  for the extensions.
- random-map-generator's `docs/starcraft/` notes (the `.tbl` layout and id counting).
