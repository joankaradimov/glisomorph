# Sprite metadata: how Diablo II assembles an animation

Diablo II rarely draws a unit from a single sprite. A player, monster or object is a stack of
**layers**. Each layer is its own [DCC](dcc.md) (sometimes [DC6](dc6.md)) file, chosen by the unit's
equipment or variant. A [COF](cof.md) file says which layers exist and in which order to draw them,
frame by frame. [AnimData.d2](animdata.md) gives the speed. Color maps recolor individual layers (see
[palettes.md](palettes.md)).

This page covers the naming, the tables and the conventions that tie those files together. Unless noted
otherwise, it follows Paul Siramy's *Extracting Diablo II Animations*, written against patches 1.09d and
1.10. Tables are `data/global/excel/*.txt`. MPQ paths are written with `/` here; the game uses `\`.

## Unit types and base paths

| Base path                 | Units                                        |
|---------------------------|----------------------------------------------|
| `data/global/chars/`      | player characters                            |
| `data/global/monsters/`   | monsters and NPCs                            |
| `data/global/objects/`    | objects: torches, chests, shrines, …         |
| `data/global/missiles/`   | missiles                                     |
| `data/global/overlays/`   | effects drawn over units: auras, curses, explosions |

Each unit has a two-letter **token** and a folder under its base path:

```
<base path>/<token>/cof/<token><mode><weapon class>.cof     one COF per mode and weapon class
<base path>/<token>/cof/palshift.dat                         color variants (most monsters)
<base path>/<token>/<layer>/<token><layer><variant><mode><weapon class>.dcc
```

Examples, for the Barbarian in town with two swords:

- `data/global/chars/ba/cof/batn1ss.cof`: token `BA`, mode `TN`, weapon class `1SS`.
- `data/global/chars/ba/hd/bahdbhmtnhth.dcc`: layer `HD` (head), variant `BHM` (the helm's graphic),
  mode `TN`, weapon class `HTH`.

The weapon class in a DCC name is **the one the COF assigns to that layer**, not the COF's own. In
`batn1ss.cof`, the arms and hands (`LA`, `RA`, `LH`, `RH`) use `1SS` graphics, while the head, torso,
legs and shoulder pads (`HD`, `TR`, `LG`, `S1`, `S2`) use `HTH`. That's how the game avoids drawing a
separate head for every weapon. See [cof.md](cof.md).

Some layers are DC6 instead of DCC: Mephisto, Tyrael, the Maggot Queen's death and Mephisto's Hell Gate,
for example. `data/global/overlays/` holds 384 DCCs and one DC6, and `data/global/uncompoverlays/` holds
11 DC6s.

## Tokens

- **Players:** `PlrType.txt`. Classic classes are in `d2char.mpq` and the expansion's in `d2exp.mpq`.

  | Class       | Token |
  |-------------|-------|
  | Amazon      | `AM`  |
  | Sorceress   | `SO`  |
  | Necromancer | `NE`  |
  | Paladin     | `PA`  |
  | Barbarian   | `BA`  |
  | Druid       | `DZ`  |
  | Assassin    | `AI`  |

- **Monsters:** up to 1.09d, the animation token is in `MonType.txt`, while `MonStats.txt` has a second
  token that only locates `palshift.dat`. Since 1.10 the token is the `Code` column of `MonStats.txt`;
  the Fallen, for example, are `FA`.
- **Objects:** the token of `Objects.txt`. The Arcane Sanctuary's teleport pad is `7H`.

## Layers

`Composit.txt` defines 16 layers, also called components:

| Layer | Name      | Layer | Name     |
|-------|-----------|-------|----------|
| `HD`  | head      | `SH`  | shield   |
| `TR`  | torso     | `S1`  | special 1 |
| `LG`  | legs      | `S2`  | special 2 |
| `RA`  | right arm | `S3`  | special 3 |
| `LA`  | left arm  | `S4`  | special 4 |
| `RH`  | right hand | `S5` | special 5 |
| `LH`  | left hand | `S6`  | special 6 |
|       |           | `S7`, `S8` | special 7 and 8 |

Layers overlap rather than tile. The right arm, for example, overlaps the torso and the right hand. The
draw order therefore matters, and it changes with direction and frame: a Barbarian facing west has his
shield in front, but facing east it's behind him. The COF holds that order.

For players, the special layers carry the shoulder pads (`S1` right, `S2` left) and other extras. For
monsters and objects, they carry whatever the artist split off. The teleport pad, for example, is a stone
(`TR`), a red aura (`S1`) and a translucent mask (`S2`).

## Which variant each layer uses

**Players.** Only four equipped items change the animation: the helm, the body armor, and the two hands.
Patch 1.10 also added overlays for set items.

- **Helm and weapons:** the item's `alternategfx` code in `Armor.txt` or `Weapons.txt`. Vampire Gaze, a
  Grim Helm, draws `BHM` on `HD`; a mace draws `MAC` on the hand holding it.
- **Body armor** is split over six layers. `Armor.txt` has one column for each: `rArm`, `lArm`, `Torso`,
  `Legs`, `rSPad` and `lSPad`, which go to the `RA`, `LA`, `TR`, `LG`, `S1` and `S2` layers. Each value
  indexes `ArmType.txt`: 0 `LIT`, 1 `MED`, 2 `HVY`. Gothic Plate has `2 2 1 2 2 2`, so it draws `HVY`
  arms, legs and pads with a `MED` torso.

**Monsters.** Since 1.10, a monster's `MonStatsEx` column names a row of `MonStats2.txt`. That row's
`HDv` … `S8v` columns list the variants each layer may use; the game picks among them when the monster
spawns. The Carver (a Fallen), for instance, allows `TR` `lit`, `RH` `ssd`/`clb`/`axe`, `SH`
`nil`/`sml`/`buc`/`tch`, and `S1` `lit`/`med`. Before 1.10 these choices were hard-coded.

## Modes

**Players** (`PlrMode.txt`):

| Token | Mode | Token | Mode |
|-------|------|-------|------|
| `DT` | death (dying) | `BL` | block |
| `NU` | neutral, outside town | `SC` | cast |
| `WL` | walk, outside town | `TH` | throw |
| `RN` | run | `KK` | kick |
| `GH` | get hit, also knock-back | `S1`–`S4` | skills |
| `TN` | neutral, in town | `DD` | dead (the corpse) |
| `TW` | walk, in town | | |
| `A1`, `A2` | attacks | | |

Not every class has every mode. The Barbarian has no `S2`, for example, and the Amazon only `S1`. A
"sequence" mode builds an animation out of frames of other modes. Those sequences are hard-coded,
except for monsters from 1.10 on, whose sequences are in `MonSeq.txt`.

**Monsters** have the same scheme with their own list (`MonMode.txt`).

**Objects** (`ObjMode.txt`):

| Index | Token | Mode      |
|-------|-------|-----------|
| 0     | `NU`  | neutral   |
| 1     | `OP`  | operating |
| 2     | `ON`  | opened    |
| 3–7   | `S1`–`S5` | special 1 to 5 |

## Weapon classes

A weapon class describes the pose of the whole body, the arms above all. It isn't about the weapon's own
look. Every mode is drawn once per weapon class the unit supports. The class codes are in
`WeaponClass.txt`, and each weapon's are in the `wclass` and `2handedwclass` columns of `Weapons.txt`.

| Code  | Name                     | Used with                                       |
|-------|--------------------------|-------------------------------------------------|
| `HTH` | hand to hand             | no weapon, with or without a shield             |
| `1HS` | one-hand swing           | shield + axe, wand, club, scepter, mace, hammer, sword, throwing axe, orb |
| `1HT` | one-hand thrust          | shield + throwing potion, knife, throwing knife, javelin |
| `2HS` | two-hand swing           | two-handed sword                                |
| `2HT` | two-hand thrust          | spear                                           |
| `STF` | staff                    | staff, large axe, maul, polearm                 |
| `BOW` | bow                      | bow                                             |
| `XBW` | crossbow                 | crossbow                                        |
| `HT1` | one hand-to-hand         | shield + claw                                   |
| `HT2` | two hand-to-hand         | two claws                                       |
| `1SS` | left swing, right swing  | two one-handed swing weapons                    |
| `1JT` | left jab, right thrust   | two one-handed thrust weapons                   |
| `1ST` | left swing, right thrust | swing weapon on the left, thrust on the right   |
| `1JS` | left jab, right swing    | thrust weapon on the left, swing on the right   |

Swords that can be used one- or two-handed have `1HS` in `wclass` and `2HS` in `2handedwclass`. The
four dual-wield classes (`1SS`, `1JT`, `1ST` and `1JS`) belong to the Barbarian, the only class that
wields two weapons. `HT1` and `HT2` are the Assassin's claws.

How the game picks the class (D2MOO, `COMPOSIT_GetWeaponClassCode`):

- **Players:** the weapon's `wclass`, or `2handedwclass` when it's held in two hands.
  - A Barbarian with two weapons combines their classes:
    - two swings give `1SS`;
    - two thrusts give `1JT`;
    - a mix gives `1JS` or `1ST`, depending on which hand holds which.
  - An Assassin with two claws gets `HT2`.
  - With no weapon, the class's `basewclass` from `CharStats.txt` applies.
- **Monsters:** `BaseW` in `MonStats2.txt`. Death and corpse (`DT`, `DD`) use `HTH`, unless the monster
  has `compositeDeath`.
- **Objects:** always `HTH`.

The COF name has a few exceptions of its own:

- Player sequences (`SQ`) and knock-back (`KB`), and monster knock-back, use the get-hit (`GH`) COF.
- A player's throw (`TH`) keeps the weapon class only for one-handed classes (`1HS`, `1HT` and the four
  dual-wield ones). Otherwise it uses `HTH`.

## Scale

Every combination of unit, mode, weapon class, layer and variant is a separate file. There are 120 DCCs
for the Claymore alone, and 149 usable COFs for the Barbarian. The files for one COF can be many, too:
`batn1ss.cof` can use 62 DCCs.

## Color maps

**Item colors.** An item can recolor the layers it draws.

- The item type's `Transform` column (in `Armor.txt`, `Weapons.txt` or `Misc.txt`) picks a color-map
  file in `data/global/items/palette/`: 1 means `grey.dat` and 2 means `grey2.dat`.
- The item picks a tint within that file:
  - up to 1.09: `transform` (whether to use the color map) and `transformcolor` (which tint) in
    `UniqueItems.txt`, `SetItems.txt`, `Gems.txt`, `MagicPrefix.txt`, `MagicSuffix.txt` or
    `AutoMagic.txt`;
  - from 1.10: `chrtransform` for the character graphic and `invtransform` for the inventory picture,
    both color codes from `Colors.txt`.

  A tint's index is its line in `Colors.txt`, counting from 0. Vampire Gaze uses `grey2.dat` tint 12
  (crystal green); the "Cruel" prefix turns a weapon black (tint 3).
- Runes can't add a tint.

**Monster variants.** The Fallen come in red, blue, green and brown from one set of sprites. The
difference is a color map from `palshift.dat` in the monster's `cof/` folder.

- That file holds 8 color maps, but the game never uses the first two. `MonStats2.txt`'s `TransLvl`
  column counts from the third map, so `TransLvl` 1 is map 4 counting from 1.
- From 1.10, super uniques can also use one of 22 maps in `data/global/monsters/randtransforms.dat`,
  through the `Utrans`, `Utrans(N)` and `Utrans(H)` columns of `SuperUniques.txt` and `MonStats2.txt`:

  | Value      | Color map                                                              |
  |------------|------------------------------------------------------------------------|
  | 2–7        | `palshift.dat` maps 3–8                                                |
  | 8–29       | `randtransforms.dat` maps 1–22                                         |
  | 1 or −1    | none                                                                   |
  | 0 or empty | `palshift.dat` map 5 in `MonStats2.txt`; a random `randtransforms.dat` map in `SuperUniques.txt` |
  | anything else | `palshift.dat` map 3                                                |

  The Countess is 16, so `randtransforms.dat` map 9, which is why she's green.

## Speed

- The game logic runs at **25 frames per second**.
- An animation's speed is a fraction of that in 256ths: 256 plays one frame per game frame, 128 plays
  at half that rate, and 512 at double. So `fps = 25 × speed / 256`.
- The speed comes from [AnimData.d2](animdata.md), keyed by the COF name. The Barbarian's `batn1ss` has
  80, about 7.8 fps.
- The frame to show at game tick `t` is `floor(t × speed / 256)`. Frames aren't shown for equal lengths
  of time unless 256 is a multiple of the speed.
- Objects ignore AnimData.d2. `Objects.txt` has per-mode columns instead: `FrameDelta0` … `FrameDelta7`
  (speed, in the same 256ths), `FrameCnt0` … `FrameCnt7` (frame counts), `CycleAnim0` … `CycleAnim7`
  and `Start0` … `Start7`. These win over the COF: the Tree of Inifuss's COF has 2 frames per direction,
  but `Objects.txt` gives it 1.

Speeds in AnimData.d2 range from 24 (about 2.3 fps) to 512 (50 fps).

## Directions

A COF has 1, 4, 8 or 16 directions and its layers' DCCs the same number. Missiles and overlays, which
are single DCCs, can have 32. Monsters' direction counts per mode are also in `MonStats2.txt` (`dDT` …
`dRN`). The game turns a unit's 64-step facing into a sprite direction as described in
[dcc.md](dcc.md#directions). The DCC files and the COF draw-order table number directions differently.

## Drawing

- **Shadows aren't in the sprites.** The game draws them from the unit's silhouette: filled with a
  shadow color, squashed to half height and skewed 45° to the left. A layer's shadow flag in the COF says
  whether it casts one. The game's shadow code isn't documented anywhere; reimplementations make up
  their own scale and skew.
- **Blending:** a COF layer can be drawn translucent, or with a screen-like or luminance blend (see
  [cof.md](cof.md)). The teleport pad's aura, drawn as-is, shows a black fringe that the blend mode
  would hide. With screen blending, dark pixels contribute little and bright ones a lot.

## Notes for glisomorph

- **Interpolate layers, not composites.** Each layer is a separate DCC with its own frames, bounding
  boxes and color map. Unlike Diablo 1, the draw order between layers changes from frame to frame and
  from direction to direction. In-between frames of a composite would need an in-between draw order,
  which doesn't exist. Synthesize each layer's frames, and let the game compose them.
- **Time:** the frame shown advances by `speed / 256` per game tick, a fraction of a frame at most
  speeds, so the gaps between frames are real. In-betweens slot in without changing the timing model.
- **Shadows** are generated by the game, so interpolated layers get correct shadows automatically.

## Sources

- Paul Siramy, [*Extracting Diablo II Animations*](https://paul-siramy.pages-perso.free.fr/_divers2/Extracting%20Diablo%20II%20Animations.pdf)
  (PDF): all of the above unless noted.
- D2MOO: `D2Common/src/D2Composit.cpp` (weapon-class choice, COF naming), `D2Common/include/D2Composit.h`
  (components and weapon classes), `D2Common/src/DataTbls/MonsterTbls.cpp` (`MonStats2.txt` fields).
