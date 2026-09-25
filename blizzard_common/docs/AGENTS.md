# Blizzard common

Things shared by the Blizzard games in this repository: rules that apply to all of them, the MPQ archive
format, and references that aren't specific to one game. Read this before a game's own `AGENTS.md`:

- [Diablo 1](../../diablo1/docs/AGENTS.md)
- [Diablo 2](../../diablo2/docs/AGENTS.md)

## This folder

It's laid out like a game folder:

| Path                   | Contents                                                        |
|------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`       | this file                                                       |
| `docs/filespecs/*.md`  | specs of formats shared by several games                        |
| `*.py`                 | shared parsers, such as an MPQ reader (none yet)                |

## Rules for every game

- **Never commit game data**, or anything extracted or rendered from it (sprites, PNGs, palettes, test
  fixtures cut from real files). It's Blizzard's copyrighted material. Tests should build synthetic
  inputs, or read the user's own game files at runtime and skip when they're absent.
- **Local game data:** ask the user where it is rather than searching the disk. Each game's
  `AGENTS.md` records what's known.
- **Mind the licenses.** This repository is MIT licensed.
  - Anything ported needs a permissive license, with attribution. These qualify: StormLib, mpqfs and
    dclimplode (MIT); `blast.c` (zlib license); and public-domain or Unlicense code.
  - Copyleft code can't be ported: libmpq is LGPL-2.1+ and pwexplode is GPL-3.
  - Nor can source-available code with restrictions. Each game's `AGENTS.md` lists the projects this
    applies to; read their code to understand a format, then write an independent implementation.
- **Check claims against the data.** Every spec ends with a "Checked against the game data" section
  that says what was verified and on which files. Keep it honest: "sampled" isn't "all". Say so plainly
  when nothing was checked.
- **Paths inside MPQs** are case-insensitive and use backslashes (`data\global\palette\act1\pal.dat`).
  The docs write them with forward slashes, and the MPQ name hash treats both the same.

## Formats

| Format | Spec | What it is | Status |
|--------|------|------------|--------|
| MPQ | [mpq.md](filespecs/mpq.md) | Blizzard's archive format, including PKWARE DCL | specified; checked on Diablo 1 and Diablo II |

## References

Links were checked on 2026-09-25. **Active** means changed in 2025–26, and **dormant** means online but
older.

### MPQ documentation

- Ladislav Zezula's [format](http://www.zezula.net/en/mpq/mpqformat.html) and
  [fundamentals](http://www.zezula.net/en/mpq/techinfo.html) pages are the canonical reference. They're
  HTTP only, because the site's HTTPS certificate is for another host.
- [libmpq's MPQ.md](https://github.com/mbroemme/libmpq/blob/master/MPQ.md): a practical guide for
  implementers.
- [mpqfs](https://github.com/diasurgical/mpqfs): a small MIT-licensed C reader and writer for format
  version 0, with PKWARE DCL built in. Active.
- PKWARE DCL: Mark Adler's [`blast.c`](https://github.com/madler/zlib/blob/master/contrib/blast/blast.c)
  (zlib license) and StormLib's [`pklib`](https://github.com/ladislav-zezula/StormLib/tree/master/src/pklib)
  (MIT).

### MPQ tools

All of these are built on [StormLib](https://github.com/ladislav-zezula/StormLib), the reference
implementation (MIT, active):

- [MPQ Editor](http://www.zezula.net/en/mpq/download.html): a Windows GUI;
- [smpq](https://launchpad.net/smpq): a command-line tool, packaged by Debian and Ubuntu;
- [mpqcli](https://github.com/thegraydot/mpqcli): a command-line tool that takes external listfiles.

### Python

- **mpyq can't read Diablo's archives.** It rejects encrypted files and never decompresses implode.
- [libmpq](https://pypi.org/project/libmpq/) has had wheels since 2026-09, and claims implode and
  encryption support. It's LGPL-2.1+, so use it as a dependency only; untested here.
- [dclimplode](https://pypi.org/project/dclimplode/) (MIT; wheels only up to CPython 3.11) and
  [pwexplode](https://github.com/Schallaven/pwexplode) (pure Python, GPL-3) do PKWARE explode on its
  own.
- [`mpq`](https://pypi.org/project/mpq/) (python-mpq, MIT) binds StormLib and can read Diablo II's
  archives. It needs a system StormLib and a compiler, and has been dormant since 2016.
- Writing our own reader is small. The hashing, decryption and sector code in
  [mpq.md](filespecs/mpq.md), plus a port of `blast.c`, came to about 150 lines of Python. It read the
  Diablo 1 archives completely, and Diablo II's graphics and data.

### Listfiles

Zezula's [`listfiles.zip`](http://www.zezula.net/download/listfiles.zip) has lists for many Blizzard
games. Each game's `AGENTS.md` names better or more specific ones.
