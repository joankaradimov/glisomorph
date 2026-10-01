"""The sprites' edges: blends with the background they were rendered over.

Diablo's sprites were rendered over a dark blue-gray background, which was then keyed out. Their edge
pixels kept a share of it, in proportion to how little of the pixel the model covered: an outline
pixel is close to a blend of its inside neighbours' color and the background. One background color
explains them: solved over every outline pixel, it comes out (34, 37, 50) for the zombie's walk and
(29, 37, 57) for the warrior's, and it halves the outline pixels' color error (RMS 23 -> 10).

At the originals' size that blend is a soft one-pixel edge. Copied into larger cells, it becomes a
bluish rim around the sprite, so for rendering larger it's taken out first: edges_over_black redraws
the edges as if over black, keeping their falloff; clean_edges gives them a clean neighbour's color,
which leaves them too bright.
"""

import numpy as np

BACKGROUND = (34.0, 37.0, 50.0)  # 0-255, as the zombie's walk's outline pixels put it


def outline(solid: np.ndarray) -> np.ndarray:
    """Solid pixels (H, W bool) with a transparent 4-neighbour (or the image's edge)."""
    pad = np.pad(solid, 1)
    return solid & ~(pad[:-2, 1:-1] & pad[2:, 1:-1] & pad[1:-1, :-2] & pad[1:-1, 2:])


EDGE_COLORS = np.arange(128, 255)  # the indices sprites use, but 0: a black pixel on the edge would read as shadow


def edges_over_black(indices: np.ndarray, palette: np.ndarray, background=BACKGROUND,
                     max_residual: float = 15.0) -> np.ndarray:
    """The sprite (H, W palette indices, -1 transparent) as if it had been rendered over black: each
    outline pixel that is a blend of its solid neighbours' mean color (3 x 3) and the background (within
    max_residual, 0-255) loses the background's share, pixel - (1 - coverage) * background, and is
    snapped back to the palette (not to index 0, the shadows' black). The edges keep their falloff,
    darkening outward as the model covers less of the pixel, without the blue. A pixel the blend
    doesn't explain keeps its own color."""
    solid = indices >= 0
    pal = np.asarray(palette, dtype=np.float64) * 255
    bg = np.asarray(background, dtype=np.float64)
    rgb = pal[np.clip(indices, 0, 255)]
    out = indices.copy()
    for y, x in zip(*np.nonzero(outline(solid))):
        y0, y1, x0, x1 = max(y - 1, 0), y + 2, max(x - 1, 0), x + 2
        near = solid[y0:y1, x0:x1].copy()
        near[y - y0, x - x0] = False
        if not near.any():
            continue
        mean = rgb[y0:y1, x0:x1][near].mean(0)
        d = mean - bg
        cover = float(np.clip(((rgb[y, x] - bg) * d).sum() / max((d * d).sum(), 1e-6), 0, 1))
        if np.linalg.norm(rgb[y, x] - (cover * mean + (1 - cover) * bg)) < max_residual:
            color = np.clip(rgb[y, x] - (1 - cover) * bg, 0, 255)
            out[y, x] = EDGE_COLORS[((pal[EDGE_COLORS] - color) ** 2).sum(1).argmin()]
    return out


def clean_edges(indices: np.ndarray, palette: np.ndarray, background=BACKGROUND, max_cover: float = 0.85,
                max_residual: float = 15.0, passes: int = 3) -> np.ndarray:
    """The sprite (H, W palette indices, -1 transparent) with its edge pixels' share of the background
    taken out. palette (256, 3) is 0-1. An outline pixel that is a blend of its solid neighbours' mean
    color (3 x 3) and the background (within max_residual, 0-255) and shows the background (coverage
    under max_cover) takes the index of the clean neighbour nearest the clean neighbours' mean color.
    Clean pixels are those inside the outline, outline pixels showing little or none of the background,
    and, over a few passes, pixels already cleaned, so that thin parts are reached from their thicker
    ends. A pixel the blend doesn't explain keeps its own color."""
    solid = indices >= 0
    pal = np.asarray(palette, dtype=np.float64) * 255
    bg = np.asarray(background, dtype=np.float64)
    rgb = pal[np.clip(indices, 0, 255)]
    edge = outline(solid)
    clean = solid & ~edge
    out = indices.copy()
    todo = []
    for y, x in zip(*np.nonzero(edge)):
        y0, y1, x0, x1 = max(y - 1, 0), y + 2, max(x - 1, 0), x + 2
        near = solid[y0:y1, x0:x1].copy()
        near[y - y0, x - x0] = False
        if not near.any():
            continue
        mean = rgb[y0:y1, x0:x1][near].mean(0)
        d = mean - bg
        cover = float(np.clip(((rgb[y, x] - bg) * d).sum() / max((d * d).sum(), 1e-6), 0, 1))
        if cover >= max_cover or np.linalg.norm(rgb[y, x] - (cover * mean + (1 - cover) * bg)) >= max_residual:
            clean[y, x] = True  # its own color is the model's
        else:
            todo.append((y, x))
    for _ in range(passes):
        rest = []
        for y, x in todo:
            y0, y1, x0, x1 = max(y - 1, 0), y + 2, max(x - 1, 0), x + 2
            near = clean[y0:y1, x0:x1]
            if not near.any():
                rest.append((y, x))
                continue
            ids = out[y0:y1, x0:x1][near]
            cols = pal[ids]
            out[y, x] = ids[((cols - cols.mean(0)) ** 2).sum(1).argmin()]
        done = set(todo) - set(rest)
        for y, x in done:
            clean[y, x] = True
        todo = rest
    return out
