"""Diablo 1 sprites as turntable views: one image per facing direction, each with its yaw."""

from dataclasses import dataclass

import numpy as np

from blizzard_common.mpq import MpqArchive
from diablo1.palette import load_pal
from diablo1.sprites import Frame, load_cl2, _u32


@dataclass
class View:
    yaw: float                   # degrees, clockwise seen from above; 0 faces the camera (south)
    indices: np.ndarray          # (H, W) int16 palette indices, -1 where transparent
    pivot: tuple[float, float]   # pixel position (x right, y down) of the rotation axis at the anchor

    @property
    def shape(self) -> tuple[int, int]:
        return self.indices.shape


@dataclass
class Preset:
    path: str          # MPQ path; "{}" is replaced by 1..16 for missiles split over files
    width: int
    layout: str        # "sheet": 8 groups; "files": 16 files; "frames": 16 frames of one list
    frame: int = 0     # which animation frame to use
    shadows: bool = False  # index-0 pixels are baked shadows, not part of the model
    pivot: tuple[float, float] | None = None  # None: (width / 2, height - 16), a character's ground point


PRESETS = {
    "arrow": Preset("missiles/arrows.cl2", 96, "frames", pivot=(46.5, 36.0)),
    "farrow": Preset("missiles/farrow{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "larrow": Preset("missiles/larrow{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "fireba": Preset("missiles/fireba{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "holy": Preset("missiles/holy{}.cl2", 96, "files", pivot=(46.5, 36.0)),
    "warrior": Preset("plrgfx/warrior/wls/wlsas.cl2", 96, "sheet", shadows=True),
    "warrior-stand": Preset("plrgfx/warrior/wls/wlsas.cl2", 96, "sheet", shadows=True),  # 10 frames
    "warrior-walk": Preset("plrgfx/warrior/wls/wlsaw.cl2", 96, "sheet", shadows=True),  # 8 frames
    "warrior-attack": Preset("plrgfx/warrior/wls/wlsat.cl2", 128, "sheet", shadows=True),  # 16 frames
    "warrior-hit": Preset("plrgfx/warrior/wls/wlsht.cl2", 96, "sheet", shadows=True),  # 6 frames
    "rogue": Preset("plrgfx/rogue/rls/rlsas.cl2", 96, "sheet", shadows=True),
    "zombie": Preset("monsters/zombie/zombien.cl2", 128, "sheet", shadows=True),
    "zombie-walk": Preset("monsters/zombie/zombiew.cl2", 128, "sheet", shadows=True),  # 24 frames
    "zombie-attack": Preset("monsters/zombie/zombiea.cl2", 128, "sheet", shadows=True),  # 12 frames
    "skeleton": Preset("monsters/skelaxe/sklaxn.cl2", 128, "sheet", shadows=True),
}


def _frame_to_array(frame: Frame) -> np.ndarray:
    return np.array([-1 if p is None else p for p in frame.pixels], dtype=np.int16).reshape(
        frame.height, frame.width)


def _groupped_cel(data: bytes) -> bool:
    fileSize = len(data)
    # CEL HEADER CHECKS
    # Read first DWORD
    if (fileSize < 4):
        return false

    firstDword = _u32(data, 0);

    # Trying to find file size in CEL header
    if (fileSize < (4 + firstDword * 4 + 4)):
        return false

    fileSizeDword = _u32(data, 4 + firstDword * 4)

    # If the dword is not equal to the file size then
    # try to read it as a groupped CEL
    return (firstDword != 0 and fileSize != fileSizeDword)


def frame_count(mpq_path: str, preset: Preset) -> int:
    """How many animation frames the preset's sprite has (1 for missiles stored as one frame per
    direction)."""
    with MpqArchive(mpq_path) as mpq:
        data = mpq.read(preset.path.format(1))
        if not _groupped_cel(data) and preset.path.find("{}") == -1:
            # frames layout
            return 1
        # read sheet or files layout
        return len(load_cl2(data, preset.width)[0])


def load_views(mpq_path: str, preset: Preset) -> tuple[list[View], np.ndarray]:
    """The views, in increasing yaw, and the palette (256, 3) as floats in [0, 1]."""
    with MpqArchive(mpq_path) as mpq:
        palette = np.array(load_pal(mpq.read("levels/towndata/town.pal")), dtype=np.float32) / 255

        if preset.path.find("{}") != -1:
            # read files layout
            frames = []
            for k in range(1, 17):
                data = mpq.read(preset.path.format(k))
                frames.append(load_cl2(data, preset.width)[0][preset.frame])
        else:
            data = mpq.read(preset.path)
            if _groupped_cel(data):
                # read sheet layout
                groups = load_cl2(data, preset.width)
                frames = [g[preset.frame] for g in groups]
            else:
                # read frames layout
                frames = load_cl2(data, preset.width)[0]
    step = 360 / len(frames)
    views = []
    for i, frame in enumerate(frames):
        pivot = preset.pivot or (frame.width / 2, frame.height - 16)
        views.append(View(yaw=i * step, indices=_frame_to_array(frame), pivot=pivot))
    return views, palette
