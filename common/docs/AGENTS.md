# Common

Code every game in this repository shares, not tied to one. So far that's writing out the frames
glisomorph makes: as the game's own files, or as previews to look at.

## This folder

| Path                    | Contents                                                        |
|-------------------------|-----------------------------------------------------------------|
| `docs/AGENTS.md`        | this file                                                       |
| `export/sprite.py`      | `Sprite` and `Animation`, what every exporter takes, and `Exporter`, the interface they share |
| `export/preview.py`     | what the previews share: windows about the unit, labels, writing GIF, APNG and WebP |
| `export/comparison.py`  | `ComparisonExporter`: the game's frames above ours, in every direction |
| `export/animation.py`   | `AnimationExporter`: a file per animation, every direction side by side |
| `export/demo.py`        | `DemoExporter`: every animation facing one way, then the next, all in one file |

Exporters for a game's own formats live with the game, in `<game>/export/`. The tests are in `tests/`
at the repository's root (`python -m unittest discover tests`). They build synthetic sprites, never game
data.

## Exporters

Every exporter is an `Exporter`. It takes its options when it's made, and `export(sprite, path)` writes
a sprite and returns the files it wrote. So any exporter can write any sprite, and a pipeline can be
handed a list of them:

```python
from common.export import Animation, ComparisonExporter, DemoExporter, Sprite
from starcraft.export import GrpExporter

sprite = Sprite(cells, palette, [Animation("walk", [0, 1, 2, 3], [67] * 4)], new_directions={1, 3, 5})
for exporter in (GrpExporter(), DemoExporter(zoom=3)):
    exporter.export(sprite, ...)
```

| Exporter             | Module                         | Writes |
|----------------------|--------------------------------|--------|
| `ComparisonExporter` | `common/export/comparison.py`  | one animated file: the game's frames above ours, every direction |
| `AnimationExporter`  | `common/export/animation.py`   | an animated file per animation, every direction side by side |
| `DemoExporter`       | `common/export/demo.py`        | one animated file: every animation in each direction in turn |
| `GrpExporter`        | `starcraft/export/grp.py`      | a StarCraft GRP |
| (planned)            | `diablo1/export/cl2.py`        | a Diablo CL2 |
| (planned)            | `fallout_common/export/frm.py` | a Fallout FRM |

## The sprite

A `Sprite` (in `export/sprite.py`) is what every exporter takes:

- **Frames and directions:** `cells[frame][direction]` is one picture, a cell. A cell is either:
  - an (H, W) integer array of palette indices, -1 where transparent;
  - or an (H, W, 4) uint8 RGBA array. Only previews take these: they're for what isn't drawn through the
    palette, such as glows or shadows composed over the ground.

  A cell is None where the sprite doesn't draw that frame in that direction (the game's 9 of 17,
  say). A frame with a single cell is drawn the same in every direction, as StarCraft's death frames
  are. Every cell shares one canvas.
- **Animations:** frames are stored once and played by `Animation`s, as the games do (a GRP's frames
  and its iscript, a CL2 and its sprite metadata). An animation is a name, the frames it plays in
  order (a frame can come back) and how long each shows, in milliseconds. Game format exporters write
  the frames; previews play the animations.
- **`palette`:** (256, 3), the colors the indices show in, player colors already swapped in.
- **`pivot`:** where the unit stands on the canvas. It defaults to the canvas center, rounded down,
  which is StarCraft's convention. Previews line frames up by it, and so do the original and ours in a
  comparison.
- **`scale`:** pixels per game pixel, such as 4 for a 4× render.
- **`new_directions` and `new_frames`:** what glisomorph made rather than the game. Previews number new
  directions in blue.
- **`mirrors`:** directions drawn as another's mirror image. `mirrored()` adds the directions a game
  draws by mirroring: with StarCraft's 17 it gives all 32, 17 to 31 being 15 to 1 flipped about the
  pivot. That's for previews of a whole turn; the game's own files keep the 17.
- **`original`:** the game's own frames, as a Sprite at the game's scale and speed, with None in the
  directions it doesn't draw. A comparison shows it.
