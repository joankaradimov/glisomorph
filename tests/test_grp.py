"""StarCraft's GRP reader and exporter, on synthetic sprites (never game data).

    python -m unittest discover tests
"""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from common.export import Sprite
from starcraft.export.grp import GrpExporter, encode
from starcraft.grp import read
from test_export import PALETTE, bar, turning


class Grp(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_round_trip(self):
        rng = np.random.default_rng(0)
        sprite = turning()
        noisy = np.full((32, 32), -1, np.int16)
        noisy[2:30, 1:31] = rng.integers(0, 256, (28, 30))
        noisy[10, :] = 7  # a run longer than one repeat run holds
        noisy[12, :] = -1
        sprite.cells.append([noisy])  # a frame drawn once
        sprite.cells.append([np.full((32, 32), -1, np.int16)])  # an empty one
        path = GrpExporter().export(sprite, self.dir / "unit.grp")[0]
        grp = read(path.read_bytes())
        self.assertEqual((grp.width, grp.height, len(grp.frames)), (32, 32, 4 * 17 + 2))
        np.testing.assert_array_equal(grp.frames[17 * 2 + 5], sprite.cells[2][5])
        np.testing.assert_array_equal(grp.frames[-2], noisy)

    def test_identical_frames_share_data(self):
        cell = bar(3, 17, 8)
        data = encode(32, 32, [cell, cell, bar(4, 17, 8)])
        offsets = [int.from_bytes(data[6 + 8 * f + 4:6 + 8 * f + 8], "little") for f in range(3)]
        self.assertEqual(offsets[0], offsets[1])
        self.assertNotEqual(offsets[0], offsets[2])

    def test_refuses_what_a_grp_cant_hold(self):
        sprite = turning()
        with self.assertRaises(ValueError):  # 8 directions
            GrpExporter().export(turning(directions=8), self.dir / "a.grp")
        with self.assertRaises(ValueError):  # colors, not indices
            sprite.cells[0][0] = sprite.rgba(sprite.cells[0][0])
            GrpExporter().export(sprite, self.dir / "b.grp")
        with self.assertRaises(ValueError):  # the unit off the canvas's center
            off = turning()
            off.pivot = (10, 10)
            GrpExporter().export(off, self.dir / "c.grp")
        with self.assertRaises(ValueError):  # a box past 255 pixels
            wide = np.full((8, 300), -1, np.int16)
            wide[4, 280] = 1
            GrpExporter().export(Sprite([[wide]], PALETTE), self.dir / "d.grp")


if __name__ == "__main__":
    unittest.main()
