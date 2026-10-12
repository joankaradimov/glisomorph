"""The frames glisomorph makes, as every exporter takes them, and the interface exporters share.

A Sprite is a set of frames, each drawn in every direction, and the animations that play them:

    sprite = Sprite(cells, palette, animations=[Animation("walk", [0, 1, 2, 3], [67] * 4)])
    ComparisonExporter(zoom=1).export(sprite, "out/marine.gif")
    GrpExporter().export(sprite, "out/marine.grp")

cells[f][d] is frame f in direction d. A cell is an (H, W) array of palette indices, -1 where transparent,
or, for previews only, an (H, W, 4) uint8 RGBA array (for what isn't drawn through the palette: glows,
shadows over the ground). It's None where the sprite doesn't draw that frame in that direction. A frame
with a single cell is drawn the same in every direction (StarCraft's death frames, say). Every cell of a
sprite shares one canvas, and `pivot` is where the unit stands on it.

Frames are stored once and played by animations, as games do (a GRP's frames and its iscript, a CL2 and
its sprite metadata): a game format exporter writes the frames, a preview plays the animations.

Every exporter is an Exporter: it takes its options when made, and writes a sprite with export(), the
same for all. See common/docs/AGENTS.md.
"""

from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class Animation:
    """A sequence the game plays: frames of the sprite, by index, each shown for a time.

    frames: indices into Sprite.cells, in the order they play (a frame can come back).
    durations: how long each entry of `frames` shows, in milliseconds."""

    name: str
    frames: list[int]
    durations: list[float]

    def __post_init__(self):
        if len(self.frames) != len(self.durations):
            raise ValueError("animation %r: %d frames but %d durations" % (self.name, len(self.frames),
                                                                           len(self.durations)))

    @property
    def length(self) -> float:
        """How long it plays once, in milliseconds."""
        return float(sum(self.durations))

    def starts(self) -> list[float]:
        """When each entry starts, in milliseconds from the animation's start."""
        return [float(t) for t in np.cumsum([0] + list(self.durations[:-1]))]


