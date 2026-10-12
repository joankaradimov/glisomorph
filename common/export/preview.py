"""What the preview exporters share: cells cut out about the unit, colors for their labels, and writing an
animated GIF, APNG or WebP.

The file type follows the path's suffix: .gif, .png or .apng (an animated PNG), .webp (lossless). GIF
stores delays in hundredths of a second and browsers draw any under 20 ms at 100 ms, so its delays are
rounded to 10 ms, carrying the error so the total stays right, and kept at 20 ms or more. APNG and WebP
keep milliseconds.

A window is a part of the canvas about the unit's position, (top, bottom, left, right) in pixels from the
anchor, bottom and right exclusive. A preview cuts every picture through the same window, so the unit
stays put from frame to frame.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from common.export.sprite import Exporter, Sprite

BACKGROUND = (36, 40, 36)
TEXT = (230, 230, 230)
NEW = (110, 160, 255)       # a direction glisomorph made
MIRRORED = (235, 165, 80)   # a direction the game draws as another's mirror image
MISSING = (110, 110, 110)   # a direction the game doesn't draw
FORMATS = {".gif": "GIF", ".png": "PNG", ".apng": "PNG", ".webp": "WEBP"}


def font(size: int):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def gif_durations(durations: list[float]) -> list[int]:
    """Delays for a GIF, in milliseconds: multiples of 10, at least 20, adding up to about the same."""
    out, total, shown = [], 0.0, 0
    for d in durations:
        total += d
        end = max(int(round(total / 10)) * 10, shown + 20)
        out.append(end - shown)
        shown = end
    return out


def save_animated(images: list[Image.Image], durations: list[float], path: str | Path) -> Path:
    """The images as one animation that loops, each shown for its duration (ms); the type from the suffix."""
    path = Path(path)
    kind = FORMATS.get(path.suffix.lower())
    if kind is None:
        raise ValueError("an animation is .gif, .png, .apng or .webp, not %r" % path.suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    first, rest = images[0], images[1:]
    if kind == "GIF":
        first.save(path, format="GIF", save_all=True, append_images=rest, duration=gif_durations(durations),
                   loop=0, disposal=1)
    elif kind == "PNG":
        first.save(path, format="PNG", save_all=True, append_images=rest,
                   duration=[int(round(d)) for d in durations], loop=0)
    else:
        first.save(path, format="WEBP", save_all=True, append_images=rest,
                   duration=[int(round(d)) for d in durations], loop=0, lossless=True)
    return path


def extent(rgba: np.ndarray | None, anchor: tuple[int, int]):
    """The window just holding what a picture draws, or None if it draws nothing."""
    if rgba is None:
        return None
    ys, xs = np.nonzero(rgba[..., 3])
    if len(ys) == 0:
        return None
    ax, ay = anchor
    return int(ys.min() - ay), int(ys.max() + 1 - ay), int(xs.min() - ax), int(xs.max() + 1 - ax)


def union(windows):
    """The smallest window holding them all (None among them ignored; None if all are)."""
    windows = [w for w in windows if w is not None]
    if not windows:
        return None
    return (min(w[0] for w in windows), max(w[1] for w in windows),
            min(w[2] for w in windows), max(w[3] for w in windows))


def grown(window, margin: int):
    top, bottom, left, right = window
    return top - margin, bottom + margin, left - margin, right + margin


def sized(window, height: int, width: int):
    """A window of the given size with `window` at its middle."""
    top, bottom, left, right = window
    top -= (height - (bottom - top)) // 2
    left -= (width - (right - left)) // 2
    return top, top + height, left, left + width


def cut(rgba: np.ndarray | None, anchor: tuple[int, int], window) -> np.ndarray:
    """The part of a picture inside the window: (height, width, 4), transparent where the picture doesn't
    reach (or for None)."""
    top, bottom, left, right = window
    out = np.zeros((bottom - top, right - left, 4), np.uint8)
    if rgba is None:
        return out
    ax, ay = anchor
    y0, y1, x0, x1 = ay + top, ay + bottom, ax + left, ax + right  # the window on the picture
    h, w = rgba.shape[:2]
    cy0, cy1, cx0, cx1 = max(y0, 0), min(y1, h), max(x0, 0), min(x1, w)
    if cy0 < cy1 and cx0 < cx1:
        out[cy0 - y0:cy1 - y0, cx0 - x0:cx1 - x0] = rgba[cy0:cy1, cx0:cx1]
    return out


def flatten(rgba: np.ndarray, background=BACKGROUND) -> np.ndarray:
    """(H, W, 3) uint8: the picture over the background."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = rgba[..., :3].astype(np.float32) * a + np.asarray(background, np.float32) * (1 - a)
    return rgb.round().astype(np.uint8)


def enlarged(array: np.ndarray, factor: int) -> np.ndarray:
    """Each pixel a factor x factor block (nearest neighbour)."""
    if factor == 1:
        return array
    return array.repeat(factor, axis=0).repeat(factor, axis=1)


class PreviewExporter(Exporter):
    """The options every preview takes:

    zoom: every pixel drawn zoom x zoom (nearest neighbour), so the pixels can be seen.
    background: the color under transparent pixels and around the cells.
    margin: pixels of background kept around what's drawn, at the sprite's scale.
    font_size: of the labels; default 16."""

    suffixes = (".gif", ".png", ".apng", ".webp")

    def __init__(self, zoom: int = 1, background=BACKGROUND, margin: int = 1, font_size: int = 16):
        self.zoom, self.background, self.margin, self.font_size = zoom, tuple(background), margin, font_size
        self.font = font(font_size)

    def picture(self, sprite: Sprite, frame: int, direction: int, factor: int = 1):
        """A frame in a direction in color, enlarged `factor` times, and its anchor: (rgba or None, anchor)."""
        if direction >= len(sprite.cells[frame]) and len(sprite.cells[frame]) > 1:
            return None, sprite.anchor
        rgba = sprite.rgba(sprite.cell(frame, direction))
        ax, ay = sprite.anchor
        return (None if rgba is None else enlarged(rgba, factor)), (ax * factor, ay * factor)

    def tile(self, rgba: np.ndarray | None, anchor, window) -> Image.Image:
        """The picture through the window, over the background, zoomed."""
        rgb = flatten(cut(rgba, anchor, window), self.background)
        return Image.fromarray(enlarged(rgb, self.zoom))

    def windows(self, extents: list, crop: str, margin: int):
        """One window per direction from each direction's extent: "union" makes them all the window
        holding every direction; "direction" gives each its own, all one size (for overlays that reach far
        from the unit, a different way in each direction)."""
        if crop not in ("union", "direction"):
            raise ValueError("crop is 'union' or 'direction', not %r" % crop)
        whole = union(extents)
        if whole is None:
            whole = (0, 1, 0, 1)
        if crop == "union":
            return [grown(whole, margin)] * len(extents)
        height = max((e[1] - e[0] for e in extents if e is not None), default=1) + 2 * margin
        width = max((e[3] - e[2] for e in extents if e is not None), default=1) + 2 * margin
        return [sized(e if e is not None else whole, height, width) for e in extents]

    def text(self, draw: ImageDraw.ImageDraw, xy, words: str, color=TEXT) -> None:
        draw.text(xy, words, fill=color, font=self.font)

    def text_width(self, words: str) -> int:
        box = self.font.getbbox(words)
        return int(box[2] - box[0])
