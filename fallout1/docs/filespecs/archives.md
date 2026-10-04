# Fallout 1's archives

The DAT1 format itself is described in [fallout_common's dat.md](../../../fallout_common/docs/filespecs/dat.md#dat1-fallout-1).
This page covers what's specific to Fallout 1: which archives exist, where the game looks for a file,
and where the sprites are.

## Archives

| Archive       | Contents                                                              |
|---------------|-----------------------------------------------------------------------|
| `master.dat`  | everything except the critters: maps, protos, scripts, text, sound, and art for items, scenery, walls, tiles, the interface, heads and so on |
| `critter.dat` | the critters' art (`ART\CRITTERS\`), including the player's            |
| `data\`       | a folder of loose files that override the archives                    |

In the US release `master.dat` holds 18,280 files in 51 directories and `critter.dat` 5,560 files in one,
`ART\CRITTERS`. The European release's `master.dat` has 19,784 files in 65 directories: the extra ones
are French, German, Italian and Spanish text and French and Spanish interface art (see [Paths](#paths)).
Its `critter.dat` has 5,459 files (see [Versions](#versions)).

The names come from `fallout.cfg`, section `[system]` (`fallout1-ce: src/game/gconfig.cc`,
`gconfig_init`):

| Key               | Default        |
|-------------------|----------------|
| `master_dat`      | `master.dat`   |
| `master_patches`  | `data`         |
| `critter_dat`     | `critter.dat`  |
| `critter_patches` | `data`         |

The values are paths, so a DAT can stay on the CD. On the original CD release, the smaller install
options did that: `fallout.cfg` pointed `master_dat` and `critter_dat` at the CD drive, and the CD had to
be in the drive to play. The GOG and Steam releases should have both DATs in the game folder. The
install type only decides where the DATs are, not what is in them.

## Which file wins

Fallout 1 doesn't search everything. It opens two separate databases, each one DAT plus one folder
(`fallout1-ce: src/game/game.cc`, `game_init_databases`):

- the **master** database: `master_dat` with `master_patches`;
- the **critter** database: `critter_dat` with `critter_patches`.

Only one is active at a time, and a lookup searches only that one (`fallout1-ce: src/plib/db/db.cc`,
`db_fopen`, `db_read_to_buf`, `db_dir_entry`). Within it:

1. the folder: the file `<patches>\<path>`, if it exists;
2. the DAT.

The master database is the default. The art code switches to the critter database only for critter
art and for `art\critters\critters.lst` (`fallout1-ce: src/game/art.cc`: `art_init`, `art_exists`,
`art_fid_valid` and the loaders around them). So:

- **a critter sprite is found only in `critter.dat` or the `data\` folder**, never in `master.dat`;
- every other file is found only in `master.dat` or `data\`.

With the defaults both folders are `data\`, so a loose file there overrides either DAT.

**Hashing.** With `hashing=1` in `[system]` (the default), the game lists the patch folder once at
start-up and remembers a 15-bit hash of each file name (`db_fill_hash_table`). A lookup skips the folder
when the name's hash isn't there. It's a speed-up only; it doesn't change which file wins, except for
files added to the folder while the game runs.

## Paths

The game builds paths with `\` and looks them up without regard to case. Inside the DAT the directory
part (`ART\CRITTERS`) and the file name (`HMJMPSAA.FRM`) are stored separately; see
[dat.md](../../../fallout_common/docs/filespecs/dat.md#finding-a-file).

Text is localized by folder: messages are read from `text\<language>\...`, where `<language>` is the
`language` key in `[system]`, `english` by default (`fallout1-ce: src/game/message.cc`).

Art depends on the executable. The US executable, which fallout1-ce and fallout1-re reproduce, has no
language folders for art. The European executable does: its `art_init` reads the same `language` key
(default `english`) and its strings include `art\%s\%s`, like Fallout 2's localized art paths. Its
`master.dat` has `art\french\` and `art\spanish\`, with interface art and splash screens only. Critter
art isn't localized.

## Where the sprites are

All art is under `art\`, one folder per object type, each with a `.lst` index file named after it
(`art\<type>\<type>.lst`) (`fallout1-ce: src/game/art.cc`, the `art` table):

| Folder          | Contents                     | Archive       |
|-----------------|------------------------------|---------------|
| `art\critters\` | critters and the player      | `critter.dat` |
| `art\items\`    | items on the ground          | `master.dat`  |
| `art\scenery\`  | scenery objects              | `master.dat`  |
| `art\walls\`    | walls                        | `master.dat`  |
| `art\tiles\`    | floor and roof tiles         | `master.dat`  |
| `art\misc\`     | effects, missiles and so on  | `master.dat`  |
| `art\intrface\` | the interface                | `master.dat`  |
| `art\inven\`    | inventory pictures           | `master.dat`  |
| `art\heads\`    | talking heads                | `master.dat`  |
| `art\backgrnd\` | backgrounds                  | `master.dat`  |
| `art\skilldex\` | Skilldex pictures            | `master.dat`  |

The archive column follows from the lookup rule above: the game can only find critter art in
`critter.dat`, and other art only in `master.dat`. The shipped archives are split exactly that way:
`critter.dat` has only `ART\CRITTERS`, and `master.dat` has no critter art.

## Versions

- **Original CD and the GOG/Steam releases.** The engine and the DAT format are the same. Fallout 1 has
  no `patchNNN.dat` mechanism; that came with Fallout 2.
- **The official patches** deliver loose files. Patch 1.1 (`fallwin11.zip`, `falldos11.zip`) is a new
  executable plus scripts and text under `DATA\SCRIPTS\` and `DATA\TEXT\ENGLISH\`; nothing
  sprite-related. Patch 1.2 wasn't checked.
- **European release.** It's the US data without the children. `critter.dat` lacks 36 of the child
  critter's (`nachld`) file names: everything but the five animations other critters borrow through
  aliases (`bn`, `na`, `rh`, `rj`, `rk`). The other 5,458 critter files are identical to the US ones,
  gore included. It also adds the European executable's localized art (see [Paths](#paths)).
- **Fallout CE.** Reads the same files with the same rules. On non-Windows systems it converts `\` to `/`
  for loose files and matches their names without regard to case.

## Checked against the game data

Checked on 2026-10-03 on the US and European CDs (the European one is the UK "GSP White Label" release,
by the MD5s on the falloutmods wiki's *Fallout critter patches* page) and on patch 1.1:

- the archive contents, counts and split between `critter.dat` and `master.dat` above, on every file;
- the European executable's localized art, from its strings, and the localized art in its
  `master.dat`;
- the European `critter.dat` against the US one, file by file;
- the 1.1 patch's file list.

Not checked: GOG and Steam installs and their `data\` folders, patch 1.2, the German release, and the
US executable's `language` handling beyond the absence of art paths.

## Sources

- fallout1-ce (commit 0609bcf): `src/game/game.cc` (`game_init_databases`), `src/game/gconfig.cc`
  and `gconfig.h` (keys and defaults), `src/plib/db/db.cc` (search order, hashing),
  `src/game/art.cc` (database switching for critters, the art folders), `src/game/message.cc`
  (language folders).
- fallout1-re (commit ac9784b): the same logic in `src/game/game.c` and `src/plib/db/db.c`.
- Batocera's Fallout CE page: the DATs can be copied from the CD or referenced from `fallout.cfg`.
