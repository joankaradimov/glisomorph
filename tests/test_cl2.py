"""Diablo's CL2 exporter, on synthetic sprites (never game data).

    python -m unittest discover tests
"""

import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np

from common.export import Sprite
from diablo1.export.cl2 import Cl2Exporter, encode_frame, header_rows
from diablo1.sprites import decode_cl2_frame, split_frames
from test_export import PALETTE

W, H = 64, 140  # tall enough for every row the header points to (32, 64, 96 and 128)


def commands(raw: bytes) -> list[tuple[str, int]]:
    """A frame's commands as (kind, pixels)."""
    out, pos = [], 10
    while pos < len(raw):
        c = raw[pos]
        if c < 0x80:
            out.append(("skip", c))
            pos += 1
        elif c < 0xBF:
            out.append(("fill", 0xBF - c))
            pos += 2
        else:
            out.append(("literal", 256 - c))
            pos += 1 + 256 - c
    return out


def decoded(raw: bytes, width: int = W) -> np.ndarray:
    frame = decode_cl2_frame(raw, width)
    return np.array([-1 if p is None else p for p in frame.pixels], np.int16).reshape(frame.height, width)


def unit(direction: int, step: int) -> np.ndarray:
    """A cell with a post on the ground and an arm turned toward `direction` of 8, longer with `step`."""
    cell = np.full((H, W), -1, np.int16)
    x, y = W // 2, H - 16
    cell[y - 40:y + 1, x - 2:x + 3] = 130 + direction
    angle = np.pi * direction / 4
    for r in range(6 + 3 * step):
        cell[y - 30 - int(round(r * np.cos(angle))), x + int(round(r * np.sin(angle)))] = 200 + r % 7
    return cell


def walker(steps=3, directions=8) -> Sprite:
    cells = [[unit(d, s) for d in range(directions)] for s in range(steps)]
    return Sprite(cells, PALETTE, pivot=(W / 2, H - 16))


