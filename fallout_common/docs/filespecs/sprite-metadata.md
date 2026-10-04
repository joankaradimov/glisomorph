# Sprite metadata

An [FRM](frm.md) stores frames, shifts, a frame rate and an action frame. It doesn't say what creature
it shows, what the animation is, which weapon is in hand, or which directions exist. The game derives
all of that from the file's name, and finds the name through a numeric art ID (FID) and a list file per
art type. This page collects those rules. Fallout 1 and 2 share almost all of them; the differences are
in [Fallout 1 and 2](#fallout-1-and-2).

File references are to fallout2-ce unless they say otherwise. Paths are written as the game builds
them, with `\`, under the game's `art\` folder; they live in `master.dat`, `critter.dat` or a patch
file (archives are covered separately).

## Directions

`ROTATION_*` in `src/obj_types.h`. One hex step is the screen offset the walking code moves a critter by
(`_off_tile` and `dword_51D984`, `src/tile.cc`).

| Value | Name | Hex step on screen (px) | Screen angle |
|------:|------|-------------------------|-------------:|
| 0     | NE   | (+16, −12)              | 36.9° up     |
| 1     | E    | (+32, 0)                | 0°           |
| 2     | SE   | (+16, +12)              | 36.9° down   |
| 3     | SW   | (−16, +12)              | 143.1°       |
| 4     | W    | (−32, 0)                | 180°         |
| 5     | NW   | (−16, −12)              | 143.1° up    |

- The values go clockwise on screen, starting up-right. Rotating clockwise is `+1 mod 6`
  (`objectRotateClockwise`, `src/object.cc`).
- There's no north or south: the hex grid has a vertical gap where those would be.
- On the ground the 6 directions are 60° apart. If the hexes are regular on the ground, the steps say
  the screen squashes the ground's depth axis to `12 / (32 · sin 60°) ≈ 0.433` of its width, which
  would put the camera about 25.7° above the ground. That's derived from the grid, not from the art;
  whether the critters were rendered with the same camera has to be measured.
- The FRM's direction blocks are in this order, and the game indexes them by the critter's direction.

## Art types and list files

Each art type has a folder and a list, `art\<dir>\<dir>.lst` (`artInit`, `artReadList`). The FID's
index is a 0-based line number in that list.

| Type | `<dir>`    | What it holds                                |
|-----:|------------|----------------------------------------------|
| 0    | `items`    | items on the ground                          |
| 1    | `critters` | people and creatures                         |
| 2    | `scenery`  | scenery                                      |
| 3    | `walls`    | walls                                        |
| 4    | `tiles`    | floor and roof tiles                         |
| 5    | `misc`     | missiles, effects, hex markers, etc.         |
| 6    | `intrface` | interface                                    |
| 7    | `inven`    | inventory pictures                           |
| 8    | `heads`    | talking heads                                |
| 9    | `backgrnd` | talking-head backgrounds                     |
| 10   | `skilldex` | Skilldex pictures                            |

**Parsing.** One entry per line. The name ends at the first space, comma, semicolon, tab, CR or LF, and
is cut to 12 characters. Anything after it is ignored, except in `critters.lst` and `heads.lst`, whose
extra fields are read separately (below). So `;` starts a comment, as the falloutmods wiki's *LST File
Format* page says. Every line takes an index, including a blank or comment-only one, which becomes an
empty name (`artReadList` counts lines first). The wiki says such lines aren't allowed; to the reader
they're legal but use up an index.

For every type but critters and heads, the list entry is the whole file name, extension included:
`art\<dir>\<entry>`. Critters and heads list a base name, and the game appends codes.

## FID: the art ID

A 32-bit number (`buildFid`, `artBuildFilePath`; `art_id`, `art_get_name` in Fallout 1):

| Bits  | Mask         | Field                                                           |
|-------|--------------|-----------------------------------------------------------------|
| 0–11  | `0x00000FFF` | index in the type's `.lst`                                      |
| 12–15 | `0x0000F000` | weapon code (critters); fidget number (heads)                   |
| 16–23 | `0x00FF0000` | animation (critters); head animation (heads)                    |
| 24–27 | `0x0F000000` | art type                                                        |
| 28–30 | `0x70000000` | file direction: 0 means `.frm`, `n` (1–6) means `.fr<n−1>`      |

**The direction field** is offset by one: callers pass the critter's direction + 1. `buildFid` keeps it
only for critters' knockdown and death animations (codes 20–35, except 33, fire dance). For everything
else it's forced to 0, the combined `.frm`. For those animations it checks the files in this order:

1. `.fr<direction>` (the field as passed);
2. `.fr0`, by setting the field to 1 (fallout2-ce's comment calls this "rotation 1 (E)", but because of
   the +1 it selects the NE file);
3. `.frm`.

Whichever file is opened, the frame inside it is still picked by the critter's real direction (see
[frm.md](frm.md#directions-shared-and-split)).

## Critters

### critters.lst

| Field | Fallout 1 | Fallout 2 | Meaning |
|-------|-----------|-----------|---------|
| 1     | yes       | yes       | base name                                                           |
| 2     | yes       | yes       | alias: the index of another critter in the list (see [Aliases](#aliases)) |
| 3     | —         | yes       | run flag: 1 if the AI may make this critter run                     |

If a line has no comma, the alias defaults to the player's base critter, and in Fallout 2 the run flag
to 1. In Fallout 2 a line with an alias but no second comma gets run flag 0, and an empty alias (`name,,1`) reads
as 0, the list's first line. In Fallout 2 that default is the tribal male (`hmwarr`), found by name before the list's fields are
read. In Fallout 1 it's `art_vault_guy_num`, which is still 0 when the list is read, so the default
alias is the first critter in the list.

The run flag only steers the combat AI (`artCritterFidShouldRun`, `combat_ai.cc`). Whether a critter
*can* run depends on whether its run animation file exists.

**The shipped lists.** Fallout 1's has 59 lines, Fallout 2's 103, with CR LF line ends and no comments.
Every base name is 6 characters. Line 0 is `reserv` with no comma, and `reserv` also fills unused
lines further down, with an alias (1 more in Fallout 1, 6 more in Fallout 2). Fallout 2 lists `macybr`
twice. In Fallout 2, 46 lines have a third field, always `1`; the other 56 with an alias have none, so
their run flag is 0.

### File names

```
art\critters\<base><weapon><anim>.frm      (or .fr0 … .fr5 for knockdowns and deaths)
```

`<weapon>` and `<anim>` are one letter each, computed by `_art_get_code` (`art_get_code` in Fallout 1).
The weapon letter isn't always a weapon: it also marks the death and stand-up groups. Base names are 6
characters in both games' lists, so the full name fits DOS's 8.3.

**Weapon codes** (FID bits 12–15; from the weapon's proto, `weaponGetAnimationCode`, `src/item.cc`).
The names are the code's (`WEAPON_ANIMATION_*`, `src/art.h`); the falloutmods wiki names the groups by
what uses them, which is more telling:

| Code | Letter | Weapon (code) | Weapon (wiki)                       |
|-----:|--------|---------------|-------------------------------------|
| 0    | `a`    | none          | unarmed                             |
| 1    | `d`    | knife         | knife                               |
| 2    | `e`    | club          | melee                               |
| 3    | `f`    | hammer        | hammer                              |
| 4    | `g`    | spear         | spear                               |
| 5    | `h`    | pistol        | pistol                              |
| 6    | `i`    | SMG           | SMG                                 |
| 7    | `j`    | shotgun       | rifle                               |
| 8    | `k`    | laser rifle   | heavy weapon (and the flamer, `kl`) |
| 9    | `l`    | minigun       | minigun, gatling laser              |
| 10   | `m`    | launcher      | rocket launcher                     |

### Animation codes

The enum is in `src/animation.h` (`src/game/anim.h` in Fallout 1). `w` below stands for the weapon
letter (`d`–`m`).

**Basic animations** — letter `a` + animation code. Only stand and walk take the weapon letter; every
other one is drawn with the unarmed letter `a`, whatever the critter holds.

| Code | Animation          | File code        | Notes                                      |
|-----:|--------------------|------------------|--------------------------------------------|
| 0    | stand              | `aa`, armed `wa` | the base pose; frame 0 is the rest pose, the rest an idle fidget |
| 1    | walk               | `ab`, armed `wb` |                                            |
| 2    | jump begin         | `ac`             |                                            |
| 3    | jump end           | `ad`             |                                            |
| 4    | climb ladder       | `ae`             |                                            |
| 5    | falling            | `af`             |                                            |
| 6    | up stairs right    | `ag`             |                                            |
| 7    | up stairs left     | `ah`             |                                            |
| 8    | down stairs right  | `ai`             |                                            |
| 9    | down stairs left   | `aj`             |                                            |
| 10   | magic hands, ground | `ak`            | picking up from the ground                 |
| 11   | magic hands, middle | `al`            | using something at waist height            |
| 12   | magic hands, up    | `am`             |                                            |
| 13   | dodge              | `an`, armed `we` | armed dodge is the parry file              |
| 14   | hit from front     | `ao`             |                                            |
| 15   | hit from back      | `ap`             | falls back to hit from front if missing    |
| 16   | punch              | `aq`             |                                            |
| 17   | kick               | `ar`             |                                            |
| 18   | throw              | `as`; knife `dm`, spear `gm` |                                |
| 19   | run                | `at`             | the game walks instead if missing          |

**Knockdowns and deaths** — letter `b`, played once, may be split into `.fr0`–`.fr5`:

| Code | Animation             | File code | Code | Animation             | File code |
|-----:|-----------------------|-----------|-----:|-----------------------|-----------|
| 20   | fall back             | `ba`      | 28   | sliced in half        | `bi`      |
| 21   | fall front            | `bb`      | 29   | burned to nothing     | `bj` (alias) |
| 22   | bad landing           | `bc`      | 30   | electrified to nothing | `bk` (alias) |
| 23   | big hole              | `bd`      | 31   | exploded to nothing   | `bl`      |
| 24   | charred body          | `be`      | 32   | melted to nothing     | `bm`      |
| 25   | chunks of flesh       | `bf`      | 33   | fire dance            | `bn` (alias; always `.frm`) |
| 26   | dancing autofire      | `bg`      | 34   | fall back, bloody     | `bo`      |
| 27   | electrify             | `bh` (alias) | 35 | fall front, bloody    | `bp`      |

Fall front falls back to fall back if its file is missing, and the bloody versions are used only if
they exist (`actionKnockdown`, `_action_blood`, `src/actions.cc`).

**Getting up** — letter `c`:

| Code | Animation             | File code |
|-----:|-----------------------|-----------|
| 36   | prone to standing     | `ch`      |
| 37   | back to standing      | `cj`      |

**Weapon animations** — the weapon letter + `c` onwards. These exist only with a weapon; asking for one
unarmed fails.

| Code | Animation        | File code |
|-----:|------------------|-----------|
| 38   | take out         | `wc`      |
| 39   | put away         | `wd`      |
| 40   | parry            | `we`      |
| 41   | thrust           | `wf`      |
| 42   | swing            | `wg`      |
| 43   | point (aim)      | `wh`      |
| 44   | unpoint          | `wi`      |
| 45   | fire single      | `wj`      |
| 46   | fire burst       | `wk`      |
| 47   | fire continuous  | `wl`      |

**Single-frame deaths** — letter `r`, codes 48–63 in the same order as 20–35: `ra` (fall back) to `rp`
(fall front, bloody). They're the corpse poses, used when a critter is put down dead without playing
the death (`critterKill`, `src/critter.cc`; the scripting opcodes in `src/interpreter_extra.cc`).
`buildFid` never gives them a direction file, so they're always `.frm`. (`_show_death`, which looks
meant to swap a finished death for its single-frame version, tests `anim < 48 && anim > 63`, which is
never true, so in practice the last frame of the played death stays on screen.)

**Called-shot picture** — code 64, `na`, the critter portrait in the called-shot window. Always taken
from the alias critter.

**Which files exist.** The code accepts every combination above; the data has far fewer. The
falloutmods wiki lists, per weapon letter, the files that exist (stand, walk, take out, put away and
dodge for every weapon; thrust and swing for the melee groups; aim, unaim and the shots for guns).
Checked against the files of both games:

- **Every base name has files and an `aa`**, except the child (`nachld`) in the European releases,
  which keep only the files other critters borrow through aliases (see the games' `archives.md`).
  Stands have 1 to 25 frames, most often 12.
- **Never in the data:** jump begin and end (`ac`, `ad`), falling (`af`), magic hands up (`am`) and the
  single-frame fire dance (`rn`), as the wiki says.
- **Stairs:** the wiki says only `ag` exists, used only by Goris (`marobe`) for his robe. That's
  Fallout 2: `ag` under `marobe` and `madeth`, no `ah`–`aj`. Fallout 1 has `ag`–`aj` for all 14 of its
  player and armor bases (`hapowr`, `hmjmps`, `hfmetl`, …), one block each; Fallout 2 dropped them.
- **`au`:** `hmlthrau.frm` and `hmmetlau.frm` exist in both games. No animation code produces `au`, so
  the game can't open them through an FID.
- **Aliased codes under a non-alias critter**, which the game never opens: `nmlosrbj` in both games,
  and `macybrna` and `mafirena` in Fallout 2.
- **`rc` and `ra`, `rh` and `re`:** the wiki says they look the same. As files they differ, except
  `rh` and `re` under 2 bases in Fallout 1 and 3 in Fallout 2, which are identical.

### Aliases

Electrify, burned to nothing, electrified to nothing (codes 27, 29, 30), their single-frame versions
(55, 57, 58), fire dance (33) and the called-shot picture (64) are never looked up under the critter's
own name. `artAliasFid` replaces the index with the alias from `critters.lst`, keeping the weapon code and
direction. That's how dozens of human critters share one set of burning and electrocution deaths. The
called-shot hit-location text is chosen by the alias index too: message `1000 + 10 × alias + location`
in `combat.msg`, with locations 0–8 being head, left arm, right arm, torso, right leg, left leg, eyes,
groin, uncalled (`hitLocationGetName`, `combat.cc`; the wiki gives the same formula).

The alias is followed once: an aliased lookup doesn't look at the alias critter's own alias. The wiki
describes the same for the called-shot picture.

### The player and armor

- Armor protos carry a male and a female critter index; putting armor on swaps the critter's base name
  (`armorGetMaleFid`, `armorGetFemaleFid`, `src/item.cc`). Each armor look is therefore a different
  creature in the list, with its own full set of files.
- Unarmored, the player is `hmjmps` / `hfjmps` (vault jumpsuit). Fallout 2 adds `hmwarr` / `hfprim`
  (tribal) for the start of the game.

### Base names

A base name is two letters of group and four of description. The falloutmods wiki's *Critter FRM
nomenclature* page gives the groups:

| Prefix | Group                     |
|--------|---------------------------|
| `ha`   | hero (player), either sex |
| `hf`   | hero, female              |
| `hm`   | hero, male                |
| `na`   | NPC, either sex           |
| `nf`   | NPC, female               |
| `nm`   | NPC, male                 |
| `ma`   | monster                   |

The same page lists the base names in Fallout 2's `critter.dat`, with what each shows (the wiki's
labels, shortened). Against the files, the list is complete except for `magko2`, a second gecko file
set; the labels weren't checked:

| Prefix | Base names |
|--------|------------|
| `ha`   | `hanpwr` advanced power armor, `hapowr` power armor, `harobe` purple robe |
| `hf`   | `hfcmbt` combat armor, `hfjmps` vault jumpsuit, `hflthr` leather armor, `hfmaxx` leather jacket, `hfmetl` metal armor, `hfprim` tribal |
| `hm`   | `hmbjmp` vault jumpsuit (black man), `hmbmet` metal armor (black man), `hmcmbt` combat armor, `hmjmps` vault jumpsuit, `hmlthr` leather armor, `hmmaxx` leather jacket, `hmmetl` metal armor, `hmwarr` tribal |
| `ma`   | `maantt` ant, `mabos2` Frank Horrigan's torso, `maboss` Frank Horrigan, `mabran` king rat, `mabrom` brahmin, `maclaw` deathclaw, `maclw2` baby deathclaw, `macybr` robot dog, `maddog` dog, `madegg` egg, `madeth` grey deathclaw, `mafeye` floating eye bot, `mafire` fire gecko, `magcko` golden gecko, `magun2` plasma turret, `magunn` minigun turret, `mahand` Mr. Handy, `malien` wanamingo, `mamant` mantis, `mamrat` mole rat, `mamtn2` super mutant in leather, `mamtnt` super mutant, `mamurt` pig rat, `maplnt` mutant plant, `maquen` wanamingo queen, `marobe` Goris, `marobo` brain bot, `marobt` assault bot, `mascp2` baby radscorpion, `mascrp` radscorpion, `masphn` floater, `masrat` rat, `mathng` centaur |
| `na`   | `nablue` blue robe, `nabrwn` brown robe, `nachld` child, `naghul` ghoul, `naglow` glowing ghoul, `napowr` power armor without helmet, `narobe` rags, `navgul` vault ghoul, `nawhit` black robe |
| `nf`   | `nfasia` Asian woman, `nfbrlp` blonde peasant, `nflynn` Lynette, `nfmaxx` punk in leather, `nfmetl` redhead in metal armor, `nfnice` blonde in a dress, `nfpeas` redhead peasant, `nfprim` tribal with ponytail, `nftrmp` tramp, `nfvalt` vault suit, `nfvred` vault suit, redhead |
| `nm`   | `nmasia` Asian peasant, `nmbonc` bouncer in blue, `nmboxx` boxer, `nmbpea` black peasant, `nmbrlp` peasant, `nmbrsr` bouncer in black, `nmbsnp` balding peasant, `nmcopp` police officer, `nmdocc` doctor, `nmfatt` Vic, `nmgang` Asian guard in blue, `nmgrch` dwarf, `nmlabb` lab coat, `nmlosr` junkie, `nmlthr` bald man in leather armor, `nmmaxx` long hair in leather jacket, `nmmexi` Mordino guard, `nmmyrn` Myron, `nmnice` tuxedo, `nmoldd` old man, `nmpeas` peasant with hat, `nmrgng` Asian guard in red, `nmvalt` vault suit, `nmwarr` tribal |
| —      | `reserv`, line 0 of the list: a man on fire |

### Heads

Talking heads use the animation field as a head animation and build `<base><c1><c2>.frm`, with the
fidget number appended for fidgets (`artBuildFilePath`; `_head1 = "gggnnnbbbgnb"`,
`_head2 = "vfngfbnfvppp"`):

| Code | Animation                   | File          |
|-----:|-----------------------------|---------------|
| 0    | very good reaction          | `gv`          |
| 1    | fidget, good                | `gf<n>`       |
| 2    | good to neutral             | `gn`          |
| 3    | neutral to good             | `ng`          |
| 4    | fidget, neutral             | `nf<n>`       |
| 5    | neutral to bad              | `nb`          |
| 6    | bad to neutral              | `bn`          |
| 7    | fidget, bad                 | `bf<n>`       |
| 8    | very bad reaction           | `bv`          |
| 9–11 | phonemes, good/neutral/bad  | `gp`, `np`, `bp` |

`heads.lst` lines are `<base>,<good fidgets>,<neutral fidgets>,<bad fidgets>`.

The wiki's example is Lynette (`lynet`): fidget 1 is a blink, 2 a nod, 3 a head shake, in each mood
(`lynetbf1` to `lynetnf3`). Which fidget does what is up to the art; the code only counts them.

## Timing

- Frame rate comes from the FRM: `1000 / fps` ms per frame, with 0 meaning 10 fps. In combat, walks get
  the *combat speed* preference added to fps ([frm.md](frm.md#timing)).
- An animation plays once and the critter stays on its last frame until something else is played.
  Walks and runs loop for as long as the critter moves.
- **The stand is also the idle fidget.** Every few seconds (`20 / n` seconds for `n` standing critters
  on screen, clamped to 1–7, plus up to 3 s at random) the game plays one visible standing critter's
  `aa` file once (`src/animation.cc`, the idle code that calls `animationRegisterAnimate(object,
  ANIM_STAND, 0)`). Between fidgets a critter shows frame 0 when it was placed, or the fidget's last
  frame after one; presumably they're the same pose. The fidget's offsets don't always sum to zero
  (in 215 of Fallout 2's 576 stand directions they don't), so the last frame can sit a little off the
  first (see [frm.md](frm.md#how-offsets-accumulate)).
- The action frame says when the effect happens (`artGetActionFrame`, `src/actions.cc`).

## Movement

Walks and runs carry the critter by their frames' offsets: each frame moves it by its `(x, y)` offset,
and every time the running total reaches one hex step in the walking direction, the critter moves to
the next hex and the step is subtracted ([frm.md](frm.md#how-offsets-accumulate)). Other animations (knockdowns especially) also move the
critter by their offsets, but it stays on its hex until the game places it again. How far the shipped
walk cycles go is in [geometry.md](geometry.md#checked-against-the-game-data).

## Fallout 1 and 2

| | Fallout 1 | Fallout 2 |
|-|-----------|-----------|
| FRM format, FID layout, animation and weapon codes | same | same |
| `critters.lst` fields | base, alias | base, alias, run flag |
| default alias (no comma) | list entry 0 | `hmwarr` |
| critter files | read from `critter.dat` (the game switches databases explicitly) | read through the normal file search |
| localized art | only the European executable reads `art\<language>\…`; it ships interface art only | `art\<language>\…` is tried first when the language isn't English |
| player looks | `hmjmps`, `hfjmps` | adds `hmwarr`, `hfprim` |

Fallout 2 didn't add animation codes: both games have the same 65. Which critters have which
animations is in the data, not the code; the list has to be built by scanning the files. Comparing the
two games' `critter.dat`:

- Fallout 2 drops 5 of Fallout 1's 58 base names (`malieu`, `mamstr`, `nmgzmo`, `nmover`, `nmovr2`) and
  adds 43.
- Of the 5,389 files with the same name in both, 5,373 are identical. The 16 that differ are the laser
  rifle's burst (`kk`) for 15 bases, and `hfjmpskj`.
- Fallout 2 also drops Fallout 1's stairs files (`ag`–`aj`, 56 files).

## What matters for 3D fitting

- **One base name is one body.** All of a base name's files, armed or not, show the same model. Weapon
  variants (`<base>d*` … `<base>m*`) add a weapon in the hands and change the pose; they don't change
  the body. Fit one model per base name, the way the Diablo work fits one model per variant.
- **Different armor is a different base name**, and so a different body, even for the same person.
- **The base pose is frame 0 of `aa`, the unarmed stand**: the rest pose in 6 directions. The other
  frames of `aa` are an idle fidget, small motion around that pose.
- **Aliased deaths aren't the critter's own art.** Leave codes 27, 29, 30, 33, 55, 57, 58 and 64 out
  of a creature's fit; they show the alias critter.
- **Walk cycles carry exact root motion.** The sum of a cycle's frame offsets is its travel in screen
  pixels, and the hex geometry turns that into ground-plane motion, known rather than guessed. Single
  frame offsets are noisier: they also absorb each frame's crop ([frm.md](frm.md#how-offsets-accumulate)).
- **Shadows are baked into the frames** ([frm.md](frm.md#pixels)); separate them from the body before
  fitting.

## Notes on the wiki

The falloutmods wiki's *Critter FRM nomenclature* page (answers collected from NMA's modding guide)
agrees with the code on the two-letter animation suffixes, the weapon letters, the numbers scripts use
for animations 0–38, `dm` and `gm` for throwing, and `na` for the called-shot picture. The
differences:

- **`ag` and `ah`.** It labels `ag` as `ANIM_up_stairs_left`, the same as `ah`. In the code `ag` (6) is
  up stairs right and `ah` (7) up stairs left.
- **The alias field.** It describes `critters.lst`'s second field only as the line whose called-shot
  picture to use. The code also uses it for the electrify, burn and fire-dance deaths and for the
  hit-location text (see [Aliases](#aliases)).
- **The run flag.** It reads the third field as "has run animations". The code uses it only to let the
  AI choose to run; whether the critter can run depends on the `at` file.
- **Missing alias.** It suggests leaving the second field blank to use the critter's own called-shot
  picture. With no comma the code uses the player's base critter, and with an empty field line 0;
  neither is the critter itself.
- **Name lengths.** It calls file names "usually 8 characters". The code doesn't check the length: it
  keeps up to 12 characters of the list entry and appends two letters.

## Checked against the game data

The rules on this page come from the code. What the data holds was checked on 2026-10-03 against
every critter file of four CD releases: Fallout 1 US and European, Fallout 2 US and UK.

- `critters.lst` in both games: fields, missing commas, run flags and name lengths (see
  [critters.lst](#critterslst));
- which files exist under each base name, against the set of names the code can build (see
  [Which files exist](#animation-codes), above the aliases);
- the split `.fr0`–`.fr5` files (see [frm.md](frm.md#directions-shared-and-split));
- Fallout 1 against Fallout 2 and the US releases against the European ones, file by file (see
  [Fallout 1 and 2](#fallout-1-and-2) and the games' `archives.md`);
- the wiki's base-name table, against the names in the data.

Not checked: the wiki's labels for the base names, and whether a fidget's last frame matches the
stand's frame 0. The walk cycles and the camera angle are in [geometry.md](geometry.md).

## Sources

- fallout2-ce (commit `e97087b`): `src/art.cc` (`artInit`, `artReadList`, `_art_get_code`,
  `artBuildFilePath`, `artAliasFid`, `artCritterFidShouldRun`, `buildFid`), `src/art.h`,
  `src/animation.h`, `src/animation.cc`, `src/obj_types.h`, `src/tile.cc`, `src/actions.cc`,
  `src/critter.cc`, `src/combat.cc`, `src/combat_ai.cc`, `src/item.cc`, `src/inventory.cc`.
- fallout1-ce (commit `0609bcf`): `src/game/art.cc` (`art_init`, `art_get_code`, `art_get_name`,
  `art_alias_fid`, `art_id`), `src/game/art.h`, `src/game/anim.h`, `src/game/anim.cc`,
  `src/game/proto.cc`.
- fallout1-re (`ac9784b`) and fallout2-re (`b135fc4`): `art_id` and the naming code, which the CE ports
  reproduce.
- The falloutmods wiki, read through the MediaWiki API (`api.php?action=parse&prop=wikitext`), since
  plain page fetches return HTTP 402:
  [Critter FRM nomenclature (naming system)](https://falloutmods.fandom.com/wiki/Critter_FRM_nomenclature_(naming_system))
  (base names, prefixes, per-weapon file lists, head fidgets, the `combat.msg` formula) and
  [LST File Format](https://falloutmods.fandom.com/wiki/LST_File_Format) (comments, line endings).
