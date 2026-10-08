"""Diablo 1 sprites as turntable views: one image per facing direction, each with its yaw.

The players' casting animations have their spell's effect drawn over them. Its pixels, from the
overlays in diablo1/overlays, grown by a pixel for the effect's blended edge, come with each view as
`ignore`: neither the model nor the background. A variant's three casts are one motion under three
effects: the "casts" layout cleans them into one, without the spells (casts.py)."""

import dataclasses
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from blizzard_common.mpq import MpqArchive
from diablo1.palette import load_pal
from diablo1.sprites import Frame, load_cl2

OVERLAYS = Path(__file__).resolve().parent.parent / "diablo1" / "overlays"
CASTS = ("fm", "lm", "qm")  # fire, lightning, magic


@dataclass
class View:
    yaw: float                   # degrees, clockwise seen from above; 0 faces the camera (south)
    indices: np.ndarray          # (H, W) int16 palette indices, -1 where transparent
    pivot: tuple[float, float]   # pixel position (x right, y down) of the rotation axis at the anchor
    ignore: np.ndarray | None = None  # (H, W) bool: what the view doesn't show (a spell's effect over it,
                                      # or all of it, where it was drawn wrong: MISDRAWN)

    @property
    def shape(self) -> tuple[int, int]:
        return self.indices.shape

    @property
    def unseen(self) -> bool:
        """Whether nothing of it is known: `ignore` everywhere (a direction drawn wrong: MISDRAWN)."""
        return self.ignore is not None and bool(self.ignore.all())


@dataclass
class Preset:
    path: str          # MPQ path; "{}" is replaced by 1..16 for missiles split over files
    width: int
    layout: str        # "sheet": 8 groups; "files": 16 files; "frames": 16 frames of one list
    frame: int = 0     # which animation frame to use
    shadows: bool = False  # index-0 pixels are baked shadows, not part of the model
    pivot: tuple[float, float] | None = None  # None: (width / 2, height - 16), a character's ground point


# Animations whose sprites were drawn about another pivot than their variant's stand, moved onto it as
# they're loaded (rows down, columns right, per direction S, SW, W, NW, N, NE, E, SE), so that a variant's
# animations share one camera. Each walk is drawn 3 pixels to the left in every direction: as drawn, its
# 8 views are no one shape (a visual hull covers 0.72 to 0.79 of them), moved, they are (1.00). Each axe
# attack is drawn up to 5 pixels aside, more the further it faces from S: moved, its frame 0 lies on the
# stand's frame 0 (0.94 of their silhouettes shared, against 0.63 and 0.72), as the attack starts from the
# stand, and its views are one shape again (0.95 to 1.00).
ONTO_STAND = {
    **{v + "/aw": [(0, 3)] * 8 for v in ("wln", "wlu", "wmn", "wmu", "whn", "whu")},
    "wla/at": [(0, 0), (0, 0), (-1, 3), (-1, 4), (0, 5), (1, 4), (1, 3), (1, 1)],
    "wma/at": [(0, 0), (-1, 1), (-1, 2), (-1, 3), (0, 4), (1, 3), (1, 2), (1, 1)],
}

# Directions drawn as another one (0 = S, 1 = SW, ... 7 = SE). wmh's stand facing SW is its W drawing
# again, in all 10 frames: their silhouettes share 0.993 to 0.999, and 0.96 of their pixels the same
# index, where every other variant's SW and W share about half their silhouettes. Such a view comes with
# `ignore` everywhere, nothing of it known, for the model to fill: without it, the stand's views are one
# shape again (a visual hull covers 0.997 of them, against 0.886 with it).
MISDRAWN = {"wmh/as": [1]}


def sheet_key(path: str) -> str | None:
    """A player's sprite as "<variant>/<animation>" (plrgfx/warrior/wmh/wmhas.cl2: "wmh/as"), the key of
    ONTO_STAND and MISDRAWN, or None."""
    m = re.fullmatch(r"plrgfx/\w+/(\w{3})/\1(\w+)\.cl2", path.replace("\\", "/").lower())
    return "%s/%s" % m.groups() if m else None


