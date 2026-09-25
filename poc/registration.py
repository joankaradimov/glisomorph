"""Do a sprite's directions share one rotation axis? Checks per-direction pixel offsets.

For each direction in turn, shifts its image by up to 3 pixels and keeps the shift that lets a strict
visual hull (no slack) explain the silhouettes best. Offsets that settle away from zero mean the
directions weren't registered to a common axis.

    python -m poc.registration --mpq PATH/TO/DIABDAT.MPQ --preset warrior --elevation 26 --offset -1 -4
"""

import argparse
import math

import torch

from poc.field import VoxelField, allowed_masks, camera_basis, carve, silhouettes
from poc.fit import masks_for
from poc.views import PRESETS, load_views


def coverage(field, masks, views, right, up, offsets):
    allowed = allowed_masks(masks, slack=0)
    inside = torch.ones(field.voxel_centers().shape[:3], dtype=torch.bool, device=field.box_min.device)
    for k in range(len(views)):
        inside &= carve(field, [allowed[k]], [views[k]], right[k:k + 1], up[k:k + 1], offsets[k])
    covered = total = 0
    for k in range(len(views)):
        proj = silhouettes(inside, field, [views[k]], right[k:k + 1], up[k:k + 1], offsets[k])[0]
        solid = masks[k] == 1
        covered += int((proj & solid).sum())
        total += int(solid.sum())
    return covered / total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mpq", required=True)
    ap.add_argument("--preset", required=True)
    ap.add_argument("--elevation", type=float, required=True)
    ap.add_argument("--offset", type=float, nargs=2, required=True)
    ap.add_argument("--voxel", type=float, default=0.5)
    args = ap.parse_args()
    device = torch.device("cuda")
    preset = PRESETS[args.preset]
    views, _ = load_views(args.mpq, preset)
    masks = masks_for(views, preset.shadows, device)
    yaws = torch.tensor([v.yaw for v in views], device=device)
    right, up, _ = camera_basis(yaws, torch.tensor(math.radians(args.elevation), device=device))
    r = max(v.shape[1] for v in views) / 2 + 4
    field = VoxelField([-r, -40, -r], [r, 160, r], args.voxel, device)
    offsets = [tuple(args.offset)] * len(views)
    base = coverage(field, masks, views, right, up, offsets)
    print("strict coverage with one shared axis: %.3f" % base)
    for sweep in range(2):
        for k in range(len(views)):
            best = (coverage(field, masks, views, right, up, offsets), offsets[k])
            for dx in range(-3, 4):
                for dy in range(-3, 4):
                    trial = list(offsets)
                    trial[k] = (args.offset[0] + dx, args.offset[1] + dy)
                    c = coverage(field, masks, views, right, up, trial)
                    if c > best[0] + 1e-4:
                        best = (c, trial[k])
            offsets[k] = best[1]
        print("sweep %d: coverage %.3f, per-direction shifts %s" % (
            sweep, best[0], [(o[0] - args.offset[0], o[1] - args.offset[1]) for o in offsets]))


if __name__ == "__main__":
    main()
