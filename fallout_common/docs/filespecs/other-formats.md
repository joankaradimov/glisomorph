# Other formats

Every file format in Fallout and Fallout 2 (PC) that doesn't have its own spec here, with what it is and
where the best description lives. Most don't matter for sprites and are marked **out of scope**. FRM, PAL
and DAT have their own specs and aren't listed; nor are PRO and MAP ([pro.md](pro.md), [map.md](map.md)).

"Wiki" links go to the [falloutmods wiki](https://falloutmods.fandom.com/wiki/Fallout_and_Fallout_2_file_formats).
Its pages are mostly translations of TeamX's Russian documents from around 2000. Where the engine code is
the better reference, the table names the `fallout2-ce` file instead.

## Formats

| Format | What it is | Games | Best spec | For glisomorph |
|--------|------------|-------|-----------|----------------|
| LST | plain-text lists, one entry per line (CRLF), index = line number. `art/<type>/<type>.lst` turn FID indices into FRM names; `proto/<type>/<type>.lst` turn PIDs into PRO names; `scripts/scripts.lst` names scripts. `art/critters/critters.lst` lines carry extra comma-separated fields | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/LST_File_Format); `fallout2-ce: src/art.cc` (`artReadList`) | **needed**: the art lists are how FIDs become file names (see the FRM spec) |
| MSG | indexed text, `{number}{sound}{text}` per entry. `text/<language>/game/pro_*.msg` hold object names, `dialog/*.msg` the dialogue | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/MSG_File_Format); `fallout2-ce: src/message.cc` | useful only for naming objects and critters |
| GAM | indexed text of global variables: `data/vault13.gam` (game globals) and `maps/*.gam` (map globals, section `MAP_GLOBAL_VARS:`) | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/GAM_File_Format); `fallout2-ce: src/game.cc` (`globalVarsRead`) | out of scope |
| TXT (data) | INI-style tables in `data/`. Fallout 2: `maps.txt`, `city.txt`, `worldmap.txt`, `party.txt`, `quests.txt`, `holodisk.txt`, `endgame.txt`, `enddeath.txt`, `karmavar.txt`, `genrep.txt`, `ai.txt`, `badwords.txt`. Fallout 1 has only `ai.txt` and `badwords.txt`; its world map, cities and map list are compiled into the executable | F2 mostly, F1 | the engine: `fallout2-ce: src/worldmap.cc`, `src/map.cc`, `src/party_member.cc`, `src/combat_ai.cc` | out of scope. `maps.txt` names maps if map context is ever wanted |
| TXT (text) | `credits.txt`, `quotes.txt`: plain text for the credits and the death screen | F1, F2 | none needed | out of scope |
| CFG | INI-style settings: `fallout.cfg` / `fallout2.cfg` (game), `mapper2.cfg` (Fallout 2 mapper). Also `art/cuts/*.cfg`, palette fade effects for movies (`movie_effect.cc`) | F1, F2 | `fallout2-ce: src/config.cc`, `src/game_config.cc`, `src/movie_effect.cc` | out of scope |
| INI | not in the original games. `f1_res.ini` / `f2_res.ini` (high-resolution patch) and `ddraw.ini` (sfall) are read by the CE ports; sfall and CE also add `elevators.ini` and others | mods | sfall documentation; `fallout2-ce: src/sfall_config.cc` | out of scope |
| INT | compiled scripts: bytecode for the engine's stack interpreter, with procedure, name and string tables | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/INT_File_Format); `fallout2-ce: src/interpreter.cc` | out of scope |
| SSL | script source (Star-Trek Scripting Language). Not shipped with the games; Fallout 2's came with the mapper release, and sfall's `sslc` compiles it | F1, F2 | sfall's `sslc` | out of scope |
| ACM | Interplay's compressed audio: music, sound effects, speech | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/ACM_File_Format); `fallout2-ce: src/sound_decoder.cc` | out of scope |
| LIP | lip-sync timing for talking-head speech: phoneme and marker timings paired with an ACM | F1, F2 (the wiki documents F2's version 2) | [wiki](https://falloutmods.fandom.com/wiki/LIP_File_Format); `fallout2-ce: src/lips.cc` | out of scope. It picks which talking-head frames are shown, but the heads are front-facing, not directional |
| MVE | Interplay MVE movies (intro, endings, cut scenes); 8- and 16-bit video, little-endian chunks | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/MVE_File_Format); `fallout2-ce: src/movie_lib.cc` | out of scope |
| SVE | movie subtitles, indexed text in `text/<language>/cuts/`: `frame:text` per line | F1, F2 (Fallout 1 ships 4, Fallout 2 ships 11) | [wiki](https://falloutmods.fandom.com/wiki/SVE_File_Format) | out of scope |
| RIX | ColoRIX 640×480 256-color images, the loading-screen splashes in `art/splash/` | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/RIX_File_Format); `fallout2-ce: src/game.cc` (`showSplash`) | out of scope |
| PCX | ZSoft PCX images, loadable by script-driven windows (`datafile.cc`) | F2 (engine support) | standard PCX | out of scope |
| AAF | bitmap fonts with 256 glyphs, one alpha byte per pixel (`font*.aaf`) | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/AAF_File_Format); `fallout2-ce: src/font_manager.cc` | out of scope |
| FON | 1-bit bitmap fonts (`font*.fon`), used on the world map and in the mapper | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/FON_File_Format); `fallout2-ce: src/text_font.cc` | out of scope |
| GCD | premade characters' stats, traits and tagged skills (`premade/*.gcd`) | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/GCD_File_Format); `fallout2-ce: src/character_editor.cc` | out of scope |
| BIO | premade characters' biographies, plain text (`premade/*.bio`) | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/BIO_File_Format) | out of scope |
| MSK | world-map walkability masks, 1 bit per pixel, one per world-map tile (`data/wrldmp*.msk`) | F2 (Fallout 1's mask is compiled in: `worldmap_walkmask.cc`) | [wiki](https://falloutmods.fandom.com/wiki/MSK_File_Format); `fallout2-ce: src/worldmap.cc` | out of scope |
| SAVE.DAT | one saved game's state: player, party, globals, world map, in a fixed sequence of sections | F1, F2 (the sections differ) | [wiki](https://falloutmods.fandom.com/wiki/SAVE.DAT_File_Format); `fallout2-ce: src/loadsave.cc` | out of scope |
| SAV | a saved map's state: a gzipped [MAP](map.md) with flag 0x1 set, in `savegame/slotNN/` | F1, F2 | [wiki](https://falloutmods.fandom.com/wiki/SAV_File_Format); [map.md](map.md) | out of scope |
| saved PROs | changed prototypes, gzipped [PRO](pro.md) files in `savegame/slotNN/proto/` | F1, F2 | [pro.md](pro.md) | out of scope |
| WORLDMAP.DAT | world-map state in a saved game (Fallout 2) | F2 | [wiki](https://falloutmods.fandom.com/wiki/Worldmap.dat_File_Format) (the page itself calls its description uncertain); `fallout2-ce: src/worldmap.cc` | out of scope |
| AUTOMAP.DB, AUTOMAP.SAV | the automap: which walls and scenery the player has seen, per map and elevation. No release ships the `.db`: the game creates `maps/automap.db` in its patches folder at start-up and deletes it on exit (`automapCreate`, `automapExit`); saves keep a copy as the `.sav` | F1, F2 | `fallout2-ce: src/automap.cc` (no wiki page) | out of scope |

## Checked against the game data

This page is a survey; each row only says where to look, and the formats themselves haven't been
checked. A few locations were checked against Fallout 1 US and European and Fallout 2 US and UK:

- every `.lst` file in the four releases uses CRLF line ends;
- `data/vault13.gam` and the `maps/*.gam` files are where the table says, and the `.gam` files' map
  globals follow a `MAP_GLOBAL_VARS:` line;
- Fallout 1's `data/` has only `ai.txt` and `badwords.txt` as text tables; Fallout 2's has the twelve
  listed plus `aibdymsg.txt`, `aigenmsg.txt` and `game.txt`;
- the SVE files are in `text/english/cuts/` in both games;
- no release's `master.dat` contains `automap.db`.

## Sources

- [falloutmods wiki, Fallout and Fallout 2 file formats](https://falloutmods.fandom.com/wiki/Fallout_and_Fallout_2_file_formats)
  and the format pages it links to, read 2026-10-03 (the site blocks plain page fetches; the MediaWiki
  API `api.php?action=parse&prop=wikitext` works).
- `fallout2-ce` (commit e97087b) and `fallout1-ce` (commit 0609bcf): the file names the engines open,
  collected from their sources.
