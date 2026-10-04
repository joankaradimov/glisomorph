# PAL: palettes and color tables

Every Fallout 1 and Fallout 2 graphic is 8-bit and palette-indexed. A PAL file holds the palette, a
table that turns any 15-bit RGB color back into a palette index, and optionally the light and mixing
tables built from it. Both games use the same format and the same code: the color library (`color.c`
in the original, a shared library of Interplay's) is identical in the two, apart from addresses.

`color.pal` in `master.dat` is the palette for nearly everything: the map, critters, items, the
interface. The other palettes are for full-screen pictures and movies (see [Which palettes
exist](#which-palettes-exist)).

## Layout

| Offset    | Size   | Contents                                                                   |
|-----------|--------|----------------------------------------------------------------------------|
| `0x00000` | 768    | the palette: 256 entries of `R, G, B`, one byte each, **0–63** (6-bit VGA)   |
| `0x00300` | 32,768 | the inverse table: palette index for every 15-bit color (see below)        |
| `0x08300` | 4      | optional tag; when it matches, the three tables after it follow             |
| `0x08304` | 65,536 | intensity table, `[color][level]`                                          |
| `0x18304` | 65,536 | additive mix table, `[a][b]`                                               |
| `0x28304` | 65,536 | multiplicative mix table, `[a][b]`                                         |

So a file is either 33,536 bytes (`0x8300`), or 230,148 bytes (`0x38304`) with the extra tables. A file
can also be longer than `0x8300` with a non-matching tag; the game then ignores everything past the
inverse table. There's no header and no alpha.

`loadColorTable` (`fallout1-ce: src/plib/color/color.cc`), called `colorPaletteLoad` in
`fallout2-ce: src/color.cc`, reads the file in that order.

### The tag

The game reads the tag as a raw little-endian 32-bit integer and compares it with `0x4E455743`, the
C character constant `'NEWC'`. On disk that is the bytes `43 57 45 4E`, which spell **`CWEN`**, not
`NEWC`. The CE source comments call it "NEWC", and so do the fodev.net PAL page and the falloutmods wiki,
which give the tag as `"NEWC"` at `0x8300`. A reader should accept both spellings and say which one it
found.

When the tag doesn't match, the game builds the three tables itself, from the palette and the
inverse table, with the formulas below.

**The shipped palettes have no tag.** Every PAL file in both games, `color.pal` included, is 33,536
bytes: the palette and the inverse table, nothing after. So the game always builds the tables itself,
and which spelling of the tag it would accept never comes up. `color.pal` is byte-identical in the US
and European releases of both games.

### Out-of-range entries

An entry with any component above 63 is "unmapped": the game sets it to black and marks it in a
256-byte flag array (`mappedColor`). Unmapped entries get an all-zero intensity row, and the mix
tables pass them through unchanged (mixing `a` with an unmapped `b` gives `a`, and the other way
round). A reader should copy the behaviour.

`color.pal` relies on it, as the falloutmods wiki's *Pal files* page says: index 0 and indices 229–255
hold 255 in every component. All of them load as unmapped black, and the cycling colors come only from
the executable (see [Color cycling](#color-cycling)). Every other entry is within 0–63.

## The 6-bit scale and 8-bit RGB

The game hands the palette to the hardware as 6-bit values shifted left by two:

    rgb8 = rgb6 << 2        (0 → 0, 63 → 252)

This is in `GNW95_SetPalette` and `GNW95_SetPaletteEntries` (`fallout1-re: src/plib/gnw/svga.c`, both
the DirectDraw palette and the 16-bit fallback) and in `directDrawSetPalette` in
`fallout2-ce: src/svga.cc`. So the brightest white the game can show is `(252, 252, 252)`. The fodev.net
page suggests `(c << 2) | (c >> 4)` "for better distribution", which reaches 255; that's a nicer
conversion but not the game's. Use `<< 2` to match what players saw.

Before the shift the values go through a 64-entry gamma table, `round_down(min(i ** gamma, 63))`
(`colorGamma` / `colorSetBrightness`). The brightness slider in the options sets `gamma` from 1.0 to
1.18 (`GAMMA_MAX` in `fallout1-ce: src/game/options.cc`). At the default 1.0 the table is the
identity. Despite the name, values above 1 brighten here, since `i ** 1.18 > i`. Entries 0 and 1 never
change, since `0 ** g = 0` and `1 ** g = 1` (the wiki's *Pal animations* page points this out).

## The inverse table

32,768 bytes, one palette index per 15-bit color:

    index = table[(r5 << 10) | (g5 << 5) | b5]        r5, g5, b5 in 0–31

Red is in the high bits. The game makes the 5-bit components in two ways:

| From                           | Code                                                           |
|--------------------------------|----------------------------------------------------------------|
| a palette entry (6-bit)        | `c5 = c6 >> 1` (`Color2RGB`)                                   |
| an 8-bit RGB image             | `c5 = c8 >> 3` (`datafileConvertData`, `fallout1-ce: src/int/datafile.cc`) |

The game never computes "nearest color" at run time. Every RGB-to-index conversion is a lookup in this
table, and every derived table below is built by doing 5-bit arithmetic and then a lookup. Many code
paths ask for a color by its 15-bit value directly, for example `colorTable[31744]` for pure red and
`colorTable[0]` for black. So "black" in the game is whatever index the table gives for `(0, 0, 0)`,
not necessarily index 0.

Note that `Color2RGB(i)` followed by a lookup doesn't always return `i`: two entries that share their
5-bit color come back as the same one.

In the shipped `color.pal`:

- black, `table[0]`, is index **228**;
- the table never answers 0 or 229–255, only indices 1–228, and 226 of those;
- the round trip fails for three entries: 84 comes back as 78, 117 as 4 and 208 as 13.

`datafileConvertData`, which remaps the interpreter's PCX and BMP pictures into the game palette, puts
the image palette's **third** byte in the red position (its own comment says "TODO: Check"). For an
R, G, B palette that swaps red and blue; it's probably meant for B, G, R data. It keeps index 0 as 0.

## Derived tables

All of these are `[256][256]` arrays of palette indices. The formulas are from `setIntensityTableColor`
and `setMixTableColor` (`fallout1-ce: src/plib/color/color.cc`); `c5` is a 5-bit component of the color
from `Color2RGB`, and every result goes through the inverse table.

### Intensity

`intensity[c][k]`, `k` = 0–255:

| `k`        | Result                                        |
|------------|-----------------------------------------------|
| 0–127      | darker: `c5 × k >> 7` (k = 0 is black)        |
| 128–255    | lighter: `c5 + ((31 − c5) × (k − 128) >> 7)` (k = 128 is the color itself) |

Light in the game is an integer from 0 to 65,536 (full light), and the row index is `light / 512`, so
full light is column 128 (`calculateColor`).

### Additive mix

`add[a][b]` adds the two 5-bit colors. If no channel passes 31, the sum is looked up. Otherwise the
overflow `m − 31` (where `m` is the largest channel) is subtracted from all three channels, clamped at
0, looked up, and the result is lightened to intensity column `128 + (m − 31)`.

### Multiplicative mix

`mul[a][b]` is `a5 × b5 >> 5` per channel, looked up.

### Blend tables for a single color

`getColorBlendTable(ch)` builds, on demand, 16 tables of 256 (4,096 bytes, plus a 4-byte reference
count in front); 14 are filled (`buildBlendTable`):

| Table   | Entry for screen pixel `x`                                         |
|---------|--------------------------------------------------------------------|
| 0       | `x` (unchanged)                                                    |
| 1–7     | `(k × ch5 + (7 − k) × x5) // 7` per channel, for table `k`, looked up |
| 8–13    | the same for every `x`: `ch` at intensity column 127, 146, 164, 182, 201, 219 |
| 14–15   | not filled                                                         |

Tables 1–7 move the pixel toward `ch` in sevenths; 8 is `ch` itself (column 127 is 1/128 short of full),
and 9–13 are `ch` lightened toward white. These tables are how text and translucent objects are drawn:
the source pixel picks the table, the screen pixel the entry.

## Lighting

Objects and floor tiles are drawn with `dark_trans_buf_to_buf` (`fallout2-ce: src/object.cc`):

- index **0 is skipped**: it is transparent in FRMs, floor tiles and every other sprite;
- indices **229–255 are drawn unchanged**, never darkened (`color < 0xE5` guards the lookup). They're
  the color-cycling range, so fire, monitors and glowing slime stay bright in the dark;
- every other index `c` becomes `intensity[c][light / 512]`.

The light an object gets is `max(ambient, tile light)`, capped at 65,536 (`_obj_render_pre_roof` in
`object.cc`). Ambient light is clamped to 16,384–65,536 (`LIGHT_INTENSITY_MIN` and `_MAX` in
`fallout2-ce: src/light.h`); the Night Vision perk adds 13,107 a rank. Scripts set it as 0–100
(`opSetLightLevel` in `fallout2-ce: src/interpreter_extra.cc`): exactly 50 gives 40,960, but the two
halves both scale `level / 100` of a half-range, so 0–49 give 16,384–28,426 and 51–100 give
53,493–65,536, with a jump either side of 50. So in practice sprites use intensity columns 32–128, and the
"lighter" half of the table is only used by blend tables and a few interface effects
(`lighten_buf` uses column 147).

At full light (column 128) a pixel is replaced by the inverse table's choice for its own 5-bit color.
Usually that's the same index, but not always: with `color.pal`, indices 84, 117 and 208 turn into 78,
4 and 13 even at full light (see [The inverse table](#the-inverse-table)).

## Translucency

A prototype's flags pick one of six drawing modes for an object (`obj_types.h`, copied to the object in
`objectCreateWithFidPid` / `obj_new`):

| Flag (proto and object) | Mode         | Tint `ch` = `table[...]` (5-bit R, G, B) | Gray table | Light      |
|-------------------------|--------------|------------------------------------------|------------|------------|
| `0x00004000`            | red          | `31744` = (31, 0, 0)                     | common     | object's   |
| `0x00008000`            | none (opaque, overrides the others) | —                 | —          | —          |
| `0x00010000`            | wall         | `25439` = (24, 26, 31), pale blue        | common     | always full |
| `0x00020000`            | glass        | `10239` = (9, 31, 31), cyan              | glass      | object's   |
| `0x00040000`            | steam        | `32767` = (31, 31, 31), white            | common     | object's   |
| `0x00080000`            | energy       | `30689` = (29, 31, 1), yellow            | common     | object's   |

The proto flags are checked in the order none, wall, glass, steam, energy, red; the first one set wins.

A translucent object's own colors are thrown away. `dark_translucent_trans_buf_to_buf` does, for every
non-zero source pixel `s` over screen pixel `d`:

    k   = gray[s]                     # 0–7
    out = intensity[blend(ch)[k][d]][light / 512]

where the gray tables are built in `obj_blend_table_init` from the 5-bit components:

| Table  | `gray[c]`                               |
|--------|-----------------------------------------|
| common | `((b + 3r + 6g) // 10) >> 2`            |
| glass  | `((r + 5g + 4b) // 10) >> 2`            |

Both are 0 for index 0. So a bright source pixel paints the tint strongly, a dark one lets the screen
show through. The same mechanism (with `wall` and `red`) draws some outlines and the hex-grid overlay.

### The egg

Walls near the player are see-through inside an egg-shaped mask, interface art number 2. The mask's
pixel values aren't colors but weights from 0 to 128. `intensity_mask_buf_to_buf` draws the wall pixel
`c` over screen pixel `d` with mask value `m` as

    out = add[intensity[c'][m]][intensity[d][128 − m]]     (c' = c lit; plain c' where m = 0)

### Outlines

Object outlines use cycling indices so they pulse: hostile critters are outlined with 243 (fast fire,
red), friendly ones with 229 (slime, green) (`objectDrawOutline` in `object.cc`).

## Color cycling

`cycle.c` animates indices 229–254 by rewriting them in the hardware palette from built-in color lists
(`colorCycleTicker` in `fallout2-ce: src/cycle.cc`, `cycle_colors` in `fallout1-ce: src/game/cycle.cc`).
**Fallout 1 and Fallout 2 are identical**: same indices, colors and periods.

| Indices   | Name in source | Colors | Step   | Full loop | Looks like              |
|-----------|----------------|-------:|-------:|----------:|-------------------------|
| 229–232   | `slime`        | 4      | 200 ms | 800 ms    | green: toxic goo        |
| 233–237   | `monitors`     | 5      | 100 ms | 500 ms    | blue-grey: computer screens |
| 238–242   | `fire_slow`    | 5      | 200 ms | 1,000 ms  | red and orange: fire    |
| 243–247   | `fire_fast`    | 5      | 142 ms | 710 ms    | dark reds: fire         |
| 248–253   | `shoreline`    | 6      | 200 ms | 1,200 ms  | browns: shoreline water |
| 254       | `bobber_red`   | 1      | 33 ms  | 990 ms    | red pulse: alarms       |
| 255       | —              | —      | —      | —         | not animated            |

The steps are `1000 / 5`, `1000 / 7`, `1000 / 10` and `1000 / 30` ms, integer-divided (Fallout 1 writes
them as 200, 142, 100, 33). Each is multiplied by `cycle_speed_factor` from the `[system]` section of
the game config (default 1), and cycling can be turned off with `color_cycling=0`. The ticker runs from
the main loop, so a step happens on the first tick after its period has passed. Cycling is paused during
palette fades.

The color lists in the source are 8-bit values, shifted right by two once at start-up. In 6-bit
(and in brackets the 8-bit the screen shows, `<< 2`):

| Name        | Colors, in order (6-bit R, G, B)                                                 |
|-------------|----------------------------------------------------------------------------------|
| `slime`     | (0, 27, 0), (2, 28, 1), (6, 30, 3), (10, 32, 6)                                  |
| `monitors`  | (26, 26, 27), (24, 25, 31), (21, 26, 35), (0, 36, 40), (26, 46, 63)              |
| `fire_slow` | (63, 0, 0), (53, 0, 0), (36, 10, 2), (63, 29, 0), (63, 14, 0)                    |
| `fire_fast` | (17, 0, 0), (30, 0, 0), (44, 0, 0), (30, 0, 0), (17, 0, 0)                       |
| `shoreline` | (20, 15, 10), (18, 14, 10), (16, 13, 9), (15, 12, 9), (13, 11, 8), (12, 10, 8)   |

On the first tick (the timers start at 0, so it's immediate), index `base + i` gets color `i`. Each step
after that the list moves one index up: after `t` steps, index `base + i` shows color `(i − t) mod n`.

Index 254 is `(r, 0, 0)` with `r` bouncing between 0 and 60 in steps of 4 (6-bit): 4, 8, …, 60, 56, …,
0, 4, … — 30 steps per loop.

Two consequences:

- The cycling only changes the **hardware palette**. The palette in memory, which the inverse table,
  the intensity tables and the blend tables were built from, keeps the file's colors at 229–254. Those
  file colors are what you see with cycling off, and what any table lookup involving these indices
  uses. `color.pal` stores 255s there, which load as black (see
  [Out-of-range entries](#out-of-range-entries)), so a still render with cycling off shows them black.
- Light doesn't touch 229–255 (see [Lighting](#lighting)), so these pixels always show the cycled color
  at full strength.

## Which palettes exist

| Path                                      | Game   | Used for                                                       |
|-------------------------------------------|--------|----------------------------------------------------------------|
| `color.pal`                               | both   | everything in play: map, critters, items, interface            |
| `art/intrface/helpscrn.pal`               | both   | the help screen (`helpscrn.frm`)                               |
| `art/intrface/death.pal`                  | both   | the death screen                                               |
| `art/intrface/<name>.pal`                 | both   | ending slides: for a slide FRM `<name>.frm`, the game loads the PAL of the same base name (`endgameEndingLoadPalette`) |
| `art/cuts/subtitle.pal`                   | both   | loaded while a movie plays with subtitles                      |
| `art/cuts/introsub.pal`, `eldersub.pal`, `artmrsub.pal`, `crdtssub.pal` | F2 | per-movie subtitle palettes (`gMoviePaletteFilePaths` in `fallout2-ce: src/game_movie.cc`) |
| any path                                  | both   | the script opcode `loadpalettetable`                           |

The movies (MVE) carry their own palettes in the stream; the subtitle PAL only provides the tables
for drawing the text. Splash screens (RIX) also carry their own palette (see below).

The art loader (`art.c`) never picks a palette: an FRM has no palette reference, and every FRM in the
world is drawn with `color.pal`. A PAL next to an FRM is only used where the code above names it.

The shipped ending-slide palettes are `art/intrface/seq*.pal` in Fallout 1 and `eg_*.pal` in Fallout 2;
both games also have `dp.pal`, and Fallout 2 `arroyo01.pal`. Like `color.pal`, every one is 33,536
bytes with no tag. The slide palettes use real colors (0–63) in all 256 entries, the cycling range
included. `subtitle.pal`, `crdtssub.pal` and `arroyo01.pal` keep `color.pal`'s 255s at 229–255.

## Other image formats

| Format | Where                     | In short                                                          |
|--------|---------------------------|-------------------------------------------------------------------|
| RIX    | `art/splash/splash<n>.rix` (F2 also `art/<language>/splash/`), n = 0–9 | `RIX3`, width and height (16-bit little-endian), 2 bytes the game skips (fodev: `0xAF`, `0x00`), a 768-byte 6-bit palette at offset 10, then width × height raw indices. Read by `game_splash_screen` (F1) and `showSplash` (F2) |
| MSK    | F2 world map              | not a picture: a 1-bit walkability mask for a 350 × 300 world-map tile, 13,200 bytes, 44 bytes a row, low bit first, 1 = blocked (fodev.net) |
| AAF    | `font<n>.aaf`             | interface fonts: signature `AAFF`, big-endian, 12-byte header, 256 glyph records of 8 bytes, then one byte per pixel, 0–9. The pixel picks the blend table of the text color (0 transparent, 1–7 mixed in sevenths, 8 the color, 9 lighter); see `interfaceFontDrawImpl` in `fallout2-ce: src/font_manager.cc` |
| FON    | `font<n>.fon`             | 1-bit bitmap fonts, little-endian, no signature (fodev.net); set bits draw the text color |
| PCX    | interpreter (scripts, mouse cursors) | standard 8-bit PCX with the 256-color palette at the end (`12` marker 769 bytes from the end); remapped into the game palette through the inverse table (`fallout1-ce: src/int/pcx.cc`) |
| BMP    | interpreter               | loaded through a pluggable loader (`setBitmapLoadFunc`), remapped the same way. Whether the shipped data uses it is unchecked |
| MVE    | `art/cuts/*.mve`          | Interplay movies, with palette opcodes that set 6-bit ranges of the palette |

None of these are sprite formats; glisomorph only needs FRM and `color.pal`.

## Notes for glisomorph

- **Transparent is 0.** Any index 1–255 is drawn. Keep 0 out of model colors except for empty pixels.
- **Safe range is 1–228.** These are the only indices that are lit normally and never animate. When
  mapping an interpolated color back, restrict the search to 1–228 unless the source pixels were in
  the cycling range.
- **229–254 animate and ignore light.** A pixel in that range is a glow (fire, screens, slime, alarm),
  not a surface color. Treat it as its own material: keep its index, never blend it with neighbours in
  RGB, and don't map ordinary colors into it. For a texture, use the cycling colors' first frame or a
  fixed representative, but write the original index back. The file's own colors at these indices are
  what a renderer without cycling shows.
- **255** isn't animated but is also never darkened. Avoid it for ordinary colors.
- **Map RGB back the game's way:** from 8-bit RGB, `table[((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3)]`.
  This is cheap and is exactly what the engine does. With the shipped `color.pal` it only ever answers
  1–228, so it never produces a transparent or cycling pixel. But 5 bits per channel is coarse: a
  nearest-color search over 1–228 in 6-bit space is more accurate. Use the inverse table when the goal
  is to reproduce the game, or as a check. Either way, compare in the palette's own 6-bit values (or
  `<< 2` 8-bit), not `(c << 2) | (c >> 4)`.
- **Critters hardly use the cycling range.** In Fallout 2's critter art, 0.009% of the opaque pixels
  are in 229–254, spread over 36 of the 96 base names, and about 2,500 pixels are 255. Most look like
  strays; the Glowing One (`naglow`, index 247) is the clear exception. The game's black, 228, is
  almost unused in critter art (764 pixels in Fallout 2, none in Fallout 1).
- **Light works per channel, not per ramp.** Unlike Diablo, Fallout doesn't darken along ramps: it
  scales the 5-bit RGB and looks the result up. So a pixel's index doesn't have to share a "ramp" with
  its neighbours to light correctly, and nearest-color mapping is safe for lighting.
- **Translucent critters and items** (glass, steam, energy, red, wall flags) only use the luminance of
  their pixels. For those, the hue of an interpolated color doesn't matter, only its `gray` value
  (0–7).

## Loading in Python

Independent code, written from the descriptions above.

```python
import numpy as np

TAGS = (b"CWEN", b"NEWC")  # the game's compare matches b"CWEN"; see "The tag"
CYCLE_FIRST, CYCLE_LAST = 229, 254


def load_pal(path):
    """Read a Fallout PAL. Returns a dict with 6-bit and 8-bit palettes and the tables."""
    data = open(path, "rb").read()
    if len(data) < 0x8300:
        raise ValueError(f"{path}: {len(data)} bytes, want at least 0x8300")

    pal6 = np.frombuffer(data, np.uint8, 768).reshape(256, 3).copy()
    mapped = (pal6 <= 63).all(axis=1)
    pal6[~mapped] = 0                       # the game blacks out entries above 63

    inverse = np.frombuffer(data, np.uint8, 0x8000, 0x300)
    tag = data[0x8300:0x8304]
    out = {"pal6": pal6, "rgb": pal6.astype(np.uint16) << 2, "mapped": mapped,
           "inverse": inverse, "tag": tag}

    if tag in TAGS and len(data) >= 0x38304:
        tables = np.frombuffer(data, np.uint8, 3 * 0x10000, 0x8304).reshape(3, 256, 256)
        out["intensity"], out["add"], out["mul"] = tables
    else:
        out["intensity"] = build_intensity(pal6, mapped, inverse)
    return out


def rgb555(c5):
    """(..., 3) array of 5-bit components -> 15-bit inverse-table keys."""
    c5 = np.asarray(c5, np.int32)
    return (c5[..., 0] << 10) | (c5[..., 1] << 5) | c5[..., 2]


def build_intensity(pal6, mapped, inverse):
    """intensity[c][k] as the game builds it when the file has no extra tables."""
    c5 = (pal6 >> 1).astype(np.int32)[:, None, :]      # (256, 1, 3)
    k = np.arange(128, dtype=np.int32)[None, :, None]  # (1, 128, 1)
    darker = (c5 * k) >> 7
    lighter = c5 + (((31 - c5) * k) >> 7)
    table = np.concatenate([inverse[rgb555(darker)], inverse[rgb555(lighter)]], axis=1)
    table[~mapped] = 0
    return table.astype(np.uint8)


def rgb8_to_index(rgb8, inverse):
    """The engine's RGB-to-index conversion: drop to 5 bits, look up."""
    return inverse[rgb555(np.asarray(rgb8, np.int32) >> 3)]


def nearest_index(rgb8, pal6, allowed=range(1, CYCLE_FIRST)):
    """Nearest palette entry among `allowed` (default 1-228: not transparent, not animated)."""
    idx = np.fromiter(allowed, np.int32)
    ref = pal6[idx].astype(np.float32) * 4.0
    d = ((np.asarray(rgb8, np.float32)[..., None, :] - ref) ** 2).sum(-1)
    return idx[d.argmin(-1)].astype(np.uint8)
```

## Notes on the wiki

The falloutmods wiki's PAL pages (*PAL File Format*, a translation of TeamX's document; *Pal files*;
*Pal animations* and *Color Processing*, two translations of TeamX's palette-processing article)
agree with the code on the layout, the 0–63 range, the blacking-out of entries above 63, the ×4
conversion, the 15-bit inverse-table key, the gamma range 1.0–1.18, the cycling groups, their colors
(given as the source's 8-bit values) and their periods. The differences:

- **Lighting.** *Pal files* says the engine multiplies the palette by a brightness modifier from 1
  (night) to 4 (noon). There's no such modifier in the code. The ×4 is the 6-bit to 8-bit conversion,
  the same at any time of day, and light goes through the intensity table (see [Lighting](#lighting)).
- **Cycling groups.** *PAL File Format* says 238–247 are fire and "the rest" (233–237 and 248–254)
  computer screens. The code has 233–237 monitors, 248–253 shoreline and 254 the alarm red.
- **Cycling order.** The *Pal animations* sample code writes each list backwards: at the start index
  `base + n − 1` gets color 0. The game gives index `base + i` color `i` at the start, and colors move
  up one index per step in both. Only the phase differs.
- **Index 254.** The same sample steps the alarm red by 16 up to 240 and writes it straight into the
  6-bit palette. The game steps by 4 from 0 to 60, in 6-bit units.
- **Tag.** All the pages write the tag as `NEWC`; see [The tag](#the-tag). No shipped palette has
  either spelling.
- **The extra tables.** *PAL File Format* calls the three tables after the tag unexplained, generated
  by the game when missing. That matches the code, which builds intensity, additive and
  multiplicative tables (see [Derived tables](#derived-tables)).
- **Index 255.** *Pal files* says it seems unused by FRMs and holds 255s. It does hold 255s, so it
  loads as black, but FRMs do use it: about 2,500 pixels in Fallout 2's critter art and over 300,000 in
  its interface art. The code never cycles it but also never darkens it ([Lighting](#lighting)).

## Checked against the game data

The formats and formulas come from the engine reimplementations. The data was checked on 2026-10-03
against every PAL file and every FRM of four CD releases (Fallout 1 US and European, Fallout 2 US and
UK):

- `color.pal`'s size and tag, the 255s at 0 and 229–255, the other entries' range, black, the
  inverse table's answers and its round trip (see [The tag](#the-tag),
  [Out-of-range entries](#out-of-range-entries) and [The inverse table](#the-inverse-table));
- the other PAL files' sizes, tags and ranges (see [Which palettes exist](#which-palettes-exist));
- which palette indices the art uses, counted per art folder over every frame (see
  [Notes for glisomorph](#notes-for-glisomorph)).

Not checked: the derived tables, which the files don't store, so there was nothing to compare
`build_intensity` and the mix formulas against; the color-cycling lists, which live in the executable;
and how the game looks on screen.

## Sources

- fallout1-ce (0609bcf): `src/plib/color/color.cc` (`loadColorTable`, `Color2RGB`, `setIntensityTableColor`,
  `setMixTableColor`, `buildBlendTable`, `colorGamma`), `src/game/cycle.cc` (`cycle_colors`),
  `src/game/object.cc` (`obj_blend_table_init`), `src/int/datafile.cc`, `src/int/pcx.cc`,
  `src/game/options.cc`.
- fallout2-ce (e97087b): `src/color.cc` (`colorPaletteLoad`), `src/cycle.cc` (`colorCycleTicker`),
  `src/object.cc` (`_dark_trans_buf_to_buf`, `_dark_translucent_trans_buf_to_buf`,
  `_intensity_mask_buf_to_buf`, `_obj_blend_table_init`, outlines), `src/light.cc`, `src/light.h`,
  `src/interpreter_extra.cc` (`opSetLightLevel`), `src/game_movie.cc`, `src/endgame.cc`,
  `src/game.cc` (splash), `src/font_manager.cc`, `src/svga.cc`.
- fallout1-re (ac9784b), fallout2-re (b135fc4): `src/plib/color/color.c` (the tag constant
  `0x4E455743`), `src/plib/gnw/svga.c` (`GNW95_SetPalette`, the `<< 2`).
- fodev.net Fallout 2 format pages (`pal.html`, `rix.html`, `msk.html`, `aaf.html`, `fon.html`).
- The falloutmods wiki, read through the MediaWiki API (`api.php?action=parse&prop=wikitext`), since
  plain page fetches return HTTP 402:
  [PAL File Format](https://falloutmods.fandom.com/wiki/PAL_File_Format),
  [Pal files](https://falloutmods.fandom.com/wiki/Pal_files),
  [Pal animations](https://falloutmods.fandom.com/wiki/Pal_animations),
  [Color Processing](https://falloutmods.fandom.com/wiki/Color_Processing),
  [Color.pal](https://falloutmods.fandom.com/wiki/Color.pal) (a GIMP palette taken from FIFE, not from
  the game file) and [Working with palettes](https://falloutmods.fandom.com/wiki/Working_with_palettes)
  (a tutorial, nothing on the format).
