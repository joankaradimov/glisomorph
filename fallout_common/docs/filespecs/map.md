# MAP: maps

**Status: specified.** The header, variables, tiles, script lists and object records are specified, and
every shipped map parses with them to its last byte (see [below](#checked-against-the-game-data)). Most
script-record fields and what saved games change are only named, not checked.

A MAP file is one location: up to 3 elevations, each with a 100×100 grid of floor and roof tiles and the
objects (walls, scenery, items, critters, exit grids) standing on its 200×200 hex grid. Files are in
`maps/` (`*.map`). Saved games store the same format, gzipped, as `*.sav`. The grids themselves are
described in [geometry.md](geometry.md).

For glisomorph, maps are a source of context, not sprites: which walls and scenery appear together, how
objects are rotated, and real scenes to render against.

**All integers are big-endian.** Every field is an i32 unless noted.

## Layout

| Part | Size |
|------|------|
| header | 236 bytes |
| global variables | 4 × global count |
| local variables | 4 × local count |
| tiles | 40,000 bytes for each elevation that exists |
| scripts | 5 lists, variable |
| objects | variable, to the end of the file |

The engine reads them in this order (`mapLoad` in `fallout2-ce: src/map.cc`).

## Header

`mapHeaderRead`:

| Offset | Type      | Field |
|--------|-----------|-------|
| 0x00   | i32       | version: 19 in Fallout 1, 20 in Fallout 2 |
| 0x04   | char[16]  | file name, NUL-terminated; the bytes after the NUL can be junk |
| 0x14   | i32       | default entry hex (0–39999) |
| 0x18   | i32       | default entry elevation (0–2) |
| 0x1C   | i32       | default entry rotation (0–5, see [geometry.md](geometry.md#the-six-directions)) |
| 0x20   | i32       | number of local variables |
| 0x24   | i32       | map script: line number in `scripts/scripts.lst`, counting from 1 (the engine subtracts 1), 0 for none |
| 0x28   | i32       | flags, see below |
| 0x2C   | i32       | darkness (1 in every shipped map) |
| 0x30   | i32       | number of global variables |
| 0x34   | i32       | map number, −1 if none. Fallout 1: the entry number in `text/<language>/game/map.msg`; Fallout 2: the section in `data/maps.txt`. Both engines recompute it from the name on load |
| 0x38   | u32       | game time of the last visit, in ticks (0.1 s) |
| 0x3C   | i32 ×44   | unused, 0 |

Flags:

| Bit  | Meaning |
|------|---------|
| 0x1  | saved-game map (`.sav`); scripts keep their local variables |
| 0x2  | elevation 0 has **no** tile data |
| 0x4  | elevation 1 has no tile data |
| 0x8  | elevation 2 has no tile data |

Fallout 1's engine only accepts version 19; Fallout 2's accepts 19 and 20, and reads ladders differently
for each (see [below](#type-specific-data)).

## Variables

Right after the header: `global count` i32 values, then `local count` i32 values. For a map that isn't a
saved game, both engines then replace the globals with the ones in `maps/<name>.gam` (see
[other-formats.md](other-formats.md)).

## Tiles

For each elevation 0–2 whose "no tile data" bit is clear: 10,000 u32, one per square tile, in the order
`row * 100 + column` (`_square_load`).

| Bits  | Field |
|-------|-------|
| 0–11  | floor: index into `art/tiles/tiles.lst` |
| 12–15 | floor flags; the floor is drawn only when bit 0 (0x1000) is clear |
| 16–27 | roof: index into `art/tiles/tiles.lst` |
| 28–31 | roof flags; bit 0 (0x10000000) is the run-time "hidden" bit and is cleared on load |

Index 1 means "no tile" (`buildFid(OBJ_TYPE_TILE, 1, …)` is skipped by the renderer). Because the value
is big-endian, the roof comes first in the file: bytes 0–1 roof, bytes 2–3 floor, as the wiki says.
Columns are mirrored on screen; see [geometry.md](geometry.md#floor-and-roof-tiles).

## Scripts

Five lists, in the order system, spatial, timed, item, critter (`scriptLoadAll` in
`fallout2-ce: src/scripts.cc`). Each list is:

- i32 count;
- if count > 0, ⌈count / 16⌉ blocks. Each block is 16 script records (all 16, even if fewer are used),
  then i32 "used in this block" and i32 (a stale pointer, ignored).

A script record (`scriptRead`):

| Offset | Type | Field |
|--------|------|-------|
| 0x00   | i32  | SID: script type in bits 24–31 (0 system, 1 spatial, 2 timed, 3 item, 4 critter) |
| 0x04   | i32  | next (unused) |
| 0x08   | i32 ×2 | spatial only: location (a "built tile", below) and radius |
| 0x08   | i32  | timed only: time |
| +0x00  | i32  | flags |
| +0x04  | i32  | script index: line in `scripts/scripts.lst`, counting from 0 |
| +0x08  | i32  | program pointer (meaningless in a file) |
| +0x0C  | i32  | owner object ID: the ID at 0x00 of the object that runs the script |
| +0x10  | i32 ×10 | local-variable offset and count, return value, action, fixed parameter, action being used, overrides, unknown, "how much", run-info flags |

The `+` offsets follow the type-specific part, so a record is 64 bytes, 68 for timed scripts and 72 for
spatial ones. Each record's own SID decides its size, unused slots included. Unused slots hold leftover
memory, so their SIDs (and sizes) are effectively random: a reader that sizes them by the list, or always
reads 64 bytes, loses its place.

A built tile packs a hex and an elevation: bits 0–25 hex, 26–28 rotation, 29–31 elevation
(`BUILT_TILE_*` in `obj_types.h`). For stairs and ladders the rotation is the facing on arrival; every
shipped destination uses 3.

## Objects

`objectLoadAllInternal` in `fallout2-ce: src/object.cc`:

- i32 total number of objects: the top-level objects of all elevations, not counting inventory items (the
  engine only uses it to size a table);
- then for each elevation 0–2, always all three: i32 count, then that many object records.

Each object record is followed by its inventory: for each of its `inventory length` items, an i32
quantity and then a complete object record (with its own inventory, recursively).

### Object record

`objectRead` and `objectDataRead` (in `proto.cc`):

| Offset | Type | Field |
|--------|------|-------|
| 0x00   | i32  | object ID. Scripts find their owner by it; it isn't unique within a map |
| 0x04   | i32  | hex, −1 if not on the map (in an inventory; a few Fallout 1 maps store 0 there) |
| 0x08   | i32  | x: pixel offset from the hex center (see [geometry.md](geometry.md#anchoring-a-sprite-to-its-hex)) |
| 0x0C   | i32  | y: pixel offset |
| 0x10   | i32  | sx: cached screen x, recomputed by the engine |
| 0x14   | i32  | sy: cached screen y |
| 0x18   | i32  | current frame |
| 0x1C   | i32  | rotation, 0–5 |
| 0x20   | i32  | FID: the art, overriding the prototype's (see [pro.md](pro.md#fid)). Critters can carry a weapon and animation code here: armed critters, and corpses placed with a single-frame death |
| 0x24   | i32  | flags, the same bits as a PRO's (see [pro.md](pro.md#flags)), plus 0x01000000 in left hand, 0x02000000 in right hand, 0x04000000 worn. Non-player critters fight with the right hand (`critterGetItem2` in `combat_ai.cc`) |
| 0x28   | i32  | elevation (the engine overwrites it with the elevation being read) |
| 0x2C   | i32  | PID of the prototype |
| 0x30   | i32  | combat ID, −1 outside combat |
| 0x34   | i32  | light radius |
| 0x38   | i32  | light intensity |
| 0x3C   | i32  | outline (ignored on load) |
| 0x40   | i32  | SID of the attached script, −1 for none |
| 0x44   | i32  | script index, the same as in the script record, or −1; the engine refills it on load |
| 0x48   | i32  | inventory length |
| 0x4C   | i32  | inventory capacity |
| 0x50   | i32  | inventory pointer (meaningless) |
| 0x54   | …    | type-specific data |

### Type-specific data

**Critters** (PID type 1): 11 i32 (`objectDataRead`, `objectCritterCombatDataRead`):

| Offset | Field |
|--------|-------|
| 0x54   | reaction to the player |
| 0x58   | damage last turn |
| 0x5C   | maneuver flags |
| 0x60   | action points |
| 0x64   | combat results, `DAM_*` flags (0x80 dead) |
| 0x68   | AI packet |
| 0x6C   | team |
| 0x70   | who hit me (combat ID, −1 for none) |
| 0x74   | hit points |
| 0x78   | radiation |
| 0x7C   | poison |

**Everything else**: i32 flags at 0x54, then, at 0x58, data that depends on the **prototype's** subtype.
The MAP file doesn't say what that subtype is, so a reader has to load the object's PRO first.

| Object | Data at 0x58 |
|--------|--------------|
| weapon | ammo count, ammo PID |
| ammo | quantity |
| misc item | charges |
| key | key code |
| armor, container, drug | nothing |
| door | open flags |
| stairs | destination built tile, destination map (Fallout 2 order; see notes). A map ≤ 0 keeps the critter on this map (`useStairs`) |
| elevator | type, level |
| ladder (up or down) | version 19: destination built tile. Version 20: destination map (0 for this map), then destination built tile |
| generic scenery, walls, tiles | nothing |
| exit grid (misc PIDs 0x5000010–0x5000017) | map (−2 the world map, −1 the town map, else a map number), hex (usually −1 with −2 and −1), elevation, rotation |
| other misc | nothing |

## Notes on the wiki

The falloutmods wiki page (TeamX's document) agrees on the header, variables, tiles and the object
header, with these differences. The data settles all of them but the last.

- It calls the object's first field an unknown separator. It's the object ID: every scripted object's
  value equals its script's owner ID.
- It describes a hex as `00 00 XX YY`. The engine uses `row * 200 + column` (see
  [geometry.md](geometry.md#the-hex-grid)). About 22% of the objects' hexes have a low byte of 200 or
  more, which `XX YY` coordinates can't give and `row * 200 + column` does.
- For critters it puts an unknown field at 0x54 and the reaction at 0x58, then current AP, combat
  results and damage last turn. The engine reads the reaction at 0x54, then damage last turn, maneuver,
  action points, results. Both put the AI packet, team, hit points, radiation and poison at the same
  offsets. The data follows the engine: 0x60 is the proto's maximum AP for most critters, and 0x64 holds
  0x80 (dead) on the critters with 0 hit points.
- It swaps the hand bits (0x01000000 right, 0x02000000 left). In the data, critters whose FID carries a
  weapon code hold a weapon with that code flagged 0x02000000 (right, in the engine's names) far more
  often than one flagged 0x01000000.
- For version-20 ladders it puts the destination hex before the map number. `fallout2-ce` and
  `fallout2-re` read the map number first, and the data agrees: the first field is 0 or a small map
  number, the second a built tile.
- Its PRO page says a stairs map of −1 goes to the world map. The engine stays on the current map for any
  map ≤ 0, and the 26 Fallout 2 stairs with −1 all have a destination hex, as stairs within a map need.
- Stairs: the wiki and the Fallout 2 code read the destination hex, then the map. `fallout1-ce` and
  `fallout1-re` read the map first. Fallout 2's data matches its code. Fallout 1's data can't settle its
  order: all 69 stairs objects in its maps (and its 10 stairs protos) hold −1 in both fields, and the
  Fallout 1 engine never reads them after loading. A Fallout 1 reader loses nothing by using either order.

## Checked against the game data

Every map in four releases and the 1.02 patch was parsed with the layout above, using each game's PROs
for the object subtypes: Fallout 1 US and European (72 maps each; the European maps are byte-identical to
the US ones), Fallout 2 US and UK (155 each; only `navarro.map` differs, in its scripts and objects), and
the 15 maps in Fallout 2's official patch (`patch000.dat`, read with the patch's own protos and
`maps.txt`). **All 469 parse to the last byte**, with nothing left over and no failures.

| | Fallout 1 | Fallout 2 | 1.02 patch |
|-|-----------|-----------|------------|
| maps | 72 | 155 | 15 |
| version | 19 in all | 20 in all | 20 in all |
| elevations with tiles | 0 (41 maps), 0–1 (17), 0–2 (14) | 0 (109), 0–1 (24), 0–2 (20), 1–2 (2) | 0 (9), 0–1 (3), 0–2 (3) |
| objects on the map | 130,925 | 299,755 | 44,694 |
| items in inventories | 2,036 | 5,217 | 1,529 |
| script records in use | 2,146 | 4,319 | 1,006 |

Counts below are for the US releases; the European ones match them except where noted.

**Header.**

- The name matches the file name (ignoring case) in all maps. 16 (F1) and 49 (F2) names have junk after
  the NUL.
- Entry hex 0–39999, elevation 0 or 1, rotation 0 (one Fallout 2 map uses 2).
- Flags are 0x0, 0x8 or 0xC, plus 0x2 in two Fallout 2 maps whose elevation 0 is empty. Never 0x1.
- Darkness is 1 everywhere. The last visit time is 0 except in one map per game. The 44 unused fields
  are 0.
- Map script: with the index taken as 1-based, the script has the map's own name in 29 of the 66 Fallout
  1 maps that have one and 100 of 149 Fallout 2 maps; the others share a script, such as a random
  encounter's. Read 0-based, it never does. 6 maps per game have 0.
- Map number: all 66 Fallout 1 maps listed in `map.msg` store their entry number, the 6 unlisted ones −1.
  In Fallout 2, 106 of the 146 maps listed in `maps.txt` store their section, 37 store −1 and 3 another
  number; 7 of the 9 unlisted ones store −1.
- Locals: none in Fallout 1, some in 12 Fallout 2 maps. The global count equals the count in the map's
  `.gam` for 28 of the 31 Fallout 1 maps that have one, and 78 of 86 in Fallout 2.

**Tiles.** Every floor and roof index other than 1 names an existing tile FRM. The floor flags are 0
everywhere; the roof's hidden bit is set on 257 tiles in Fallout 1 and none in Fallout 2. Tile names
containing "roof" show up in the high half (751 F1, 4,218 F2) and almost never in the low half (0, 159),
which confirms the roof-first order.

**Scripts.** Counts are never negative. Each block's used count is 0–16, and the used counts add up to
the list's count in every list. Every used record's SID type matches its list, and every script index
falls inside `scripts.lst`. In use are only spatial (72 bytes), item and critter (64) records; no system
or timed ones. The unused slots carry 0xCCCCCCCC, text fragments and stale SIDs; 10 (F1) and 768 (F2) of
them are 68 or 72 bytes long because of their junk SID, which is why sizes must come from each record's
own SID. Spatial locations are valid hexes on elevations 0–2.

**Objects.**

- The total equals the number of top-level objects in every map.
- Map objects: hex 0–39999, and the elevation field equals the list they're in, for all. Rotation 0–5.
  x and y are 0 except on 17 (F1) and 55 (F2) objects; the frame is 0 except on 20 and 64.
- Every PID has a proto. The FID's art type equals the PID's type, and the art exists, for every object
  including inventory items. Critter FIDs with weapon and animation codes all resolve to files (taking
  the alias for aliased codes), except in the European releases, whose 25 (F1) and 55 (F2) child
  critters need the missing `nachldaa.frm`.
- Combat ID −1 and outline 0 everywhere. Every SID is in the script lists, and the script's owner ID
  equals the object's ID (1,970 F1, 4,036 F2). The script index at 0x44 equals the record's, or is −1
  (23 F1, 49 F2); 3 Fallout 2 objects hold a stale index.
- Object IDs repeat within 15 Fallout 1 and 134 Fallout 2 maps.
- Inventories hold only items, with hex −1 (265 Fallout 1 items store 0). One Fallout 1 inventory item
  has an inventory of its own.
- Critters: reaction, damage last turn, maneuver, radiation and poison are 0, and who-hit-me is −1, in
  all. Action points at 0x60 equal the proto's maximum for 814 of 1,095 (F1) and 2,320 of 2,451 (F2).
  Combat results at 0x64 are 0x80 (dead) on every critter with 0 hit points (34 F1, 75 F2) and 0 on the
  rest, except 5 Fallout 1 critters marked dead with hit points left. The team at 0x6C matches the proto
  for 958 (F1) and all 2,451 (F2);
  the AI packet at 0x68 for 628 and 2,232.
- Hands: critters drawn with a weapon code hold a weapon of that code flagged 0x02000000 in 217 (F1) and
  297 (F2) cases, one flagged 0x01000000 in 3 and 2.
- Item data: weapon ammo counts are within the magazine; ammo PIDs are the proto's ammo or another
  existing item (2 F1, 34 F2); ammo quantities are positive.
- Scenery in maps: 392 (F1) and 1,171 (F2) doors, 69 and 45 stairs, 0 and 50 elevators, 30 and 62
  ladders. Fallout 2's stairs: 42 have a built tile at 0x58 and −1 or a small map number at 0x5C, 3 have
  −1 in both. Its ladders: 0x58 is 0 or a small map number in all 62, 0x5C a built tile in 59 (one 0,
  one −1, one with an impossible elevation 7). Fallout 1's ladders hold only 0 or −1.
- Exit grids: 13,055 (F1) and 19,693 (F2). Map −2 or −1 comes with hex −1, except 22 (F1) and 61 (F2)
  world-map grids that give a hex anyway; a map number comes with a valid hex. Rotation is 0 in all
  Fallout 1 grids, 0–5 in Fallout 2. The only other misc objects are scroll blockers (`0x500000C`).
- Translucency on map objects: TransNone is common on walls, scenery, items and exit grids. TransGlass:
  96 (F1) and 280 (F2) scenery, plus 9 Nightkin in Fallout 1's Cathedral maps, though their proto isn't
  translucent. TransSteam: 112 Fallout 2 scenery and 2 copies of Anna's ghost. TransEnergy 15 and 38,
  TransRed 8 and 6 scenery. Seven Fallout 1 items carry several Trans bits (see
  [pro.md](pro.md#checked-against-the-game-data)).

Not checked: saved-game maps (`.sav`), the script fields beyond SID, index and owner, and the elevator
types against the elevator tables.

## Sources

- `fallout2-ce` (commit e97087b): `src/map.cc` (`mapLoad`, `mapHeaderRead`, `_square_load`,
  `mapHandleTransition`), `src/scripts.cc` (`scriptLoadAll`, `scriptListExtentRead`, `scriptRead`,
  `scriptsLoadScriptsList`), `src/object.cc` (`objectRead`, `objectLoadAllInternal`), `src/proto.cc`
  (`objectDataRead`, `objectCritterCombatDataRead`), `src/proto_instance.cc` (`useStairs`,
  `useLadderUp`, `useLadderDown`), `src/combat_ai.cc`, `src/obj_types.h`.
- `fallout1-ce` (commit 0609bcf): `src/game/map.cc` (`map_read_MapData`, `map_match_map_number`,
  `map_get_name_idx`), `src/game/scripts.cc`, `src/game/object.cc` (`obj_read_obj`),
  `src/game/proto.cc` (`proto_read_protoUpdateData`).
- `fallout1-re` (ac9784b) and `fallout2-re` (b135fc4), `src/game/proto.c`: the stairs field order.
- [falloutmods wiki, MAP File Format](https://falloutmods.fandom.com/wiki/MAP_File_Format) and
  [PRO File Format](https://falloutmods.fandom.com/wiki/PRO_File_Format).