- **`labels` and `name`:** each direction's label in previews (default: its number), and what to call
  the sprite.

## Previews

The previews write an animation that loops, its type set by the path's suffix:

- `.gif`. GIF stores delays in hundredths of a second, and browsers draw any under 20 ms at 100 ms. So
  delays are rounded to 10 ms, the error carried so the total stays right, and kept at 20 ms or more.
  Our frames at twice the game's Normal speed alternate 30 and 40 ms.
- `.png` or `.apng`: an animated PNG, delays in milliseconds.
- `.webp`: lossless, delays in milliseconds.

**Options every preview takes:**

- `zoom`: each pixel drawn as a block, nearest neighbour, so the pixels can be seen.
- `background`: the color behind everything.
- `margin`: pixels kept around what's drawn, at the sprite's scale.
- `font_size`: of the labels.

**Windows and labels:**

- Each preview cuts every picture through a window about the pivot, so the unit stays put from frame
  to frame. By default one window holds what every direction draws.
- `crop="direction"` gives each direction its own window, all one size. That suits overlays that reach
  far from the unit, a different way in each direction, such as the firebat's flame.
- Labels are blue for directions glisomorph made and orange for mirror images. In the game's row of a
  comparison, gray means a direction the game doesn't draw.

### Comparison

`ComparisonExporter(play=None, rows=("game", "ours"), per_line=0, crop="union")`

- **Rows:** the game's frames above ours, in every direction, each cell under its direction's number.
  The game's frames are enlarged to our scale, each of its pixels a block, and placed by the pivots.
- **Timing:** the rows play together in time. `play` names the animations in order, repeats allowed
  (`["walk", "walk", "walk", "attack"]`); by default it plays every animation once. Each of our frames
  shows over the game's frame playing at the same moment of the same animation. Where ours has twice the
  frames, each of the game's stays up over two of ours.
- **Bands:** with `per_line`, the directions wrap into bands, each with a game and an ours row.
- **The sprite** needs its `original`.

### Animation

`AnimationExporter(columns=0, crop="union")`

- **Files:** one per animation, named after the path with the animation's name added: `out/unit.gif`
  gives `out/unit-walk.gif`, `out/unit-attack.gif` and so on.
- **Each frame** shows every direction in a grid `columns` wide (default: one row), each under its
  label.

### Demo

`DemoExporter(play=None, directions=None, caption=True)`

- **Order:** facing one direction, the sprite plays every animation in `play` (default each once), then
  turns to the next and plays them again, until every direction in `directions` has had its turn
  (default all, in order).
- **A whole turn:** for a game that mirrors half its turn, pass `sprite.mirrored()`.
- **Caption:** names the direction and the animation, above the unit.

## Game formats

A game format exporter writes the cells the way the game stores them:

- **What it takes:** palette indices, the game's own canvas, and the game's convention for where the
  unit stands.
- **What it refuses:** anything the format can't hold, with a message: RGBA cells, a direction count
  the game doesn't use, a pivot off where the game puts it, frames too large.
- **Checking:** when there's a reader, it reads the file back and compares it with the cells.

`GrpExporter(check=True)`, in `starcraft/export/grp.py`:

- **Frames:** written in order, each frame's directions together. A turning frame's 17 cells (directions
  0 to 16 of 32) are one animation step of 17 GRP frames, and a single cell is one GRP frame. The
  animations aren't written: the iscript holds them.
- **Pivot:** at the canvas center.
- **Encoding:** see [Writing](../../starcraft/docs/filespecs/grp.md#writing) in the GRP spec.

## Adding an exporter

- **A game format:**
  - It goes in `<game>/export/<format>.py`, as a subclass of `Exporter` with its file `suffixes`.
  - Check the sprite and refuse what the format can't hold. Read the file back with the game's reader
    and compare, where there is one.
  - Document it: the format's spec gets a "Writing" section, and the game's `AGENTS.md` lists the
    module. Test it in `tests/` on synthetic sprites.
- **A preview:** it goes in `common/export/`, as a subclass of `PreviewExporter`. Use its windows,
  tiles and `save_animated`, so it writes every format the others do.
