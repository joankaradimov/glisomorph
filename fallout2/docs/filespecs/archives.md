# Fallout 2's archives

The DAT2 format itself is described in [fallout_common's dat.md](../../../fallout_common/docs/filespecs/dat.md#dat2-fallout-2).
This page covers what's specific to Fallout 2: which archives exist, which one wins, and where the
sprites are.

## Archives

| Archive          | Contents                                                                  |
|------------------|---------------------------------------------------------------------------|
| `master.dat`     | most of the game: maps, protos, scripts, text, sound, and all art except the critters' |
| `critter.dat`    | the critters' art (`art\critters\`), including the player's               |
| `patch000.dat`   | the official patch's data (1.02); further `patchNNN.dat` files are allowed |
| `f2_res.dat`     | from the community high-resolution patch (its interface art, per community docs); read by Fallout 2 CE, not by the original game |
| `data\`          | a folder of loose files                                                   |

The shipped archives split exactly as the table says (and as the falloutmods wiki's *Fallout 2 File
Structure* and *Master.dat* pages say): `critter.dat` holds only `art\critters\` (7,120 files in the US
release), and `master.dat` (23,120 files) holds everything else, with no critter art. Unlike Fallout 1,
the split doesn't matter to the game, which searches every archive for every file.

The official 1.02 patch (`f2patch.exe`, a self-extracting zip) ships `patch000.dat` with 489 files:
446 scripts, 15 maps, 17 message files, 4 data files (`data\city.txt`, `karmavar.txt`, `maps.txt`,
`vault13.gam`), 3 protos, two readme files and the help screen (`art\intrface\helpscrn.frm` and its
`.pal`). It replaces no sprites.

The names of the first two and the folder come from `fallout2.cfg`, section `[system]`
(`fallout2-ce: src/game_config.cc`, `gameConfigInit`):

| Key               | Default        |
|-------------------|----------------|
| `master_dat`      | `master.dat`   |
| `master_patches`  | `data`         |
| `critter_dat`     | `critter.dat`  |
| `critter_patches` | `data`         |

As in Fallout 1, the values are paths, and the smaller CD installs left the DATs on the CD.

## Which file wins

Fallout 2 keeps one list of search locations, DATs and folders mixed. Opening a location puts it at the
front of the list, and opening one that's already there moves it to the front (`fallout2-ce:
src/xfile.cc`, `xbaseOpen`). A lookup tries the list front to back and takes the first hit
(`xfileOpen`). The game opens, in this order (`fallout2-ce: src/game.cc`, `gameDbInit`):

1. `master_dat`, then `master_patches`;
2. `critter_dat`, then `critter_patches`. With the defaults that is `data` again, which moves it back to
   the front;
3. `patch000.dat` to `patch999.dat`, each one that exists in the current folder;
4. `f2_res.dat`, if it exists (CE only).

So the search order, highest first, with the defaults:

| Priority | Location                                    |
|---------:|---------------------------------------------|
| 1        | `f2_res.dat` (CE only)                      |
| 2        | `patch999.dat` … `patch000.dat`, the highest number first |
| 3        | `data\`                                     |
| 4        | `critter.dat`                               |
| 5        | `master.dat`                                |
| 6        | the current folder, as a last resort        |

Two consequences worth knowing:

- **`patch000.dat` overrides loose files in `data\`**, because it is opened after the folder.
- **There is no separate critter database.** The original code still calls `db_select`, but it does
  nothing (`fallout2-re: src/plib/db/db.c`). Critter art in `master.dat` or a patch DAT would be found.

The original game does the same, without step 4 (`fallout2-re: src/game/game.c`,
`src/plib/xfile/xfile.c`). In CE, sfall's `ddraw.ini` key `PatchFile` in `[Misc]` replaces the
`patch%03d.dat` name pattern.

**Gzip.** When a file comes from a folder rather than a DAT, the game checks its first two bytes. If they
are `1F 8B` it reads the file through gzip (`xfileOpen`). Files inside DATs are never gzipped; they use
the DAT's own zlib flag.

## Paths

The game builds paths with `\`, relative to the game folder (`art\critters\...`), and DAT lookups ignore
case. On non-Windows systems CE converts `\` to `/` for loose files and matches their names without
regard to case.

## Language folders

With `language` in `[system]` set to anything but `english`:

- **Text** comes from `text\<language>\...`, falling back to `text\english\...` (`fallout2-ce:
  src/message.cc`).
- **Art** is looked up in a language folder first, then in the normal place (`fallout2-ce: src/art.cc`,
  `artCacheGetFileSizeImpl` and `artCacheReadDataImpl`).

The language path for art is built by inserting the language after `art`, but the code keeps the `\`
that followed `art`, so `art\critters\x.frm` becomes `art\<language>\\critters\x.frm`, with a doubled
separator. Windows accepts that for a loose file, but it can't match a path stored in a DAT. The US and
UK releases ship no localized art; for sprites this doesn't matter.

## Where the sprites are

All art is under `art\`, one folder per object type, each with a `.lst` index file named after it
(`art\<type>\<type>.lst`) (`fallout2-ce: src/art.cc`, `gArtListDescriptions`). The folders are the
same as Fallout 1's:

| Folder          | Contents                     |
|-----------------|------------------------------|
| `art\critters\` | critters and the player      |
| `art\items\`    | items on the ground          |
| `art\scenery\`  | scenery objects              |
| `art\walls\`    | walls                        |
| `art\tiles\`    | floor and roof tiles         |
| `art\misc\`     | effects, missiles and so on  |
| `art\intrface\` | the interface                |
| `art\inven\`    | inventory pictures           |
| `art\heads\`    | talking heads                |
| `art\backgrnd\` | backgrounds                  |
| `art\skilldex\` | Skilldex pictures            |

A reader that wants the sprites the game would show should search the locations in the order above.
For unmodified data, that means `patch000.dat`, then `critter.dat`, then `master.dat`.

## Versions

- **Original CD (1.0, then the 1.02 patch).** The CD has no `patch000.dat`; the 1.02 patch installs it
  (see [Archives](#archives)). There were separate US and European 1.02 patches, reportedly, so
  `patch000.dat` may differ between them; only the US one was checked.
- **UK release.** It's the US data without the children. Its `critter.dat` lacks 40 of the child
  critter's (`nachld`) file names (105 files, counting `.fr0`–`.fr5`), keeping only the called-shot
  picture `nachldna.frm`, which other critters borrow through their alias. The other 7,014 critter files
  are identical to the US ones. A community restore, `f2children.zip`, puts the 106 missing files back
  in `art\critters\` as loose files, byte for byte the US ones. The UK `master.dat` differs from the US
  one only slightly (23,122 files against 23,120).
- **GOG and Steam.** These ship a patched game, so `patch000.dat` should be present along with the two
  main DATs.
- **Fallout 2 CE** adds `f2_res.dat` and sfall's `PatchFile` setting. Mods usually add more `patchNNN.dat` files or loose files in `data\`.

## Notes on the wiki

The falloutmods wiki's *Fallout 2 File Structure* page gives a search order from Red's research, and
*Unpacking the Fallout 2 .dat files* gives modding advice built on it. Both differ from the code:

- **Patch DATs.** The wiki says the game tries only even numbers, `patch000.dat` to `patch998.dat`, and
  stops at the first one it finds. The code tries every number from 000 to 999 and opens each one that
  exists (`gameDbInit`; the same loop in `fallout2-re: src/game/game.c`).
- **`data\` and the patches.** The tutorial says loose files in `data\` beat the DATs, and has readers
  unpack `patch000.dat` into `data\` last. That gives the right files, but in the code `patch000.dat`
  itself beats `data\` (see [Which file wins](#which-file-wins)); the wiki's own search order agrees
  with that.
- **Save games.** The wiki puts the loaded save's folder first in the search order. The code never adds
  it to the search list. Saving and loading copy the slot's maps and protos to and from
  `<master_patches>\maps\` and `<master_patches>\proto\` (`fallout2-ce: src/loadsave.cc`), so they
  are found as ordinary `data\` files.
- **Deleted protos.** The wiki warns that the game deletes `proto\items\*.pro` and
  `proto\critters\*.pro` from `data\`, and suggests making them read-only. The code does erase those
  folders' `.pro` files (and `maps\*.sav`) at start-up and whenever a game is reset
  (`_InitLoadSave`, `_ResetLoadSave` in `loadsave.cc`), which fits.

## Checked against the game data

Checked on 2026-10-03 on the US and UK CDs and the US 1.02 patch:

- the split between `critter.dat` and `master.dat`, and the counts above, on every file;
- the contents of the 1.02 `patch000.dat`, every file;
- the UK `critter.dat` against the US one, file by file, and `f2children.zip` against the US files;
- that neither release has localized art;
- the DAT2 details, listed in [dat.md](../../../fallout_common/docs/filespecs/dat.md#checked-against-the-game-data).

The US `critter.dat` has the MD5 the falloutmods wiki's *Fallout critter patches* page gives for the US
release. The wiki's UK entry doesn't match the UK CD checked here: it says the UK `critter.dat` is the
same as the US one, and gives as the UK `master.dat` the hash the US CD's `master.dat` has. It may
describe a later UK re-release.

Not checked: GOG and Steam installs and their `data\` folders, the European 1.02 patch, the German
release, and the search order at run time.

## Sources

- fallout2-ce (commit e97087b): `src/game.cc` (`gameDbInit`), `src/game_config.cc` and
  `src/game_config.h` (keys and defaults), `src/db.cc` (`dbOpen`), `src/xfile.cc` (`xbaseOpen`,
  `xfileOpen`), `src/art.cc` (art folders, language folders), `src/sfall_config.h` (`PatchFile`).
- fallout2-re (commit b135fc4): `src/game/game.c` (the `patch%03d.dat` loop, no `f2_res.dat`),
  `src/plib/db/db.c` (`db_select` does nothing), `src/plib/xfile/xfile.c`.
- The falloutmods wiki, read through the MediaWiki API (`api.php?action=parse&prop=wikitext`), since
  plain page fetches return HTTP 402:
  [Fallout 2 File Structure](https://falloutmods.fandom.com/wiki/Fallout_2_File_Structure),
  [File structure of Fallout 2](https://falloutmods.fandom.com/wiki/File_structure_of_Fallout_2),
  [Master.dat](https://falloutmods.fandom.com/wiki/Master.dat) and
  [Unpacking the Fallout 2 .dat files](https://falloutmods.fandom.com/wiki/Unpacking_the_Fallout_2_.dat_files):
  what the archives hold, `patch000.dat` coming from the official patch, and the search order compared
  above.
