"""Zoomed side-by-side of ground truth and prediction for some views of a fit.

    python -m poc.zoom out/arrow-alternate --mpq PATH/TO/DIABDAT.MPQ --views 1 3 5 --scale 8
"""

import argparse
from pathlib import Path

import numpy as np
from PIL import Image

from blizzard_common.mpq import MpqArchive
from diablo1.palette import load_pal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--mpq", required=True)
    ap.add_argument("--views", type=int, nargs="+", required=True)
    ap.add_argument("--scale", type=int, default=8)
    args = ap.parse_args()
    with MpqArchive(args.mpq) as mpq:
        pal = np.array(load_pal(mpq.read("levels/towndata/town.pal")), dtype=np.uint8)
    data = np.load(Path(args.run) / "views.npz")
    tiles = []
    for i in args.views:
        images = [data["gt%d" % i], data["pred%d" % i]]
        if "rep%d" % i in data:
            images.append(data["rep%d" % i])
        solid = np.any([img >= 0 for img in images], axis=0)
        ys, xs = np.nonzero(solid)
        y0, y1, x0, x1 = max(ys.min() - 3, 0), ys.max() + 4, max(xs.min() - 3, 0), xs.max() + 4
        row = []
        for img in images:
            crop = img[y0:y1, x0:x1]
            rgb = np.full(crop.shape + (3,), 48, dtype=np.uint8)
            rgb[crop >= 0] = pal[crop[crop >= 0]]
            row.append(rgb)
            row.append(np.full((crop.shape[0], 1, 3), 255, dtype=np.uint8))
        tiles.append(np.concatenate(row, 1))
    width = max(t.shape[1] for t in tiles)
    padded = [np.pad(t, ((0, 2), (0, width - t.shape[1]), (0, 0)), constant_values=255) for t in tiles]
    out = np.concatenate(padded, 0).repeat(args.scale, 0).repeat(args.scale, 1)
    path = Path(args.run) / ("zoom_%s.png" % "_".join(map(str, args.views)))
    Image.fromarray(out).save(path)
    print(path)


if __name__ == "__main__":
    main()
