# Sprite metadata

[CEL](cel.md) and [CL2](cl2.md) files store pixels and little else. They don't record the frame width,
what each group means, how many frames an animation plays, or how fast. The game hard-coded all of that.
DevilutionX moved most of it into TSV tables:

- `assets/txtdata/` for Diablo,
- `mods/hf/txtdata/` for Hellfire, whose tables replace Diablo's when Hellfire is loaded.

This page collects it all. File references are to the DevilutionX repository. Paths are MPQ paths,
written with `/` (see [archives.md](archives.md)).

For widths alone there's a shortcut: `data/diabdat-clx.txt` in
[devilutionx-asset-optimizer](https://github.com/diasurgical/devilutionx-asset-optimizer) lists a width
for every CEL and CL2 in `DIABDAT.MPQ`. It's a good cross-check for the tables below.

## Directions

DevilutionX's `Direction` enum is in `Source/engine/direction.hpp`, and the displacements are in
`Source/engine/displacement.hpp`.

| Value | Name      | World step (x, y) | Screen step (px) | On screen  |
|------:|-----------|-------------------|------------------|------------|
| 0     | South     | (1, 1)            | (0, +32)         | down       |
| 1     | SouthWest | (0, 1)            | (−32, +16)       | down-left  |
| 2     | West      | (−1, 1)           | (−64, 0)         | left       |
| 3     | NorthWest | (−1, 0)           | (−32, −16)       | up-left    |
| 4     | North     | (−1, −1)          | (0, −32)         | up         |
| 5     | NorthEast | (0, −1)           | (+32, −16)       | up-right   |
| 6     | East      | (1, −1)           | (+64, 0)         | right      |
| 7     | SouthEast | (1, 0)            | (+32, +16)       | down-right |

- One world step in +x moves the screen by (+32, +16), and one in +y by (−32, +16).
- The values go clockwise on screen. The 8 directions are 45° apart on the ground. On screen the
  diagonals sit about 26.6° off horizontal, because of the 2:1 projection.
- **Direction16** (`Source/tables/misdat.h`) splits each step in two: South, South_SouthWest, SouthWest,
  West_SouthWest, West, and so on round to South_SouthEast. `Direction` value `d` corresponds to
  `Direction16` value `2·d`. The missile code computes it from world-space tile deltas, so its steps
  are 22.5° on the ground.

How each family picks a group:

| Family      | Group                                                                                                  |
|-------------|--------------------------------------------------------------------------------------------------------|
| players     | `sheet[direction]`                                                                                     |
| monsters    | `sheet[direction]`, or the same single list for every direction                                        |
| missiles    | `sheet[i]`, where `i` is a `Direction16`, a `Direction` or a state, depending on the missile           |
| cows        | `sheet[direction]`                                                                                     |
| everything else | a single list                                                                                      |

## Placement on screen

- A frame is drawn with its **bottom-left** pixel at the draw position (`ClxDraw`,
  `Source/engine/render/clx_render.hpp`). Frames of different heights therefore share a bottom edge.
- A tile's draw position is the bottom-left of its 64×32 diamond. Sprites are shifted left by
  `(width − 64) / 2` (`CalculateSpriteTileCenterX`, `Source/levels/dun_tile.hpp`), which centers them
  on the tile.
- So in frame coordinates, an actor's own tile center is at `x = width / 2`, 16 px above the bottom
  row. That's the natural pivot for comparing directions.
- Missiles take their shift from the `width2` column instead of the formula. It's usually
  `(width − 64) / 2`, but not always.
- A walking actor is also offset along its path in proportion to the animation's progress
  (`Source/engine/render/scrollrt.cpp`).

## Timing

- The game runs at 20 ticks per second (50 ms). An animation shows each frame for its delay, a number of
  ticks per frame.
- DevilutionX draws faster than 20 fps. When the game skips frames, it chooses which frame to show from
  the progress toward the next tick (`Source/engine/animationinfo.cpp`). Synthesized in-between frames
  would fit into that same gap.

## Players

**Path:** `plrgfx/<class>/<p>/<p><anim>.cl2`, where `<p>` is three letters: class, armour, weapon.
Example: `plrgfx/warrior/wln/wlnas.cl2` is a warrior in light armour, unarmed, standing in the dungeon.

Every file is an 8-group sheet in `Direction` order. The path is built in `Source/player.cpp`, and the
per-class values come from `assets/txtdata/classes/<class>/sprites.tsv`.

| Class     | `<class>`        | Class letter | Archive       |
|-----------|------------------|--------------|---------------|
| Warrior   | `warrior`        | `w`          | `DIABDAT.MPQ` |
| Rogue     | `rogue`          | `r`          | `DIABDAT.MPQ` |
| Sorcerer  | `sorceror` (sic) | `s`          | `DIABDAT.MPQ` |
| Monk      | `monk`           | `m`          | `hfmonk.mpq`  |

Hellfire's hidden Bard and Barbarian classes have no graphics in the retail archives. DevilutionX draws
them with the Rogue's and the Warrior's sprites unless optional graphics (`hfbard.mpq`, `hfbarb.mpq`)
are installed.

**Armour letter:** `l` light, `m` medium, `h` heavy.

**Weapon letter:**

| Letter | Weapon        |
|--------|---------------|
| `n`    | unarmed       |
| `u`    | shield only   |
| `s`    | sword         |
| `d`    | sword + shield |
| `b`    | bow           |
| `a`    | axe           |
| `m`    | mace          |
| `h`    | mace + shield |
| `t`    | staff         |

**Animations:**

| Code       | Animation                | Width column | Notes                                        |
|------------|--------------------------|--------------|----------------------------------------------|
| `as`, `st` | stand                    | `stand`      | dungeon, town                                |
| `aw`, `wl` | walk                     | `walk`       | dungeon, town                                |
| `at`       | attack                   | `attack`, or `bow` for bows |                               |
| `ht`       | got hit                  | `swHit`      |                                              |
| `bl`       | block                    | `block`      | only for weapon sets that can block          |
| `lm`       | cast a lightning spell   | `lightning`  |                                              |
| `fm`       | cast a fire spell        | `fire`       |                                              |
| `qm`       | cast any other spell     | `magic`      |                                              |
| `dt`       | death                    | `death`      | the game only uses weapon `n`                |

**Widths** (`sprites.tsv`):

| Class               | stand | walk | attack | bow | swHit | block | lightning | fire | magic | death |
|---------------------|------:|-----:|-------:|----:|------:|------:|----------:|-----:|------:|------:|
| Warrior, Barbarian  | 96    | 96   | 128    | 96  | 96    | 96    | 96        | 96   | 96    | 128   |
| Rogue, Bard         | 96    | 96   | 128    | 128 | 96    | 96    | 96        | 96   | 96    | 128   |
| Sorcerer            | 96    | 96   | 128    | 128 | 96    | 96    | 128       | 128  | 128   | 128   |
| Monk                | 112   | 112  | 130    | 130 | 98    | 98    | 114       | 114  | 114   | 160   |

**Frame counts** are in `classes/<class>/animations.tsv`, per weapon for attacks and per action
otherwise. For the Warrior, for example: `unarmedFrames 16`, `idleFrames 10`, `walkingFrames 8`,
`deathFrames 20`, `castingFrames 20`. There are also code overrides: a Warrior or Barbarian standing
with a bow in the dungeon has 8 frames, and dies in 15 in medium or heavy armour.

**Delays:** stand 4 ticks per frame, death 2, block 3, everything else 1. Walks, attacks and spells
can skip frames to speed them up.

**TRNs:** the loader applies two optional recolors: `<same path>.trn` for one file, and
`plrgfx/<trn>.trn` for the class, named by `sprites.tsv`. See [trn.md](trn.md).

**Extra frames:** some files have more frames than the engine plays. The Warrior's mace attack in heavy
armour (`whmat`) has 17 frames and plays 16. The Rogue's staff attack in medium and heavy armour
(`rmtat`, `rhtat`) has 18 and plays 16. The Monk has death animations for all 9 weapon sets, though
only `n` is used.

## Monsters

**Path:** `monsters/<assetsSuffix><letter>.cl2`, where `assetsSuffix` is a column of
`monsters/monstdat.tsv`. Example: `monsters/zombie/zombiew.cl2` is the Zombie's walk.

| Letter | Animation |
|--------|-----------|
| `n`    | stand     |
| `w`    | walk      |
| `a`    | attack    |
| `h`    | got hit   |
| `d`    | death     |
| `s`    | special: a second attack, eating, fading in or out, healing, etc. (only if `hasSpecial`) |

- Every file is an 8-group sheet in `Direction` order. The exceptions are `golem/golemd.cl2` and
  `golem/golems.cl2`, which are single lists used for every direction.
- **Width:** the `width` column, one value for all of a monster's animations. Diablo's monsters are
  96, 128 or 160 wide. Hellfire's range from 64 to 226.
- **Frames and delays:** `frames[6]` and `rate[6]`, comma-separated, in `n w a h d s` order. A count of
  0 means the file doesn't exist; for example, the Golem has no stand or got-hit animation.
- Several monster types can share one set of sprites through the same `assetsSuffix`.
- **Color variants:** `monsters/<trnFile>.trn`, for example `monsters/zombie/bluered.trn`. It's
  applied to every animation when the sprites load. Before applying it, DevilutionX replaces entries
  equal to 255 with 0. The Counselor family's walk animation is left untranslated.
- **Unique monsters** use their base type's sprites, plus `monsters/monsters/<trn>.trn` from the `trn`
  column of `monsters/unique_monstdat.tsv`. That TRN is applied at draw time, in place of lighting.
- **Corpses** are the last frame of the death animation, in the direction the monster died facing.
- **Hellfire** adds 26 monster types in `mods/hf/txtdata/monsters/monstdat.tsv`. Their sprites are in
  `hellfire.mpq`, apart from a few that reuse Diablo's. `hellfire.mpq` also replaces
  `goatlord/goatld.cl2` and `unrav/unrava.cl2`.
- **Oddities:**
  - Some files have more frames than the table says. `acid` death has 24 frames against 16, and
    `magma` walk 14 against 10.
  - `worm/worm*` is missing from every MPQ; its monster types are never spawned.
  - `darkmage/dmagew.cl2` is a 96-byte stub.

## Missiles

**Tables:** `missiles/missile_sprites.tsv` describes the graphics. `missiles/misdat.tsv` names the
graphic each missile uses, in its `graphic` column.

- **Paths:** `numFrames` counts files, not frames, despite its name.
  - If it's 1, the graphic is `missiles/<name>.cl2`.
  - Otherwise it's `missiles/<name>1.cl2` … `<name>N.cl2`. Each file is one group, and the game joins
    them into a sheet.
  - Every missile file is a single list.
- **Width:** `width`. The draw shift is `width2` (see [Placement](#placement-on-screen)).
- **Frames and delays:** `frameLength` and `frameDelay`, one value per group. A delay of 0 or 1 means
  every tick. Missile frames are numbered from 1.

What the groups mean (`Source/missiles.h`, `Source/missiles.cpp`):

| Groups | Meaning | Graphics |
|--------|---------|----------|
| 16 | `Direction16`: file `k` is value `k − 1` | `fireba` (Fireball), `farrow` (fire arrow), `larrow` (lightning arrow), `holy` (Holy Bolt), `acidbf` (acid); Hellfire: `ms_ora`, `ms_bla`, `ms_reb`, `ms_yeb`, `ms_blb` |
| 1 file, 16 frames | `Direction16` as the frame (1-based); never animated | `arrows` |
| 8 | `Direction` | `magball`, `firerun`, `spawns` |
| 9 | groups 1–8 are directions; group 9 is the explosion | `sklball` (Bone Spirit); also `doom`, which nothing seems to load |
| 2–3 | states such as start, idle, attack or end | `guard`, `firewal`, `portal`, `rportal`, `acidpud` |
| 1 | not directional | everything else |

The 16-direction graphics give 16 real views of the same projectile, 22.5° apart. That's ground truth for
direction interpolation: synthesize the odd directions from the even ones and compare.

Hellfire's missile graphics are in `hellfire.mpq`, defined in rows 48–60 of the Hellfire table.

## Objects

- **Path:** `objects/<file>.cel`, from the `file` column of `objects/objdat.tsv`. Example:
  `objects/l1braz.cel`.
- A single list, not directional. Door states and left or right variants are separate frames.
- **Width:** `animWidth` (64, 96, 128 or 160).
- **Frames and delay:** `animLen` frames and `animDelay` ticks each, for objects flagged `Animated`.
  For static objects, `animDelay` holds the frame to show. Frames are numbered from 1.
- Hellfire's objects (`l5*`, `l6pod*`, `urn*`) are in `hellfire.mpq`.

## Town NPCs (towners)

- **Path:** the `animPath` column of `towners/towners.tsv`, plus `.cel`. Example:
  `towners/smith/smithn.cel`.
- A single list, not directional. It has `animWidth` (96), `animFrames` and `animDelay`. The optional
  `animOrder` column gives the playback sequence as 0-based frame indices.
- Towners are drawn without lighting or TRNs.
- **Cows** are the exception: `towners/animals/cow.cel` is an 8-group CEL sheet, 128 wide, with 12
  frames at delay 3. Both values are hard-coded. The TSV's `direction` column picks the group.
- Hellfire adds the farmer, the cow farmer and the girl (in `hellfire.mpq`).

## Items on the ground

- **Path:** `items/<name>.cel`, with names from `ItemDropNames` in `Source/items.cpp`. Example:
  `items/goldflip.cel`.
- A single list, 96 wide (hard-coded `ItemAnimWidth`), with frame counts from `ItemAnimLs`. It plays
  at 1 tick per frame when the item drops, and the last frame is the one shown while it lies there.
- An item's cursor graphic picks its drop animation, through `ItemCAnimTbl`.

## Inventory and cursor graphics

- `data/inv/objcurs.cel`, 179 frames, and Hellfire's `data/inv/objcurs2.cel`, 61 frames. Both are
  single lists.
- **Widths per frame:** DevilutionX's `data/inv/objcurs-widths.txt` and `objcurs2-widths.txt`.
  - `objcurs.cel`: frame 1 is 33, frames 2–10 are 32, frame 11 is 23, frames 12–86 are 28 and
    frames 87–179 are 56.
  - `objcurs2.cel`: 28 or 56.
- Frames 1–11 are the mouse cursors. Item graphics start at 12. An item's footprint in inventory cells is
  its sprite size divided by 28.
- These don't animate, but they are the inventory pictures of every item.

## The TSV tables

The format is described in `assets/txtdata/Readme.md`: a Diablo 2-style TSV with an optional UTF-8 BOM
and a header row. Values contain no tabs or newlines. DevilutionX reads most tables **by column
position**, not by name, so a malformed row shifts its values silently. The `classes/<class>/*.tsv`
files are `Variable` / `Value` pairs instead.

The sprite-related columns:

| Table | Columns that matter here |
|-------|--------------------------|
| `classes/classdat.tsv` | `className`, `folderName` (the class's data folder) |
| `classes/<class>/sprites.tsv` | `classPath`, `classChar`, `trn`, and the widths: `stand`, `walk`, `attack`, `bow`, `swHit`, `block`, `lightning`, `fire`, `magic`, `death` |
| `classes/<class>/animations.tsv` | `<weapon>Frames` and `<weapon>ActionFrame` for the 9 weapon sets, plus `idleFrames`, `walkingFrames`, `blockingFrames`, `deathFrames`, `castingFrames`, `recoveryFrames`, `townIdleFrames`, `townWalkingFrames`, `castingActionFrame` |
| `monsters/monstdat.tsv` | `_monster_id`, `assetsSuffix`, `trnFile`, `width`, `hasSpecial`, `frames[6]`, `rate[6]`, `animFrameNum`, `animFrameNumSpecial` |
| `monsters/unique_monstdat.tsv` | `type`, `name`, `trn` |
| `missiles/missile_sprites.tsv` | `id`, `width`, `width2`, `name`, `numFrames`, `flags`, `frameDelay`, `frameLength` |
| `missiles/misdat.tsv` | `id`, `graphic` |
| `objects/objdat.tsv` | `id`, `file`, `flags`, `animDelay`, `animLen`, `animWidth` |
| `towners/towners.tsv` | `type`, `direction`, `animWidth`, `animPath`, `animFrames`, `animDelay`, `animOrder` |
| `items/itemdat.tsv`, `items/unique_itemdat.tsv` | `cursorGraphic` |

Example rows:

- `monstdat.tsv`, the Ghoul: `MT_BZOMBIE`, `assetsSuffix` `zombie\zombie`, `trnFile` `zombie\bluered`,
  `width` 128, `frames[6]` `11,24,12,6,16,0`, `rate[6]` `4,1,1,1,1,1`.
- `missile_sprites.tsv`, Fireball: `width` 96, `width2` 16, `name` `fireba`, `numFrames` 16, and
  `frameLength` 14 for every group.
- `objdat.tsv`, the cathedral brazier: `OBJ_L1LIGHT`, `file` `l1braz`, `animDelay` 1, `animLen` 26,
  `animWidth` 64.
- `towners.tsv`, Griswold: `TOWN_SMITH`, `animWidth` 96, `animPath` `towners\smith\smithn`,
  `animFrames` 16, `animDelay` 3.

## Direction groups that repeat

Some sheets reuse one direction's frames for another, byte for byte. A comparison of every player and
monster sheet, 1,360 in all, found these:

| File | Repeated groups |
|------|-----------------|
| `monsters/mage/magew.cl2`, `monsters/mage/maged.cl2` | all 8 identical (the Counselor family's walk and death) |
| `monsters/darkmage/dmaged.cl2` | all 8 identical |
| `monsters/mega/megah.cl2` | all 8 identical (the Balrog's and Slayer's got-hit) |
| `monsters/darkmage/dmageh.cl2` | NE = E |
| `monsters/magma/magmad.cl2` | S = SW |
| `plrgfx/rogue/rla/rlaas.cl2` | NE = E |
| `plrgfx/rogue/rht/rhtat.cl2` | W = NW |
| `plrgfx/monk/mlm/mlmdt.cl2` | SW = W and SE = S (a death animation the game never plays) |

The sheets with 8 identical groups are effects that look the same from every side. The partial repeats
look like mistakes in the original art.

Either way, leave these out when using direction groups as ground truth. sanctuary/formats' notes also
report flaws that a byte comparison can't find. They haven't been checked here:

- frames out of place in the fireman's got-hit, the Goat Lord's death and the Unraveler's attack;
- odd camera angles in the Gargoyle's, Rhino's and Zombie's deaths;
- only 3 truly different directions in the goat archer's death.

## Checked against the game data

Every player, monster and missile file named by the rules above was decoded with the widths above:
1,056 player files, 306 monster files and 245 missile files, 141,975 frames in all. Every frame
decoded to a whole number of rows. Details are in [cl2.md](cl2.md#checked-against-the-game-data).

Two monster cases didn't decode:

- the `worm` files are missing, as noted above;
- `darkmage/dmagew.cl2` is a stub.

A separate pass over the same MPQs checked the rest. It decoded the object, towner, item-drop and
cursor files with their widths, all cleanly, and compared frame counts with the tables. That pass is
the source of the "extra frames" and other oddities noted above.

## Sources

DevilutionX at commit `6f26339f4`: the TSVs named above, plus `Source/player.cpp`,
`Source/monster.cpp`, `Source/missiles.cpp`, `Source/tables/misdat.h`, `Source/objects.cpp`,
`Source/towners.cpp`, `Source/items.cpp`, `Source/cursor.cpp`, `Source/engine/direction.hpp`,
`Source/engine/displacement.hpp`, `Source/engine/render/scrollrt.cpp`,
`Source/engine/render/clx_render.hpp` and `Source/levels/dun_tile.hpp`.
