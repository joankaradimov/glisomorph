"""Diablo 1 palettes (PAL). See diablo1/docs/filespecs/pal.md."""

# Palette indices that sprites use: 0 (black, mostly shadow) and the shared range 128-254.
SPRITE_INDICES = [0] + list(range(128, 255))

# Shade ramps, as the light tables see them: (first index, length). Brightest first.
RAMPS = ([(i, 16) for i in range(0, 128, 16)] + [(i, 8) for i in range(128, 160, 8)]
         + [(i, 16) for i in range(160, 256, 16)])


def load_pal(data: bytes) -> list[tuple[int, int, int]]:
    """256 (r, g, b) entries."""
    if len(data) != 768:
        raise ValueError("a PAL file is 768 bytes, got %d" % len(data))
    return [tuple(data[3 * i:3 * i + 3]) for i in range(256)]


def ramp_of(index: int) -> int:
    """The number of the shade ramp an index belongs to."""
    for number, (start, length) in enumerate(RAMPS):
        if start <= index < start + length:
            return number
    raise ValueError(index)
