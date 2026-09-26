"""Where does a held-out direction's error come from? Splits it into shape, placement, hue and shade.

    python -m poc.diagnose out/warrior-holdout1-h0-rep 1
"""

import argparse
from pathlib import Path

import numpy as np
import torch

from diablo1.palette import RAMPS
from poc.shadow import baked_shadow

RAMP_OF = np.zeros(256, dtype=np.int64)
STEP_OF = np.zeros(256, dtype=np.int64)
for number, (start, length) in enumerate(RAMPS):
    RAMP_OF[start:start + length] = number
    STEP_OF[start:start + length] = np.arange(length)


def neighbours(img: np.ndarray, radius: int):
    """All shifts of img by up to `radius` pixels, with -1 shifted in."""
    out = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            shifted = np.full_like(img, -1)
            ys = slice(max(dy, 0), img.shape[0] + min(dy, 0))
            yd = slice(max(-dy, 0), img.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), img.shape[1] + min(dx, 0))
            xd = slice(max(-dx, 0), img.shape[1] + min(-dx, 0))
            shifted[yd, xd] = img[ys, xs]
            out.append(shifted)
    return np.stack(out)


def report(gt: np.ndarray, pred: np.ndarray, label: str) -> None:
    both = (gt >= 0) & (pred >= 0)
    g, p = gt[both], pred[both]
    same_ramp = RAMP_OF[g] == RAMP_OF[p]
    exact = g == p
    shade_err = np.abs(STEP_OF[g] - STEP_OF[p])[same_ramp & ~exact]
    near = neighbours(pred, 1)[:, both]                    # predictions within 1 pixel of each gt pixel
    exact_1px = (near == g).any(0)
    ramp_1px = (RAMP_OF[np.clip(near, 0, 255)] == RAMP_OF[g]).any(0) & (near >= 0).any(0)
    n = both.sum()
    print("%-9s exact %4.0f%%  | same ramp, wrong shade %4.0f%% (off by 1 shade: %3.0f%%, 2: %3.0f%%, 3+: %3.0f%%)"
          "  | wrong ramp %4.0f%%  || within 1 px: exact %4.0f%%, same ramp %4.0f%%" % (
              label, 100 * exact.mean(), 100 * (same_ramp & ~exact).mean(),
              100 * (shade_err == 1).sum() / max(n, 1), 100 * (shade_err == 2).sum() / max(n, 1),
              100 * (shade_err >= 3).sum() / max(n, 1), 100 * (~same_ramp).mean(),
              100 * exact_1px.mean(), 100 * ramp_1px.mean()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("view", type=int)
    args = ap.parse_args()
    data = np.load(Path(args.run) / "views.npz")
    gt = data["gt%d" % args.view].astype(np.int64)
    gt[baked_shadow(torch.as_tensor(gt)).numpy()] = -1  # baked shadows aren't part of the model
    print(Path(args.run).name)
    for key, label in (("pred", "field"), ("rep", "reproj"), ("relit", "relit")):
        name = "%s%d" % (key, args.view)
        if name in data:
            report(gt, data[name].astype(np.int64), label)


if __name__ == "__main__":
    main()
