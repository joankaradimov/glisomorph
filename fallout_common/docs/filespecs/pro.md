# PRO: prototypes

A PRO file is the template for one kind of object: an item, critter, piece of scenery, wall, floor tile or
"misc" object (exit grids, projectiles, effects). Map objects point at a prototype by its PID, and take
their default art, lighting, translucency and stats from it. For glisomorph the useful parts are the
links to art (FIDs), the translucency flags, and the few critter fields that change which animations
exist.

Files live in `proto/<type>/` (`items`, `critters`, `scenery`, `walls`, `tiles`, `misc`) with names like
`00000032.pro`. Each folder has a `<type>.lst`; line *n* (counting from 1) holds the file name for index
*n* (`_proto_list_str`). Always go through the list: the file name is usually the index in eight digits,
but not always. In both games line 1 of `items.lst` is `00000003.pro`, and that file holds PID 1.
Saved games keep gzipped copies of changed prototypes.

**All integers are big-endian.** Every field is an i32 except the single sound-ID bytes noted below.

## Common start

| Offset | Type | Field |
|--------|------|-------|
| 0x00   | i32  | PID: type in bits 24–31, index in bits 0–23 (the line in `<type>.lst`) |
| 0x04   | i32  | message ID: the name is the entry with this number in `text/<language>/game/pro_<type>.msg`, the description the entry after it. `<type>` is the folder name cut to four letters: `item`, `crit`, `scen`, `wall`, `tile`, `misc` (`protoInit`). Shipped protos all use 100 × the index |
| 0x08   | i32  | FID: the object's art, see [below](#fid) |

The PID type byte: 0 item, 1 critter, 2 scenery, 3 wall, 4 tile, 5 misc (`OBJ_TYPE_*` in
`obj_types.h`). The engine reads the rest according to it (`protoRead`).

Every type except tiles continues with:

| Offset | Type | Field |
|--------|------|-------|
| 0x0C   | i32  | light radius, in hexes (0–8) |
| 0x10   | i32  | light intensity, 0–65536 (65536 is full) |
| 0x14   | i32  | flags, see [below](#flags) |
| 0x18   | i32  | extended flags, depending on the type |
| 0x1C   | i32  | script ID (SID), −1 for none; walls, items, critters and scenery only. Script type in bits 24–31 (3 item, 4 critter), 0-based line in `scripts/scripts.lst` in bits 0–23 (`_obj_new_sid`) |

## Sizes

| Type      | Size (bytes) | Notes |
|-----------|--------------|-------|
| item      | 129, 65, 125, 122, 81, 69, 61 | armor, container, drug, weapon, ammo, misc, key |
| critter   | 416 (F2), 412 (F1) | see [F1 vs F2](#fallout-1-vs-fallout-2) |
| scenery   | 49 (door, stairs, elevator), 45 (ladders, generic) | |
| wall      | 36 | |
| tile      | 28 | |
| misc      | 28 | |

## Items

| Offset | Type | Field |
|--------|------|-------|
| 0x20   | i32  | item type: 0 armor, 1 container, 2 drug, 3 weapon, 4 ammo, 5 misc, 6 key |
| 0x24   | i32  | material (0 glass, 1 metal, 2 plastic, 3 wood, 4 dirt, 5 stone, 6 cement, 7 leather) |
| 0x28   | i32  | size (volume in containers) |
| 0x2C   | i32  | weight |
| 0x30   | i32  | cost |
| 0x34   | i32  | **inventory FID**: the picture in the inventory (`art/inven`), −1 for none (furniture such as desks and bookcases). The FID at 0x08 is the item on the ground (`art/items`) |
| 0x38   | u8   | sound ID |
| 0x39   | …    | type-specific data |

Item extended flags (0x18): bits 0–3 are the primary attack mode and bits 4–7 the secondary one (weapons
only), 0x100 big gun, 0x200 two-handed, 0x08000000 hidden (natural weapons such as claws), plus the
[action bits](#action-bits).

**Weapon** (122 bytes), the fields that matter for art:

| Offset | Type | Field |
|--------|------|-------|
| 0x39   | i32  | **animation code**: which set of critter animations a wielder uses. 0 none, 1 knife, 2 club, 3 sledgehammer, 4 spear, 5 pistol, 6 SMG, 7 rifle, 8 big gun, 9 minigun, 10 rocket launcher. It becomes the weapon code in the critter's FID, and the weapon letter (A, D–M) in critter FRM names |
| 0x3D–0x75 | i32 ×15 | min and max damage, damage type, two ranges, projectile PID, min strength, two AP costs, critical-failure table, perk, burst rounds, caliber, ammo PID, magazine size |
| 0x79   | u8   | sound ID |

The **projectile PID** (0x51) is a misc prototype whose FID is the projectile's art.

**Armor** (129 bytes): AC, 7 damage resistances, 7 thresholds, perk, then at 0x79 the **male FID** and
at 0x7D the **female FID**: the critter art the player switches to while wearing it.

Other item types hold only game rules: container (max size, open flags), drug (17 fields of stat
effects), ammo (6 fields), misc (power PID, power type, charges), key (key code). Their layout is in
`protoItemDataRead`; the wiki's tables agree with it.

## Critters

| Offset | Type | Field |
|--------|------|-------|
| 0x20   | i32  | **head FID**: the talking head for dialogue (`art/heads`), −1 if none. It's −1 in every shipped critter proto; dialogue scripts pick the head |
| 0x24   | i32  | AI packet (from `data/ai.txt`) |
| 0x28   | i32  | team |
| 0x2C   | i32  | critter flags, see below |
| 0x30   | i32 ×35 | base stats: SPECIAL, derived stats, 7 damage thresholds, 9 resistances, age, gender |
| 0xBC   | i32 ×35 | bonus stats, same order |
| 0x148  | i32 ×18 | skills |
| 0x190  | i32  | **body type**: 0 biped, 1 quadruped, 2 robotic |
| 0x194  | i32  | experience for killing it |
| 0x198  | i32  | kill type |
| 0x19C  | i32  | natural damage type (Fallout 2 only) |

The FID at 0x08 is the critter's base art: its index picks a line in `art/critters/critters.lst`, and the
engine fills in the animation and weapon code at run time.

Critter flags that change which animations are played:

| Flag   | Name in the engine      | Effect on art |
|--------|-------------------------|---------------|
| 0x0800 | `CRITTER_FLAT`          | when clear, the corpse is made flat and non-blocking at death; when set, it isn't. (The wiki reads this as "leaves no dead body") |
| 0x1000 | `CRITTER_SPECIAL_DEATH` | every death plays the "exploded to nothing" animation (`_check_death` callers in `actions.cc`) |
| 0x2000 | `CRITTER_LONG_LIMBS`    | melee reaches 2 hexes |
| 0x4000 | `CRITTER_NO_KNOCKBACK`  | never knocked back |

Body type gates behavior more than art: for example, only bipeds and robots open doors
(`animation.cc`), and only bipeds take items into their inventory without the barter flag (`item.cc`).
Fallout 1's protos use only 0 and 1: its robots are typed biped or quadruped.

## Scenery

| Offset | Type | Field |
|--------|------|-------|
| 0x20   | i32  | scenery type: 0 door, 1 stairs, 2 elevator, 3 ladder bottom, 4 ladder top, 5 generic |
| 0x24   | i32  | material |
| 0x28   | u8   | sound ID |
| 0x29   | …    | door: open flags, key code; stairs: two i32 (destination); elevator: type, level; ladders and generic: one i32 |

The destination fields of stairs, elevators and ladders are −1 in every shipped proto; the real values
are in the map objects (see [map.md](map.md#type-specific-data)). The generic field is never read, and
mostly holds leftover memory (0xCCCCCCCC).

Scenery extended flag 0x01 makes the player kneel to use the object (the "magic hands, ground"
animation instead of the middle one, `actions.cc`). It's set on manholes, trapdoors and the like.

## Walls, tiles and misc

| Type | Offset | Type | Field |
|------|--------|------|-------|
| wall | 0x20 | i32 | material |
| tile | 0x0C | i32 | flags (0 in every shipped tile proto) |
| tile | 0x10 | i32 | extended flags (0 in every shipped tile proto) |
| tile | 0x14 | i32 | SID (−1 in every shipped tile proto) |
| tile | 0x18 | i32 | material |
| misc | —    | —   | nothing past the common fields; the file ends after the extended flags at 0x18 |

Tile prototypes have **no light fields**: their flags are at 0x0C, not 0x14.

**Wall light type.** For walls and scenery, the top 5 bits of the extended flags say which way the wall
runs: 0 north/south, 0x08000000 east/west, 0x10000000 north corner, 0x20000000 south corner, 0x40000000
east corner, 0x80000000 west corner. At most one is set. The engine uses them to decide whether a wall is
between the camera and the player and should be cut away (`_obj_render_object`), and for lighting.
They're the only record of a wall's orientation on the ground.

## Action bits

Bits 11–15 of the extended flags say what the player can do with the object. Items, critters, scenery
and walls all use them; tiles and misc protos have none set.

| Bit    | Action   | What the engine does with it |
|--------|----------|------------------------------|
| 0x0800 | use      | can be used (`_proto_action_can_use`); containers always can |
| 0x1000 | use on   | can be used on something (`_proto_action_can_use_on`); drugs always can |
| 0x2000 | look at  | not tested |
| 0x4000 | talk to  | tested for non-critters only (`_proto_action_can_talk_to`): every critter can be talked to |
| 0x8000 | pick up  | tested for containers only (`_proto_action_can_pickup`): other items can always be picked up, and nothing but items ever can |

## FID

`buildFidInternal` in `fallout2-ce: src/art.cc`:

| Bits  | Field |
|-------|-------|
| 0–11  | index into `art/<type>/<type>.lst` |
| 12–15 | weapon code (critters) |
| 16–23 | animation (critters, heads) |
| 24–27 | art type: 0 items, 1 critters, 2 scenery, 3 walls, 4 tiles, 5 misc, 6 interface, 7 inventory, 8 heads, 9 backgrounds, 10 skilldex |
| 28–30 | direction + 1 when a critter animation is stored as one file per direction (`.fr0`–`.fr5`), else 0 |

Protos store the base FID with animation and weapon code 0, and an art type equal to the proto's own
type. How a FID becomes a file name, and the per-direction files, belong to [FRM](frm.md).

## Flags

When the engine creates an object from a prototype (`objectCreateWithFidPid` in `object.cc`), it copies
these flags, and only these. Objects loaded from a MAP keep the flags stored there instead.

| Flag        | Name | Meaning |
|-------------|------|---------|
| 0x00000008  | Flat | drawn with the floor, before other objects |
| 0x00000010  | NoBlock | doesn't block its hex |
| 0x00000800  | MultiHex | occupies more than one hex |
| 0x00001000  | NoHighlight | no outline when highlighted |
| 0x00004000  | TransRed | drawn translucent, red |
| 0x00008000  | TransNone | opaque, and never cut away near the player |
| 0x00010000  | TransWall | translucent wall blend |
| 0x00020000  | TransGlass | translucent glass blend |
| 0x00040000  | TransSteam | translucent steam blend |
| 0x00080000  | TransEnergy | translucent energy blend |
| 0x10000000  | WallTransEnd | changes the cut-away test for some walls |
| 0x20000000  | LightThru | light passes |
| 0x80000000  | ShootThru | projectiles pass |

**Translucency.** At most one Trans flag applies. When copying from the prototype, the engine checks
TransNone, then Wall, Glass, Steam, Energy, Red, in that order. When drawing, it needs exactly one Trans
bit: an object with several set matches none of the blend cases and is drawn opaque. A translucent object
is blended through a color table (`_wallBlendTable`, `_glassBlendTable`, `_steamBlendTable`,
`_energyBlendTable`, `_redBlendTable`) instead of drawn opaque. Sprites with these flags, such as glass,
steam or force fields, are effects in the art: their pixels are opaque palette colors meant to be
blended. Treat them like Diablo's cast overlays, not as solid bodies.

Which protos are translucent (the same in the US and European releases):

| Flag | Fallout 1 | Fallout 2 |
|------|-----------|-----------|
| TransGlass  | 4 scenery (bullet-proof glass) | 7 scenery (bullet-proof glass) |
| TransEnergy | 2 scenery (force fields) | 6 scenery (force fields) |
| TransRed    | 2 scenery (force fields) | 4 scenery (force fields, laser tripwires) |
| TransSteam  | none | 2 scenery (water, steam), 1 critter (Anna's ghost) |
| TransWall   | none | none |
| TransNone   | 35 items, 539 scenery, 75 walls, 26 misc | 42 items, 958 scenery, 178 walls, 28 misc |

Maps can add translucency the proto doesn't have: Fallout 1's Cathedral maps place Nightkin with
TransGlass (see [map.md](map.md#checked-against-the-game-data)).

## Fallout 1 vs Fallout 2

The layout is the same, field for field (`fallout1-ce: src/game/proto.cc`, `proto_read_protoSubNode`),
except:

- **Critters:** Fallout 1 has no natural damage type, so its critter PROs are 412 bytes. The Fallout 2
  engine treats the field as optional, and `fallout2-ce` notes two Fallout 2 critter PROs (Sentry Bot,
  Weak Brahmin) that are also 412 bytes. The data agrees: those two are the only short ones.
- **Kill types:** Fallout 1 has 15 (man through plant), Fallout 2 has 19 (adding gecko, alien, giant
  ant, big bad boss). The wiki marks plants as Fallout 2 only; `fallout1-ce` lists them, and Fallout 1's
  data uses the plant kill type once.

## Notes on the wiki

The falloutmods wiki page broadly agrees, with these differences. The data settles each of them.

- It says the first 56 bytes are common to every PRO. Only the first 12 are. Every tile and misc
  prototype is 28 bytes in total.
- It splits the extended flags into a 3-byte field and an attack-mode byte (items) or two 16-bit fields
  (walls and scenery). The engine reads one i32. The item values agree once shifted. In its "Repeated
  values" table, though, the action flags (use 0x0008, talk 0x0040, pick up 0x0080) are 8 bits lower
  than the engine's tests (0x0800, 0x4000, 0x8000). The data sets them at 0x0800–0x8000, never lower.
  The same table's "kneel down when using" (0x0001) is right; it's the scenery flag 0x01 above.
- It reads the wall light flags the same way the engine does, once the 16-bit field is placed in the top
  half. No proto sets two of them.
- It says a tile's flags are always −1. They're 0 in every tile proto; the −1 it saw is the SID at 0x14,
  where its 56-byte layout puts the flags.
- Its script ID gives type 2 to items and 3 to scenery. Scripted items and scenery both use type 3 (item
  scripts), critters 4; type 2 is the engine's timed script.

## Checked against the game data

Every PRO in four releases was parsed with the layout above: Fallout 1 US and European, 4,306 files each,
and Fallout 2 US and UK, 7,650 files each. So were the three protos in Fallout 2's official 1.02 patch
(`patch000.dat`). The archives were read with readers written from [dat.md](dat.md).

| Type | Fallout 1 | Fallout 2 | Sizes found |
|------|-----------|-----------|-------------|
| items | 242 | 531 | as in the table, per item type (below) |
| critters | 312 | 483 | F1: all 412. F2: 481 at 416, 2 at 412 |
| scenery | 908 | 1,851 | 49 for doors, stairs, elevators; 45 for the rest |
| walls | 1,176 | 1,633 | 36 |
| tiles | 1,622 | 3,102 | 28 |
| misc | 46 | 50 | 28 |

| Item type | Size | F1 | F2 | | Scenery type | Size | F1 | F2 |
|-----------|------|----|----|-|--------------|------|----|----|
| armor | 129 | 9 | 16 | | door | 49 | 42 | 98 |
| container | 65 | 77 | 115 | | stairs | 49 | 10 | 18 |
| drug | 125 | 14 | 28 | | elevator | 49 | 1 | 3 |
| weapon | 122 | 43 | 110 | | ladder bottom | 45 | 1 | 1 |
| ammo | 81 | 16 | 25 | | ladder top | 45 | 4 | 5 |
| misc | 69 | 77 | 229 | | generic | 45 | 850 | 1,726 |
| key | 61 | 6 | 8 | | | | | |

What held, in all files of all four releases:

- **Sizes:** every file is exactly the size its type and subtype give. No bytes are left over or
  missing.
- **Lists:** each `<type>.lst` has one line per file, every line names an existing file, and line *n*
  names the file whose PID index is *n*. The file names differ from the index for 14 items, 160 walls, 89
  tiles, 886 (F1) or 1,829 (F2) scenery and 2 Fallout 1 critters.
- **PIDs:** the type byte matches the folder.
- **Message IDs:** 100 × the index in every file. Every item, critter, scenery, wall and misc proto has
  its name entry; 810 (F1) and 2,289 (F2) tile protos have none, and many protos have no description.
- **FIDs:** the art type equals the proto's type, the animation, weapon and direction bits are 0, and
  the art exists: the file named on the list line for items, scenery, walls, tiles and misc, and
  `<base>aa.frm` for critters. The one exception is the children in the European releases (below).
- **Lights:** radius 0–8, intensity 0–65536.
- **SIDs:** −1, or type 3 (17 F1 and 38 F2 items, 4 and 35 scenery) or 4 (10 and 13 critters) with a
  line inside `scripts.lst`. The names fit (Fallout 1's radio runs `Radio.int`, Fallout 2's Magic 8-Ball
  `zi8Ball.int`), except for some items Fallout 2 inherited, whose old indices now name unrelated
  scripts.
- **Critters:** the head FID is −1 in all of them. Body types: F1 285 biped, 27 quadruped; F2 386, 79
  and 18 robotic. All 15 kill types occur in F1 (plant once, for the Master) and all 19 in F2. The
  natural damage type is 0 except for the two floaters (plasma) and the floating eye bot (electrical).
  Critter flags: Fallout 1 sets only 0x02 (barter, 171 protos). Fallout 2 sets more, among them the
  table's four: 0x0800 on 2 turrets, 0x1000 on 1, 0x2000 on 4, 0x4000 on 13.
- **Items:** the inventory FID is an existing `art/inven` file except for 73 (F1) and 114 (F2) furniture
  containers and shelves, which have −1. Every armor's male and female FIDs are critter FIDs whose art
  exists. Weapons use all 11 animation codes; min damage ≤ max damage in all 153, which confirms the
  field order; every projectile PID (16 and 31) is an existing misc proto; ammo PIDs are −1 or an
  existing ammo proto.
- **Scenery:** stairs, elevator and ladder fields are −1 in every proto, so they can't settle the stairs
  field order (see [map.md](map.md#notes-on-the-wiki)). The generic field holds 0xCCCCCCCC in 843 (F1)
  and 1,277 (F2) protos and other leftovers in most of the rest. 13 (F1) and 19 (F2) protos set the
  kneel flag 0x01.
- **Walls:** at most one light-type bit. F1: 454 north/south, 536 east/west, 67, 41, 37, 41 for the
  north, south, east, west corners. F2: 682, 744, 73, 52, 42, 40.
- **Tiles:** flags 0, extended flags 0, SID −1.
- **Action bits:** always at bits 11–15, never at the wiki's lower positions, and never on tiles or
  misc. Fallout 2: look on 481 of 483 critters, talk on 472; items use 176, use-on 128, look 450,
  pick-up 352; scenery use 201, look 1,476; walls use 13, look 937. Fallout 1 has the same pattern.

Odd values:

- Six ammo protos (10mm JHP and AP, .44 Magnum JHP, 14mm AP, .223 FMJ, 5mm AP) have flags 0xFFFFEFFF in
  both games: every bit but NoHighlight, all six Trans bits included. A new object made from one gets
  TransNone by the copy order. Seven Fallout 1 map objects made from them carry every Trans bit but Red,
  which the renderer draws opaque.
- One armor (Tesla Armor) has 0x66 in the attack-mode bits.

Differences between releases:

- **Fallout 1 European vs US:** 13 animal critter protos change stat 34 (gender) from 0 to 1. Nothing
  that affects art.
- **Fallout 2 UK vs US:** one critter (`critters/00000216.pro`, a mantis) gains a script. The 1.02 patch
  ships the same file, so the UK release already has that fix.
- **Children:** the European releases keep the child protos (2 in Fallout 1, 7 in Fallout 2) and their
  FIDs still point at `nachld`, but their `critter.dat` lacks `nachldaa.frm`. Fallout 1 European keeps
  five `nachld` files, all of them [aliased](sprite-metadata.md#aliases) codes (fire dance, three
  single-frame deaths, the called-shot picture); Fallout 2 UK keeps only `nachldna.frm`.
- **The 1.02 patch:** three protos, 416, 416 and 81 bytes, all consistent with the above. One is the
  mantis fix above, one changes an ammo value, and the third is identical to the shipped file.

Not checked: the stat, skill and drug fields beyond their count, the meaning of the material and sound
values, and saved-game PROs.

## Sources

- `fallout2-ce` (commit e97087b): `src/proto.cc` (`protoRead`, `protoItemDataRead`,
  `protoSceneryDataRead`, `_proto_list_str`, `protoInit`, `_proto_action_can_use`,
  `_proto_action_can_use_on`, `_proto_action_can_talk_to`, `_proto_action_can_pickup`),
  `src/critter.cc` (`protoCritterDataRead`), `src/proto_types.h`, `src/obj_types.h`, `src/art.cc`
  (`buildFidInternal`), `src/object.cc` (`objectCreateWithFidPid`, `_obj_render_object`),
  `src/proto_instance.cc` (`_obj_new_sid`), `src/actions.cc`.
- `fallout1-ce` (commit 0609bcf): `src/game/proto.cc`, `src/game/critter.cc` (`critter_read_data`),
  `src/game/proto_types.h`.
- [falloutmods wiki, PRO File Format](https://falloutmods.fandom.com/wiki/PRO_File_Format): field names
  and value lists (TeamX's document, translated).
