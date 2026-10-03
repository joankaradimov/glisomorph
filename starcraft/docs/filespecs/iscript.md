# iscript.bin: animation scripts

`scripts/iscript.bin` holds the bytecode that animates every image: which frame to show, for how long,
where to spawn overlays and shadows, when to play a sound or fire a weapon. A GRP is just frames; the
iscript is what makes them an animation. Each image in [images.dat](dat.md) names one script by ID,
and several images can share one: all 46 shadow images that follow their unit's frame run script 275.

## File layout

All values are little-endian; offsets are from the start of the file.

| Version | Start of the file |
|---------|-------------------|
| StarCraft (`StarDat.mpq`) | the ID table, at offset 0 |
| Brood War (`BrooDat.mpq`, `patch_rt.mpq`) | the offset of the ID table, which is at the end of the file; PyMS reads it as a u16, OpenBW as a u32 (the next two bytes are 0) |

The **ID table** is pairs of u16: a script ID and the offset of its header, ending with ID `0xFFFF`.
Brood War's has 398 scripts, the original's 342. IDs aren't contiguous.

A **script header**:

| Offset | Size | Field |
|-------:|------|-------|
| 0 | 4 | `SCPE` |
| 4 | u8 | type, which sets the number of animation entries |
| 5 | 3 | padding (OpenBW reads type as a u32) |
| 8 | u16 × N | one code offset per animation entry; 0 means the script has no such animation |

| Type | N | | Type | N |
|-----:|--:|-|-----:|--:|
| 0, 1 | 2 | | 20, 21 | 22 |
| 2 | 4 | | 23 | 24 |
| 12, 13 | 14 | | 24 | 26 |
| 14, 15 | 16 | | 26, 27, 28, 29 | 28 |

The entries, in order (`N` cuts the list short):

| # | Entry | # | Entry | # | Entry | # | Entry |
|--:|-------|--:|-------|--:|-------|--:|-------|
| 0 | Init | 7 | CastSpell | 14 | SpecialState2 | 21 | WarpIn |
| 1 | Death | 8 | GndAttkToIdle | 15 | AlmostBuilt | 22 | (unused) |
| 2 | GndAttkInit | 9 | AirAttkToIdle | 16 | Built | 23 | StarEditInit |
| 3 | AirAttkInit | 10 | (unused) | 17 | Landing | 24 | Disable |
| 4 | (unused) | 11 | Walking | 18 | LiftOff | 25 | Burrow |
| 5 | GndAttkRpt | 12 | WalkingToIdle | 19 | IsWorking | 26 | UnBurrow |
| 6 | AirAttkRpt | 13 | SpecialState1 | 20 | WorkingToIdle | 27 | Enable |

Different entries often share code; the marine's attack entries all run into one loop, and its
WalkingToIdle is its Init minus the first instruction.

## Opcodes