@dataclass
class Sprite:
    """A sprite's frames, each in every direction, and the animations that play them.

    cells: [frame][direction] -> a cell (see the module's docstring), or None where not drawn.
    palette: (256, 3) uint8, the colors indices are shown in (player colors already swapped in).
    animations: the sequences that play the frames, in the order previews show them.
    labels: each direction's name in previews (default: its number).
    new_directions, new_frames: what glisomorph made, rather than the game's own; previews mark them.
    mirrors: directions drawn as another one's mirror image, {direction: the one it mirrors} (see mirrored()).
    scale: pixels per game pixel (4 for a 4x render).
    pivot: where the unit stands on the canvas, (x right, y down); default the canvas center, rounded
        down, which is where StarCraft puts it.
    original: the game's own frames this sprite was made from, as a Sprite (a comparison shows them).
    name: what to call it in file names and titles."""

    cells: list[list[np.ndarray | None]]
    palette: np.ndarray
    animations: list[Animation] = field(default_factory=list)
    labels: list[str] | None = None
    new_directions: set[int] = field(default_factory=set)
    new_frames: set[int] = field(default_factory=set)
    mirrors: dict[int, int] = field(default_factory=dict)
    scale: int = 1
    pivot: tuple[float, float] | None = None
    original: Sprite | None = None
    name: str = ""

    def __post_init__(self):
        self.palette = np.asarray(self.palette, np.uint8).reshape(-1, 3)
        shapes = {c.shape[:2] for frame in self.cells for c in frame if c is not None}
        if len(shapes) > 1:
            raise ValueError("a sprite's cells share one canvas; these have %s" % sorted(shapes))
        for a in self.animations:
            if any(not 0 <= f < len(self.cells) for f in a.frames):
                raise ValueError("animation %r plays frames the sprite doesn't have" % a.name)

    @property
    def directions(self) -> int:
        """How many directions the sprite is drawn in (frames drawn the same in every direction aside)."""
        return max(len(frame) for frame in self.cells)

    @property
    def canvas(self) -> tuple[int, int]:
        """(height, width) of every cell."""
        for frame in self.cells:
            for c in frame:
                if c is not None:
                    return c.shape[0], c.shape[1]
        raise ValueError("the sprite has no cells")

    @property
    def anchor(self) -> tuple[int, int]:
        """The pivot in whole pixels, (x, y): where the unit stands on the canvas."""
        if self.pivot is not None:
            return int(np.floor(self.pivot[0])), int(np.floor(self.pivot[1]))
        h, w = self.canvas
        return w // 2, h // 2

    def label(self, direction: int) -> str:
        return self.labels[direction] if self.labels else str(direction)

    def cell(self, frame: int, direction: int) -> np.ndarray | None:
        """Frame `frame` in `direction`: a frame drawn once is the same in every direction."""
        cells = self.cells[frame]
        return cells[0] if len(cells) == 1 else cells[direction]

    def animation(self, name: str) -> Animation:
        for a in self.animations:
            if a.name == name:
                return a
        raise KeyError("no animation %r in %s" % (name, self.name or "the sprite"))

    def rgba(self, cell: np.ndarray | None) -> np.ndarray | None:
        """A cell in color: (H, W, 4) uint8, alpha 0 where transparent."""
        if cell is None:
            return None
        if cell.ndim == 3:
            if cell.shape[2] == 4:
                return cell.astype(np.uint8)
            return np.concatenate([cell.astype(np.uint8), np.full(cell.shape[:2] + (1,), 255, np.uint8)], 2)
        out = np.zeros(cell.shape + (4,), np.uint8)
        solid = cell >= 0
        out[solid, :3] = self.palette[cell[solid]]
        out[solid, 3] = 255
        return out

    def mirrored(self) -> Sprite:
        """The sprite with the directions its game draws by mirroring added, as their mirror images: with n
        directions from one side of the turn to the other (StarCraft's 17, 0 to 16 of 32), directions n to
        2(n - 1) - 1 are n - 2 down to 1, flipped left to right about the pivot. The canvas is widened to
        sit evenly about the pivot first, so the mirror images fit on it. The original is mirrored too. For
        previews of a whole turn; the game's own files keep the n."""
        n = self.directions
        h, w = self.canvas
        ax = self.anchor[0]
        half = max(ax, w - ax)
        left, right = half - ax, half - (w - ax)

        def widened(c):  # transparent columns added, so the pivot is the middle column's left edge
            if c is None or (left == 0 and right == 0):
                return c
            pad = ((0, 0), (left, right)) + (((0, 0),) if c.ndim == 3 else ())
            return np.pad(c, pad, constant_values=0 if c.ndim == 3 else -1)

        total = 2 * (n - 1)
        cells = []
        for frame in self.cells:
            frame = [widened(c) for c in frame]
            if len(frame) == 1:
                cells.append(frame)
                continue
            flipped = [None if c is None else np.ascontiguousarray(c[:, ::-1]) for c in frame]
            cells.append(frame + [flipped[total - d] for d in range(n, total)])
        mirrors = dict(self.mirrors)
        mirrors.update({d: total - d for d in range(n, total)})
        labels = None if self.labels is None else list(self.labels) + [str(d) for d in range(n, total)]
        px, py = self.pivot if self.pivot is not None else (ax, h // 2)
        pivot = None if self.pivot is None and left == 0 else (px + left, py)
        return dataclasses.replace(self, cells=cells, labels=labels, mirrors=mirrors, pivot=pivot,
                                   new_directions=self.new_directions | {d for d in range(n, total)
                                                                          if total - d in self.new_directions},
                                   original=None if self.original is None else self.original.mirrored())


class Exporter(ABC):
    """Writes a sprite to files: a game format (a GRP, a CL2, an FRM) or a preview (a GIF, an APNG, a
    WebP). Options go to the constructor; export() is the same for every exporter."""

    suffixes: tuple[str, ...] = ()  # the file types it writes; the first is its default

    @abstractmethod
    def export(self, sprite: Sprite, path: str | Path) -> list[Path]:
        """Writes `sprite` at `path` and returns the files written. An exporter that writes one file
        writes it at `path`; one that writes several names them after `path` (see each)."""

    def check_suffix(self, path: str | Path) -> Path:
        """`path` as a Path, after checking this exporter writes its file type."""
        path = Path(path)
        if self.suffixes and path.suffix.lower() not in self.suffixes:
            raise ValueError("%s writes %s files, not %r" % (type(self).__name__, "/".join(self.suffixes),
                                                            path.suffix))
        return path