class Presets(dict):
    """The presets by name. A player's animation also comes for any other variant of its class, as
    "<name>@<variant>" (plrgfx/<class>/<variant>/<variant>..., e.g. warrior-stand@wla, the warrior in
    light armor with an axe), its width as that variant's (a warrior's bow attack is narrower: see
    diablo1/docs/filespecs/sprite-metadata.md)."""

    def __missing__(self, key):
        name, at, variant = key.partition("@")
        m = re.fullmatch(r"(plrgfx/\w+/)(\w{3})/\2(.*)", dict.get(self, name, Preset("", 0, "")).path)
        if not at or not m or not re.fullmatch(r"[a-z]{3}", variant):
            raise KeyError(key)
        preset = dict.__getitem__(self, name)
        bow = m.group(1) == "plrgfx/warrior/" and variant[2] == "b" and m.group(3).startswith("at")
        return dataclasses.replace(preset, path="%s%s/%s%s" % (m.group(1), variant, variant, m.group(3)),
                                   width=96 if bow else preset.width)

    def __contains__(self, key):  # so that argparse takes "<name>@<variant>" among its choices
        try:
            return self[key] is not None
        except KeyError:
            return False


PRESETS = Presets({
    "arrow":Preset("missiles/arrows.cl2", 96, "frames", pivot=(46.5, 36.0)),
    "farrow": Preset("missiles/farrow{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "larrow": Preset("missiles/larrow{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "fireba": Preset("missiles/fireba{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "holy": Preset("missiles/holy{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "warrior": Preset("plrgfx/warrior/wls/wlsas.cl2", 96, "sheet", shadows=True),
    "warrior-stand": Preset("plrgfx/warrior/wls/wlsas.cl2", 96, "sheet", shadows=True),  # 10 frames
    "warrior-walk": Preset("plrgfx/warrior/wls/wlsaw.cl2", 96, "sheet", shadows=True),  # 8 frames
    "warrior-attack": Preset("plrgfx/warrior/wls/wlsat.cl2", 128, "sheet", shadows=True),  # 16 frames
    "warrior-hit": Preset("plrgfx/warrior/wls/wlsht.cl2", 96, "sheet", shadows=True),  # 6 frames
    # In town the game draws these instead of the stand and walk
    "warrior-town-stand": Preset("plrgfx/warrior/wls/wlsst.cl2", 96, "sheet", shadows=True),  # 20 frames
    "warrior-town-walk": Preset("plrgfx/warrior/wls/wlswl.cl2", 96, "sheet", shadows=True),  # 8 frames
    # Casting, 20 frames each, a spell's effect drawn over them (diablo1/overlays), and the three cleaned
    # into one, without the spells (casts.py)
    "warrior-fire": Preset("plrgfx/warrior/wls/wlsfm.cl2", 96, "sheet", shadows=True),
    "warrior-lightning": Preset("plrgfx/warrior/wls/wlslm.cl2", 96, "sheet", shadows=True),
    "warrior-magic": Preset("plrgfx/warrior/wls/wlsqm.cl2", 96, "sheet", shadows=True),
    "warrior-cast": Preset("plrgfx/warrior/wls/wls{}.cl2", 96, "casts", shadows=True),
    "rogue": Preset("plrgfx/rogue/rls/rlsas.cl2", 96, "sheet", shadows=True),
    "zombie": Preset("monsters/zombie/zombien.cl2", 128, "sheet", shadows=True),
    "zombie-walk": Preset("monsters/zombie/zombiew.cl2", 128, "sheet", shadows=True),  # 24 frames
    "zombie-attack": Preset("monsters/zombie/zombiea.cl2", 128, "sheet", shadows=True),  # 12 frames
    "skeleton": Preset("monsters/skelaxe/sklaxn.cl2", 128, "sheet", shadows=True),
})


def _frame_to_array(frame: Frame) -> np.ndarray:
    return np.array([-1 if p is None else p for p in frame.pixels], dtype=np.int16).reshape(
        frame.height, frame.width)


def frame_count(mpq_path: str, preset: Preset) -> int:
    """How many animation frames the preset's sprite has (1 for missiles stored as one frame per
    direction)."""
    if preset.layout == "frames":
        return 1
    with MpqArchive(mpq_path) as mpq:
        path = {"sheet": preset.path, "casts": preset.path.format(CASTS[0])}.get(preset.layout, preset.path.format(1))
        return len(load_cl2(mpq.read(path), preset.width)[0])


def load_views(mpq_path: str, preset: Preset, grown: bool = True) -> tuple[list[View], np.ndarray]:
    """The views, in increasing yaw, and the palette (256, 3) as floats in [0, 1]. A spell's effect is
    grown by a pixel in `ignore`, unless not `grown`."""
    if preset.layout == "casts":
        from poc.casts import clean_casts  # casts.py loads its casts through this module
        return clean_casts(mpq_path, preset)
    with MpqArchive(mpq_path) as mpq:
        palette = np.array(load_pal(mpq.read("levels/towndata/town.pal")), dtype=np.float32) / 255
        if preset.layout == "sheet":
            groups = load_cl2(mpq.read(preset.path), preset.width)
            frames = [g[preset.frame] for g in groups]
        elif preset.layout == "files":
            frames = [load_cl2(mpq.read(preset.path.format(k)), preset.width)[0][preset.frame]
                      for k in range(1, 17)]
        else:
            frames = load_cl2(mpq.read(preset.path), preset.width)[0]
    step = 360 / len(frames)
    overlay = spell_overlay(preset.path, preset.width) if preset.layout == "sheet" else None
    key = sheet_key(preset.path) if preset.layout == "sheet" else None
    moves, misdrawn = ONTO_STAND.get(key), MISDRAWN.get(key, [])
    views = []
    for i, frame in enumerate(frames):
        pivot = preset.pivot or (frame.width / 2, frame.height - 16)
        indices = _frame_to_array(frame)
        ignore = None
        if overlay is not None:
            group = overlay[i if len(overlay) == len(frames) else 0]
            if preset.frame < len(group):
                drawn = _frame_to_array(group[preset.frame]) >= 0
                ignore = np.zeros(indices.shape, dtype=bool)
                rows = min(drawn.shape[0], indices.shape[0])  # both drawn from their bottom-left corner
                ignore[-rows:] = drawn[-rows:]
                if grown:
                    ignore = _grown(ignore)
        if moves is not None:  # drawn about another pivot than the stand's (ONTO_STAND)
            indices = _shifted(indices, *moves[i], -1)
            ignore = None if ignore is None else _shifted(ignore, *moves[i], False)
        if i in misdrawn:  # drawn as another direction (MISDRAWN)
            ignore = np.ones(indices.shape, dtype=bool)
        views.append(View(yaw=i * step, indices=indices, pivot=pivot, ignore=ignore))
    return views, palette


def _shifted(a: np.ndarray, dy: int, dx: int, fill) -> np.ndarray:
    """a (..., H, W) moved by dy rows down and dx columns right, `fill` where nothing moved in."""
    out = np.full_like(a, fill)
    h, w = a.shape[-2:]
    rows, cols = slice(max(dy, 0), h + min(dy, 0)), slice(max(dx, 0), w + min(dx, 0))
    out[..., rows, cols] = a[..., max(-dy, 0):h + min(-dy, 0), max(-dx, 0):w + min(-dx, 0)]
    return out


def _grown(mask: np.ndarray) -> np.ndarray:
    """A bool mask (..., H, W) grown by a pixel, diagonals included."""
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= _shifted(mask, dy, dx, False)
    return out


def spell_overlay(path: str, width: int) -> list[list[Frame]] | None:
    """The spell's effect drawn over a player's casting sprite (plrgfx/<class>/<v>/<v>{fm,lm,qm}.cl2), as
    diablo1/overlays has it: one group for every direction, or 8. None for other sprites, and for the five
    casts without an overlay (see diablo1/overlays/README.md)."""
    m = re.fullmatch(r"plrgfx/\w+/(\w{3})/\1(fm|lm|qm)\.cl2", path.replace("\\", "/").lower())
    if not m or not (OVERLAYS / "overlays.tsv").exists():
        return None
    for line in (OVERLAYS / "overlays.tsv").read_text().splitlines()[1:]:
        _, variant, cast, overlay = line.split("\t")[:4]
        if (variant, cast) == m.groups():
            return load_cl2((OVERLAYS / overlay).read_bytes(), width) if overlay else None
    return None
