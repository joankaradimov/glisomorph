"""One animated file showing the whole sprite: facing one direction it plays every animation, then turns to
the next direction and plays them again, until every direction has had its turn.

    DemoExporter(play=["walk", "walk", "attack"], zoom=3).export(sprite.mirrored(), "out/marine-demo.gif")

`play` names the animations in order (repeats allowed; default each once), and `directions` the directions
in the order visited (default every one, in order). For a game that draws half its turn by mirroring,
pass sprite.mirrored() to go all the way round. Every frame goes through the same window, so the unit
stays put while it turns. A caption above names the direction (in blue when glisomorph made it, orange
for a mirror image) and the animation.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from common.export.preview import MIRRORED, NEW, TEXT, PreviewExporter, extent, grown, save_animated, union
from common.export.sprite import Sprite


class DemoExporter(PreviewExporter):
    """Every animation in every direction, in one file (see the module). Options, besides
    PreviewExporter's:

    play: animation names in the order they play in each direction, repeats allowed; default each once.
    directions: the directions in the order visited; default all of them, in order.
    caption: write the direction and the animation above the unit."""

    def __init__(self, play: list[str] | None = None, directions: list[int] | None = None, caption: bool = True,
                 **options):
        super().__init__(**options)
        self.play, self.directions, self.caption = play, directions, caption

    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        path = self.check_suffix(path)
        animations = [sprite.animation(name) for name in self.play or [a.name for a in sprite.animations]]
        directions = list(self.directions) if self.directions is not None else list(range(sprite.directions))
        frames = sorted({f for a in animations for f in a.frames})
        window = union([extent(*self.picture(sprite, f, d)) for f in frames for d in directions])
        window = grown(window if window is not None else (0, 1, 0, 1), self.margin * sprite.scale)
        top, bottom, left, right = window
        cw, ch = (right - left) * self.zoom, (bottom - top) * self.zoom
        head = self.font_size + 7 if self.caption else 0
        width = max(cw, max((self.text_width("%s  %s" % (sprite.label(d), a.name)) for d in directions
                             for a in animations), default=0) + 8 if self.caption else 0)
        tiles, images, durations = {}, [], []
        for d in directions:
            color = MIRRORED if d in sprite.mirrors else NEW if d in sprite.new_directions else TEXT
            for a in animations:
                for f, duration in zip(a.frames, a.durations):
                    image = Image.new("RGB", (width, head + ch), self.background)
                    if self.caption:
                        self.text(ImageDraw.Draw(image), (4, 2), "%s  %s" % (sprite.label(d), a.name), color)
                    if (f, d) not in tiles:
                        tiles[f, d] = self.tile(*self.picture(sprite, f, d), window)
                    image.paste(tiles[f, d], ((width - cw) // 2, head))
                    images.append(image)
                    durations.append(duration)
        return [save_animated(images, durations, path)]
