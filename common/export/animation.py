"""One animated file per animation: its frames in every direction, side by side.

    AnimationExporter(zoom=2, columns=8).export(sprite, "out/warrior.gif")
    # writes out/warrior-walk.gif, out/warrior-attack.gif, ...

Each file is named after `path`, with the animation's name added to the stem. A frame shows every
direction in a grid `columns` wide (default: all in one row), each cell under its label: the directions
glisomorph made in blue, mirror images in orange. The frames play at their durations, and the file loops.
All of an animation's frames go through the same window, so the unit stays put. With crop="direction"
each direction gets its own window, all one size, for overlays that reach far from the unit.
"""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

from common.export.preview import MIRRORED, NEW, TEXT, PreviewExporter, extent, save_animated, union
from common.export.sprite import Sprite


def slug(name: str) -> str:
    """A name as it goes into a file name."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", name).strip("-") or "animation"


class AnimationExporter(PreviewExporter):
    """A file per animation (see the module). Options, besides PreviewExporter's:

    columns: directions to a row of the grid; 0 puts them all in one.
    crop: "union" (one window) or "direction" (one each)."""

    def __init__(self, columns: int = 0, crop: str = "union", **options):
        super().__init__(**options)
        self.columns, self.crop = columns, crop

    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        path = self.check_suffix(path)
        n = sprite.directions
        columns = self.columns or n
        rows = -(-n // columns)
        gap, head = 6, self.font_size + 7
        written = []
        for a in sprite.animations:
            frames = sorted(set(a.frames))
            extents = [union([extent(*self.picture(sprite, f, d)) for f in frames]) for d in range(n)]
            windows = self.windows(extents, self.crop, self.margin * sprite.scale)
            top, bottom, left, right = windows[0]
            cw, ch = (right - left) * self.zoom, (bottom - top) * self.zoom
            width, height = columns * (cw + gap) - gap, rows * (head + ch + gap) - gap
            tiles, images = {}, []
            for f in a.frames:
                image = Image.new("RGB", (width, height), self.background)
                draw = ImageDraw.Draw(image)
                for d in range(n):
                    x, y = (d % columns) * (cw + gap), (d // columns) * (head + ch + gap)
                    color = MIRRORED if d in sprite.mirrors else NEW if d in sprite.new_directions else TEXT
                    self.text(draw, (x + 2, y + 2), sprite.label(d), color)
                    if (f, d) not in tiles:
                        tiles[f, d] = self.tile(*self.picture(sprite, f, d), windows[d])
                    image.paste(tiles[f, d], (x, y + head))
                images.append(image)
            target = path.with_name("%s-%s%s" % (path.stem, slug(a.name), path.suffix))
            written.append(save_animated(images, a.durations, target))
        return written
