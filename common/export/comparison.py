"""The game's frames above ours, in every direction, as one animated file: the comparison grid.

    ComparisonExporter(play=["walk", "walk", "walk", "attack"], zoom=1).export(sprite, "out/marine.gif")

The sprite needs its original (Sprite.original): the game's own frames, at the game's scale and speed, in
the same directions, None where the game doesn't draw one. Each row is a strip of directions, a number
above each cell:

- the top row is the game's: its frame in each direction it draws. A direction it doesn't draw keeps its
  number, in gray, over an empty cell; one it draws as a mirror image is numbered in orange.
- the bottom row is ours, in every direction; the ones glisomorph made are numbered in blue.

The rows play together in time. `play` names the animations in order (repeats allowed; default every
animation once), and the file loops through them. Each of our frames shows over the game's frame playing at
the same moment of the same animation, so where ours has more frames each of the game's stays up over
several of ours. The game's frames are enlarged by nearest neighbour to our scale, each of its pixels a
block, and placed by the pivots. Then everything is enlarged by `zoom`.

With `per_line` the directions wrap into bands of that many, each band a top and a bottom row. With
crop="direction" each direction gets its own window, all one size, for overlays that reach far from the
unit (the firebat's flame); the default keeps one window for all.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from common.export.preview import MIRRORED, MISSING, NEW, TEXT, PreviewExporter, extent, save_animated, union
from common.export.sprite import Sprite


class ComparisonExporter(PreviewExporter):
    """The comparison grid (see the module). Options, besides PreviewExporter's:

    play: animation names in the order they play, repeats allowed; default each once.
    rows: the two rows' labels.
    per_line: directions to a band; 0 puts them all in one.
    crop: "union" (one window) or "direction" (one each)."""

    def __init__(self, play: list[str] | None = None, rows=("game", "ours"), per_line: int = 0,
                 crop: str = "union", **options):
        super().__init__(**options)
        self.play, self.rows, self.per_line, self.crop = play, tuple(rows), per_line, crop

    def timeline(self, sprite: Sprite) -> list[tuple[int, int, float]]:
        """(our frame, the game's frame, milliseconds) for each of our frames, in play order."""
        original = sprite.original
        out = []
        for name in self.play or [a.name for a in sprite.animations]:
            ours, theirs = sprite.animation(name), original.animation(name)
            starts = np.asarray(theirs.starts())
            for t, frame, duration in zip(ours.starts(), ours.frames, ours.durations):
                j = int(np.searchsorted(starts, t + 1e-6, side="right")) - 1  # the game's entry playing at t
                out.append((frame, theirs.frames[min(max(j, 0), len(theirs.frames) - 1)], duration))
        return out

    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        path = self.check_suffix(path)
        original = sprite.original
        if original is None:
            raise ValueError("a comparison needs the game's own frames: set the sprite's original")
        factor = sprite.scale // original.scale
        if factor * original.scale != sprite.scale:
            raise ValueError("our scale (%d) has to be a whole multiple of the game's (%d)" % (sprite.scale,
                                                                                            original.scale))
        timeline = self.timeline(sprite)
        n = sprite.directions

        def picture(row, f, d):  # the game's enlarged to our scale; None where it doesn't draw
            if row == "ours":
                return self.picture(sprite, f, d)
            return self.picture(original, f, d, factor) if d < original.directions else (None, (0, 0))

        # the windows, from what every picture shown draws (pictures are made again for the tiles rather
        # than kept: a large render's would take a lot of memory)
        extents = []
        for d in range(n):
            extents.append(union([extent(*picture("ours", f, d)) for f in {fo for fo, _, _ in timeline}] +
                                 [extent(*picture("game", f, d)) for f in {ft for _, ft, _ in timeline}]))
        windows = self.windows(extents, self.crop, self.margin * sprite.scale)
        tiles = {}

        def tile(row, f, d):  # None where the game doesn't draw
            if (row, f, d) not in tiles:
                rgba, anchor = picture(row, f, d)
                tiles[row, f, d] = None if row == "game" and rgba is None else self.tile(rgba, anchor, windows[d])
            return tiles[row, f, d]
        top0, bottom0, left0, right0 = windows[0]
        cw, ch = (right0 - left0) * self.zoom, (bottom0 - top0) * self.zoom

        gap, head = 6, self.font_size + 7
        label_w = max(self.text_width(r) for r in self.rows) + 2 * gap
        per = self.per_line or n
        bands = [list(range(s, min(s + per, n))) for s in range(0, n, per)]
        band_h = 2 * (head + ch) + gap
        width = label_w + min(per, n) * (cw + gap)
        height = len(bands) * band_h + (len(bands) - 1) * 3 * gap

        images, durations = [], []
        for fo, ft, duration in timeline:
            image = Image.new("RGB", (width, height), self.background)
            draw = ImageDraw.Draw(image)
            for b, columns in enumerate(bands):
                oy = b * (band_h + 3 * gap)
                self.text(draw, (4, oy + head + ch // 2 - self.font_size // 2), self.rows[0])
                self.text(draw, (4, oy + 2 * head + ch + gap + ch // 2 - self.font_size // 2), self.rows[1])
                for j, d in enumerate(columns):
                    x = label_w + j * (cw + gap)
                    game = tile("game", ft, d)
                    color = MIRRORED if d in sprite.mirrors else MISSING if game is None else TEXT
                    self.text(draw, (x + 2, oy + 2), sprite.label(d), color)
                    if game is not None:
                        image.paste(game, (x, oy + head))
                    color = MIRRORED if d in sprite.mirrors else NEW if d in sprite.new_directions else TEXT
                    self.text(draw, (x + 2, oy + head + ch + gap + 2), sprite.label(d), color)
                    image.paste(tile("ours", fo, d), (x, oy + 2 * head + ch + gap))
            images.append(image)
            durations.append(duration)
        return [save_animated(images, durations, path)]