class Cl2(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def test_sheet_round_trip(self):
        sprite = walker()
        once = np.full((H, W), -1, np.int16)
        once[H - 20:H - 10, 5:60] = 140  # a frame drawn once, the same in every direction
        sprite.cells.append([once])
        path = Cl2Exporter().export(sprite, self.dir / "wlsas.cl2")[0]
        data = path.read_bytes()
        groups = split_frames(data)
        self.assertEqual([len(g) for g in groups], [4] * 8)
        np.testing.assert_array_equal(decoded(groups[5][2]), sprite.cells[2][5])
        np.testing.assert_array_equal(decoded(groups[3][3]), once)
        # as the game lays sheets out: the table, every list's count and offsets, then all the frames
        table = struct.unpack_from("<8I", data)
        self.assertEqual(list(table), [32 + 24 * g for g in range(8)])
        self.assertEqual(table[0] + struct.unpack_from("<I", data, table[0] + 4)[0], 32 + 8 * 24)

    def test_long_runs(self):
        cell = np.full((2, W), -1, np.int16)
        cell[1, :63] = 5  # 63 of one index: a fill of 62, and the one left goes on as a literal
        cell[1, 63] = 6
        cell[0, :] = 9  # 64 of one index: two fills
        self.assertEqual(commands(encode_frame(cell)), [("fill", 62), ("literal", 2), ("fill", 62), ("literal", 2)])
        cell[0, :] = np.arange(W)  # 64 different: one literal
        cell[0, 60:] = 3
        self.assertEqual(commands(encode_frame(cell))[2:], [("literal", 60), ("fill", 4)])

    def test_runs_across_rows(self):
        cell = np.full((2, W), -1, np.int16)
        cell[1, W - 4:] = [1, 2, 3, 8]  # a run of 8s from the bottom row's last pixel into the next row's
        cell[0, :2] = 8
        cell[0, 2:5] = [4, 5, 6]
        self.assertEqual(commands(encode_frame(cell)), [("skip", W - 4), ("literal", 3), ("fill", 1), ("literal", 5),
                                                         ("skip", W - 5)])
        cell[0, 2] = 8  # four: one at the row's end, three after it
        self.assertEqual(commands(encode_frame(cell))[2:5], [("fill", 1), ("fill", 3), ("literal", 2)])

    def test_runs(self):
        rng = np.random.default_rng(0)
        cell = np.full((H, W), -1, np.int16)
        cell[H - 1, :] = 7  # a fill longer than a fill command holds (63)
        cell[H - 2, :] = rng.integers(0, 256, W)  # literals longer than a literal holds (65)
        cell[H - 3, 1:4] = 9  # a fill of three, between literals
        cell[H - 3, 4:6] = [1, 2]
        cell[H - 120:H - 33, 10] = 3  # skips that run on over rows, and up to row 128
        cell[0, W - 1] = 250  # the top row, at its right edge
        raw = encode_frame(cell)
        np.testing.assert_array_equal(decoded(raw), cell)
        self.assertEqual(list(struct.unpack_from("<4H", raw, 2)), header_rows(raw, W))
        self.assertTrue(all(header_rows(raw, W)))  # every one of the four rows exists, and is pointed at

    def test_header_rows(self):
        cell = np.full((40, W), -1, np.int16)
        cell[39, 0] = 1  # then a skip that would run from row 0 into row 32 if it could
        cell[0, 0] = 1
        raw = encode_frame(cell)
        rows = header_rows(raw, W)
        self.assertNotEqual(rows[0], 0)
        self.assertEqual(rows[1:], [0, 0, 0])  # a 40-row frame has no row 64, 96 or 128
        self.assertEqual(raw[rows[0]], 0x7F)  # row 32 starts with a skip of its own
        np.testing.assert_array_equal(decoded(raw), cell)
        joined = raw[:10] + bytes([0x7F] * 17)  # 17 skips of 127 run from row 0 into row 32 (pixel 2048)
        with self.assertRaises(ValueError):
            header_rows(joined, W)

    def test_list_and_split(self):
        missile = Sprite([[unit(0, s)] for s in range(5)], PALETTE)
        path = Cl2Exporter(directions=1, ground=None).export(missile, self.dir / "arrows.cl2")[0]
        data = path.read_bytes()
        self.assertEqual(struct.unpack_from("<I", data)[0], 5)  # a frame list: its count first
        self.assertEqual([len(g) for g in split_frames(data)], [5])
        fireball = walker(steps=2, directions=16)
        fireball.pivot = None
        paths = Cl2Exporter(directions=16, ground=None, split=True).export(fireball, self.dir / "fireba.cl2")
        self.assertEqual([p.name for p in paths], ["fireba%d.cl2" % k for k in range(1, 17)])
        np.testing.assert_array_equal(decoded(split_frames(paths[10].read_bytes())[0][1]), fireball.cells[1][10])

    def test_refuses_what_a_cl2_cant_hold(self):
        with self.assertRaises(ValueError):  # 16 directions, where the game draws 8
            Cl2Exporter().export(walker(directions=16), self.dir / "a.cl2")
        with self.assertRaises(ValueError):  # colors, not indices
            sprite = walker()
            sprite.cells[0][0] = sprite.rgba(sprite.cells[0][0])
            Cl2Exporter().export(sprite, self.dir / "b.cl2")
        with self.assertRaises(ValueError):  # the unit at the canvas's center, not on the ground
            sprite = walker()
            sprite.pivot = None
            Cl2Exporter().export(sprite, self.dir / "c.cl2")
        with self.assertRaises(ValueError):  # a 2x render
            sprite = walker()
            sprite.scale = 2
            Cl2Exporter().export(sprite, self.dir / "d.cl2")
        with self.assertRaises(ValueError):  # a direction missing
            sprite = walker()
            sprite.cells[1][3] = None
            Cl2Exporter().export(sprite, self.dir / "e.cl2")


if __name__ == "__main__":
    unittest.main()