One byte of opcode, then its arguments. Types: `u8`/`u16` unsigned, `s8` signed, `label` a u16
offset into the file. An image ID is a row of `images.dat`, a sprite ID one of `sprites.dat`. An LO
slot numbers an image's overlay files: 0 attack, 1 damage, 2 special, 3 landing dust, 4 lift-off
dust, 5 shield (see [dat.md](dat.md#lo-overlay-offsets)). A direction step is 1/32 of a turn.

| # | Name | Arguments | Effect |
|--:|------|-----------|--------|
| 0x00 | `playfram` | u16 frame | show this frame; for turning images, the base of a 17-frame step |
| 0x01 | `playframtile` | u16 frame | show frame `frame + tileset index`, if the GRP has it |
| 0x02 | `sethorpos` | s8 x | set the image's horizontal offset |
| 0x03 | `setvertpos` | s8 y | set its vertical offset (not while the unit is cloaked) |
| 0x04 | `setpos` | s8 x, s8 y | set both |
| 0x05 | `wait` | u8 ticks | hold for this many game ticks |
| 0x06 | `waitrand` | u8 min, u8 max | hold for a random count of ticks, `min` to `max` |
| 0x07 | `goto` | label | jump |
| 0x08 | `imgol` | u16 image, s8 x, s8 y | add an image above this one, at this image's offset plus (x, y) |
| 0x09 | `imgul` | u16 image, s8 x, s8 y | the same, below (shadows) |
| 0x0A | `imgolorig` | u16 image | add an image above, kept at the main image's special-overlay offset |
| 0x0B | `switchul` | u16 image | the same, below |
| 0x0C | — | | not handled |
| 0x0D | `imgoluselo` | u16 image, u8 slot, u8 index | add an image above, at entry `index` of LO slot `slot` for the current frame |
| 0x0E | `imguluselo` | u16 image, u8 slot, u8 index | the same, below (OpenBW has no handler) |
| 0x0F | `sprol` | u16 sprite, s8 x, s8 y | create a sprite one elevation above, at an offset |
| 0x10 | `highsprol` | u16 sprite, s8 x, s8 y | (OpenBW has no handler) |
| 0x11 | `lowsprul` | u16 sprite, s8 x, s8 y | create a sprite at the lowest elevation (remains) |
| 0x12 | `uflunstable` | u16 flingy | (OpenBW has no handler) |
| 0x13 | `spruluselo` | u16 sprite, s8 x, s8 y | create a sprite at this elevation, at an offset, turned like this image |
| 0x14 | `sprul` | u16 sprite, s8 x, s8 y | create a sprite one elevation below, at an offset, turned like this image |
| 0x15 | `sproluselo` | u16 sprite, u8 slot | create a sprite above, at entry 0 of LO slot `slot` |
| 0x16 | `end` | | destroy the image |
| 0x17 | `setflipstate` | u8 | mirror the image, or not |
| 0x18 | `playsnd` | u16 sound | play a sound (`sfxdata.dat` row) |
| 0x19 | `playsndrand` | u8 n, u16 × n | play one of n sounds |
| 0x1A | `playsndbtwn` | u16 first, u16 last | play a random sound in the range |
| 0x1B | `domissiledmg` | | the bullet hits |
| 0x1C | `attackmelee` | u8 n, u16 × n | deal melee damage and play one of n sounds |
| 0x1D | `followmaingraphic` | | take the main image's frame and mirroring (shadows, overlays) |
| 0x1E | `randcondjmp` | u8 chance, label | jump if a random byte is at most `chance` |
| 0x1F | `turnccwise` | u8 steps | turn the unit counter-clockwise |
| 0x20 | `turncwise` | u8 steps | turn it clockwise |
| 0x21 | `turn1cwise` | | turn it one step clockwise, unless it has a target |
| 0x22 | `turnrand` | u8 steps | turn it one way or the other (clockwise 3 times in 4) |
| 0x23 | `setspawnframe` | u8 | used once; OpenBW has no handler |
| 0x24 | `sigorder` | u8 flags | set signal bits for the unit's order |
| 0x25 | `attackwith` | u8 weapon | fire the ground (1) or air (2) weapon |
| 0x26 | `attack` | | fire the weapon for the target: ground or air |
| 0x27 | `castspell` | | fire the order's spell |
| 0x28 | `useweapon` | u8 weapon | fire a given `weapons.dat` row |
| 0x29 | `move` | u8 pixels | move the unit forward this many pixels this tick, scaled by speed upgrades |
| 0x2A | `gotorepeatattk` | | allow the next attack to start; the script goes on |
| 0x2B | `engframe` | u8 frame | show this frame base, in the main image's direction (engine glows) |
| 0x2C | `engset` | u8 set | use frame set `set`: base = the main image's base + set × its frame count |
| 0x2D | — | | used once; OpenBW has no handler |
| 0x2E | `nobrkcodestart` | | start a part that orders can't interrupt |
| 0x2F | `nobrkcodeend` | | end it, and act on a queued order |
| 0x30 | `ignorerest` | | hold here until the unit has no target, checking every 10 ticks, then go idle |
| 0x31 | `attkshiftproj` | u8 pixels | fire the ground weapon from further along the facing |
| 0x32 | `tmprmgraphicstart` | | hide the image |
| 0x33 | `tmprmgraphicend` | | show it again |
| 0x34 | `setfldirect` | u8 direction | face direction 0–31 |
| 0x35 | `call` | label | call a subroutine (one level only) |
| 0x36 | `return` | | return from it |
| 0x37 | `setflspeed` | u16 | set the unit's top speed, in 1/256 pixel per tick |
| 0x38 | `creategasoverlays` | u8 n | add gas-building smoke at entry n of LO slot 2 |
| 0x39 | `pwrupcondjmp` | label | jump if this isn't the sprite's main image (a carried power-up) |
| 0x3A | `trgtrangecondjmp` | u16 pixels, label | jump if the target is within range |
| 0x3B | `trgtarccondjmp` | u16 direction, u16 arc, label | jump if the target lies within `arc` of `direction` |
| 0x3C | `curdirectcondjmp` | u16 direction, u16 arc, label | jump if the unit faces within `arc` of `direction` |
| 0x3D | `imgulnextid` | s8 x, s8 y | add the next image ID below this one, at an offset |
| 0x3E | — | | not handled |
| 0x3F | `liftoffcondjmp` | label | jump if the unit is flying (a lifted building) |
| 0x40 | `warpoverlay` | u16 frame | the warp-in effect's frame |
| 0x41 | `orderdone` | u8 flags | clear order signal bits |
| 0x42 | `grdsprol` | u16 sprite, s8 x, s8 y | create a sprite above, if a marine could stand there |
| 0x43 | — | | not handled |
| 0x44 | `dogrddamage` | | the bullet hits, as `domissiledmg` |

Directions in `trgtarccondjmp` and `curdirectcondjmp` are in 256ths of a turn, as unit facings are.

**Where code stops.** `goto` and `end` end a run of code; so does `return`. `ignorerest` holds the
script in place. `gotorepeatattk` doesn't stop anything, though the sources often list it with
these: it clears a flag, and all 62 in the file are followed by more code, 31 of them by a `goto`.

64 of the 69 opcodes occur in Brood War's file; the five that don't are 0x0C, 0x3E, 0x43,
`highsprol` and `uflunstable`. `wait` (3,609) and `playfram` (3,453) are most of it.

## Timing

`wait n` holds the current frame for n game ticks. The tick length depends on the game speed:

| Speed | Slowest | Slower | Slow | Normal | Fast | Faster | Fastest |
|-------|--------:|-------:|-----:|-------:|-----:|-------:|--------:|
| ms per tick | 167 | 111 | 83 | 67 | 56 | 48 | 42 |

Multiplayer is played on Fastest, about 24 ticks a second. An animation is a run of `playfram` and
`wait`, and in Brood War's file the waits are short:

| `wait` | 1 | 2 | 3 | 4–6 | 8–25 | 38–125 |
|--------|--:|--:|--:|----:|-----:|-------:|
| times used | 1,720 | 1,418 | 202 | 148 | 35 | 86 |

So most animations change frame every tick or every other tick, and the long waits are idle loops
(the marine idles with `waitrand 63 75`).

**Walking is often in the script.** `move n` moves the unit n pixels in the tick it runs. The marine
walks in 9 frames, one tick each, 4 pixels a tick:

```
Walking:  move 4, wait 1, playfram 85, move 4, wait 1, playfram 102, … playfram 68, goto Walking
```

44 units walk this way, and their `flingy.dat` movement control is 2: the marine, firebat, ghost,
medic, goliath, siege tank and spider mine; the larva, zergling, hydralisk, lurker, ultralisk,
defiler and broodling; the zealot, dragoon, dark templar, reaver and scarab; the critters and the
heroes among them. Every flyer, the SCV, the vulture, the drone, the probe and the archons move by
`flingy.dat`'s speed instead (control 0), and their walking animation doesn't move them.

## The direction a frame is drawn in

`playfram` sets a base frame. If the image turns, the frame drawn is picked from the base and the
unit's facing as described in [grp.md](grp.md#directions). Turning the unit (`turncwise` and the
like, or the game's own turning) changes the frame at once, without a new `playfram`.

## Checked against the game data

Checked on the MPQs of a 2017 classic install:

- Both header layouts, by reading `iscript.bin` from `StarDat.mpq` (342 scripts, table at 0) and from
  `BrooDat.mpq` and `patch_rt.mpq` (398 scripts each). The last two differ in 6 bytes, all in code
  no entry reaches.
- **The opcode table, by decoding the whole file**: starting from every animation entry of every
  script and following every jump and fall-through, 9,753 instructions decode in Brood War's file
  with no two overlapping, and neither script headers nor instructions overlap each other. The last
  instruction ends exactly where the ID table starts. About 1.8 KB of the file is code that no entry
  reaches. StarCraft's own file decodes the same way: 8,043 instructions, none overlapping.
- That `goto` and `end` stop: decoding past either runs into bytes that aren't code. The data can't
  tell for `ignorerest` and `return`; their effects are from OpenBW.
- The entry counts per type, by the same walk: headers sized by the table above never run into code.
- The `wait` statistics, the 62 uses of `gotorepeatattk`, the shadow script and the 44 walkers are
  from the same walk; the walkers' movement control is from `flingy.dat`.
- What each opcode does is from OpenBW's interpreter, not checked here.

## Sources

- PyMS's `FileFormats/IScriptBIN` (MIT): the opcode names, the entry counts per type and the entry
  names. Chkdraft (MIT) and OpenBW's `ins_data` agree on the argument sizes. OpenBW would derive the
  entry count as `(type + 2) & ~1`, which gives 30 for types 28 and 29; neither type occurs in the
  files.
- OpenBW (`bwgame.h`, `iscript_execute`) for what each opcode does. No license: read only.
- [staredit.net's "IceCC Animations"](https://wiki.staredit.net/wiki/IceCC_Animations) for the entry
  names.
- Chkdraft's `render/game_clock.h` and [staredit.net's "Game speed"](https://wiki.staredit.net/wiki/Game_speed)
  for the tick lengths.
