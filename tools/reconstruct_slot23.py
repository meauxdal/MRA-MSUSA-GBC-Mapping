"""Reconstruct MSUSA extra slot 23 as a conjectural "unfinished arena".

Slot 23's own graphics render as scrambled terrain. Its cell grid and terrain
codes look like an early version of the City Arena (slot 24) with a different
layout, so this tool redraws it with the City Arena's metatiles and graphics.
The result is a conjecture, not a ROM recovery. The steps are:

  1. solve:  map each slot 23 cell ID to a City Arena ID with the same terrain
             template, choosing among candidates by how well neighbours join.
  2. quilt:  for each cell, choose between that remapped ID and a City Arena
             cell copied at one of a few fixed offsets, so that whole runs of
             real city scenery are reused. Road-coded cells must keep the
             remapped ID.
  3. patch:  a hand-made list of fixes, each taken from City Arena cells, for
             the seams the first two steps leave.

Writes the PNG named in data/msusa_extras.json (slot 23 "reconstruction").
--debug DIR also writes the cell grid (.npy), a labelled grid render and a
terrain-boundary overlay for checking patches. --city-grid FILE writes the City
Arena with row,col labels, for picking the source cells of new patches.
"""
import argparse
import collections
import json
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw
from maps import ROOT, read_rom, courses, render_tiles
from terrain import cell_ids, template, terrain_map

# Cost of a neighbour pair never seen in the City Arena, on top of the mean
# edge pixel difference (0-1). Both search steps use it.
PRIOR = 0.5

# Quilt step: offsets (dx, dy) at which City Arena cells may be copied.
OFFSETS = [(3, -2), (3, -1), (3, -4), (0, -3), (1, -3), (5, -3), (4, -3),
           (2, -3), (3, 0), (3, 1), (3, 2), (1, 0), (5, 0), (1, 1), (5, 1),
           (13, -6), (-7, -6), (11, -5), (-5, -5), (-1, -3), (11, -7),
           (-5, -7), (1, -2), (5, -2), (7, -3)]
REMAP = "remap"

# Patch step: (row, col, source), where source is a City Arena cell ID or
# ("city", r, c) to copy City Arena cell (r, c).
WATER = 232  # city (25, 5)
PATCHES = []

# Waterfront runs in 2-column strips, top to bottom: kerb, shore (bollards),
# steps, water.
#   left (/ shore):  16/18, 224/226 (or 224/814), 240/242, water
#   right (\ shore): 20/22, 228/230 (or 776/230), 244/246, water
# The five road-coded 2x2 "islands" at (18,3) (20,8) (22,12) (21,24) (18,30)
# are not islands: each is a strip's steps cell plus the water below. Slot 23
# codes those steps as road, so the quilt filled them with building corners.
PATCHES += [
    # Left steps
    (18, 3, WATER), (18, 4, 240), (19, 3, WATER), (19, 4, WATER),
    (20, 8, 240), (20, 9, 242), (21, 8, WATER), (21, 9, WATER),
    (22, 12, 240), (22, 13, 242), (23, 12, WATER), (23, 13, WATER),
    # Right steps
    (21, 24, 244), (21, 25, 246), (22, 24, WATER), (22, 25, WATER),
    (18, 30, 244), (18, 31, 246), (19, 30, WATER), (19, 31, WATER),
    # Right seam, strip cols 26-27: was 844/106, 134/106 (manhole slab),
    # 656/106, 246/232
    (19, 26, 228), (19, 27, 230), (20, 26, 244), (20, 27, 246),
    (21, 26, WATER), (21, 27, WATER), (22, 26, WATER), (22, 27, WATER),
    # Strip cols 30-31 shore row: green park fragment 744/748
    (17, 30, 228), (17, 31, 230),
]

# The four inner planters are 2x4-cell diamonds (top-left corners below). Each
# is the city grass planter's left corner (744/748 over 742/734) next to its
# right corner (750/764 over 732/758), without the city's wider middle. The
# kerb above the peak is plain 16/18, not the pit's 644/646.
for r, c in [(12, 16), (15, 10), (15, 22), (18, 16)]:
    PATCHES += [(r, c, 744), (r, c+1, 748), (r, c+2, 750), (r, c+3, 764),
                (r+1, c, 742), (r+1, c+1, 734), (r+1, c+2, 732),
                (r+1, c+3, 758), (r-1, c+2, 16), (r-1, c+3, 18),
                (r+1, c+5, 6)]

# Road kerb next to the shore: the quilt used the building kerbs 16/18 (left)
# and 20/22 (right), which leaves dark sidewalk wedges. The city uses 376/64
# and 66/374 there.
for r, c in [(16, 4), (17, 6), (18, 8), (19, 10), (20, 12)]:
    PATCHES += [(r, c, 376), (r, c+1, 64)]
for r, c in [(16, 30), (17, 28), (18, 26), (19, 24), (20, 22)]:
    PATCHES += [(r, c, 66), (r, c+1, 374)]
# Shore corners, as city (13, 2-3) and (13, 34-35).
PATCHES += [(15, 2, 376), (15, 3, 64), (15, 33, 374)]

# Bottom tip, modelled on the city tip (city rows 20-22): the shores meet one
# row lower than the quilt had them.
PATCHES += [
    (20, 14, 48), (20, 15, 48), (20, 20, 48), (20, 21, 48),
    (21, 14, 376), (21, 15, 64), (21, 16, 48), (21, 17, 48),
    (21, 18, 48), (21, 19, 48), (21, 20, 66), (21, 21, 374),
    (22, 14, 224), (22, 15, 226), (22, 16, 376), (22, 17, 64),
    (22, 18, 66), (22, 19, 374), (22, 20, 228), (22, 21, 230),
    (23, 14, 240), (23, 15, 242), (23, 16, 224), (23, 17, 226),
    (23, 18, 228), (23, 19, 230), (23, 20, 244), (23, 21, 246),
    (24, 16, 240), (24, 17, 242), (24, 18, 244), (24, 19, 246),
]

# Top road edges: the quilt put pit kerb 678 (left edge) and 106 (right edge)
# where the building meets the kerb, which shows as dark stair blocks. Use
# the cell the city has between the same two neighbours.
PATCHES += [
    (6, 15, 196), (7, 13, 120), (8, 11, 426), (9, 9, 438), (10, 7, 426),
    (11, 5, 486), (10, 35, 544), (11, 33, 606),
    (6, 20, 122), (7, 22, 300), (8, 24, 300), (9, 26, 364), (10, 28, 122),
    (11, 30, 570), (11, 2, 122),
]

# White kerb stubs: 64 holds the start of a line that continues into 0 on its
# right, and 66 the end of a line coming from 6 on its left. Where no line
# follows, they leave a dash on bare road, so use plain road 48. The tip at
# (22, 17-18) keeps its 64/66, as in the city.
PATCHES += [(r, c, 48) for r, c in [
    (13, 3), (13, 4), (13, 31), (13, 32), (15, 17), (15, 18), (18, 11),
    (18, 12), (18, 23),
    (15, 3), (16, 5), (17, 7), (18, 9), (19, 11), (20, 13), (21, 15),
    (16, 30), (17, 28), (18, 26), (19, 24), (20, 22), (21, 20)]]

# Top centre: rows 2-6, cols 11-22 match the city's brown building at
# slot = city + (2, -3), except a five-cell "alley" the quilt filled with
# sidewalk and a manhole. Slot 23 road-codes those cells; the city road-codes
# only the two at the building's foot (214/194), so take the city cells.
PATCHES += [(5, 17, ("city", 3, 20)), (5, 18, ("city", 3, 21)),
            (4, 19, ("city", 2, 22)), (4, 20, ("city", 2, 23)),
            (3, 20, ("city", 1, 23))]

# Right yellow building: even rows run ...536 544 546 528...; (2, 32) had the
# odd-row edge cell 552.
PATCHES += [(2, 32, 546)]

# Inner median apex: the thin kerb lines (696 692 694 rising left, 688 690 698
# rising right) met in sidewalk kerbs 4 6 0 2 with a pit-rim hump 648/650
# above, leaving a dark triangle. Continue both thin lines to a point instead.
PATCHES += [(8, 17, 696), (8, 18, 698), (9, 15, 696), (9, 16, 692),
            (9, 17, 694), (9, 18, 688), (9, 19, 690), (9, 20, 698),
            (10, 15, 694)]

# The quilt's out-of-bounds filler becomes the city's hatched out-of-bounds
# cell.
OOB_FROM, OOB_TO = 662, 1024


class City:
    """City Arena metatiles, graphics and neighbour statistics."""

    def __init__(self, c24, rom):
        self.rom = rom
        self.bank = c24.metatile_bank
        self.gfx, _ = c24.graphics()
        self.colors = c24.palette()
        self.grid = cell_ids(c24).astype(int)
        self.h = collections.Counter()
        self.v = collections.Counter()
        rows, cols = self.grid.shape
        for y in range(rows):
            for x in range(cols):
                if x+1 < cols:
                    self.h[(self.grid[y, x], self.grid[y, x+1])] += 1
                if y+1 < rows:
                    self.v[(self.grid[y, x], self.grid[y+1, x])] += 1
        self._img = {}
        self._cost = {}

    def _addr(self, n, sx, sy):
        return self.bank*0x4000 + n + sx*0x400 + sy*0x1000

    def valid(self, n):
        """True if all 16 subtile pairs of metatile n lie inside its bank."""
        end = (self.bank+1)*0x4000
        return all(self._addr(n, sx, sy)+1 < end
                   for sx in range(4) for sy in range(4))

    def pairs(self, n):
        return bytes(b for sy in range(4) for sx in range(4)
                     for b in self.rom[self._addr(n, sx, sy):][:2])

    def img(self, n):
        if n not in self._img:
            im = render_tiles(4, 4, self.pairs(n), self.gfx, self.colors)
            self._img[n] = np.asarray(im, dtype=np.int16)
        return self._img[n]

    def cost(self, a, b, horiz):
        """Join cost of a next to b (left/right if horiz, else above/below)."""
        key = (a, b, horiz)
        if key not in self._cost:
            if (a, b) in (self.h if horiz else self.v):
                c = 0.0
            elif horiz:
                c = np.abs(self.img(a)[:, 31]-self.img(b)[:, 0]).mean()
                c = c/255 + PRIOR
            else:
                c = np.abs(self.img(a)[31]-self.img(b)[0]).mean()/255 + PRIOR
            self._cost[key] = c
        return self._cost[key]

    def render(self, grid):
        rows, cols = grid.shape
        full = bytearray(cols*4 * rows*4 * 2)
        for y in range(rows):
            for x in range(cols):
                p = self.pairs(int(grid[y, x]))
                for sy in range(4):
                    for sx in range(4):
                        d = ((y*4+sy)*cols*4 + x*4+sx)*2
                        s = (sy*4+sx)*2
                        full[d:d+2] = p[s:s+2]
        im = render_tiles(cols*4, rows*4, bytes(full), self.gfx, self.colors)
        return im.convert("RGB")


def solve(c23, c24, city):
    """Remap slot 23 cell IDs to City Arena IDs; returns the remapped grid."""
    A = cell_ids(c23).astype(int)
    ids23 = sorted(set(A.ravel().tolist()))
    pool = {m for m in set(city.grid.ravel().tolist()) | set(ids23)
            if city.valid(m)}

    def tr(course, n):
        return (template(course, n) & 63).tobytes()

    by_tr = collections.defaultdict(list)
    for m in pool:
        by_tr[tr(c24, m)].append(m)
    cand = {n: by_tr[tr(c23, n)] for n in ids23}
    occ = collections.defaultdict(list)
    rows, cols = A.shape
    for y in range(rows):
        for x in range(cols):
            occ[A[y, x]].append((y, x))
    f = {n: (n if n in cand[n] else cand[n][0]) for n in ids23}

    def total(n, m):
        def at(y, x):
            return m if A[y, x] == n else f[A[y, x]]
        t = 0
        for y, x in occ[n]:
            if x > 0:
                t += city.cost(at(y, x-1), m, True)
            if x+1 < cols:
                t += city.cost(m, at(y, x+1), True)
            if y > 0:
                t += city.cost(at(y-1, x), m, False)
            if y+1 < rows:
                t += city.cost(m, at(y+1, x), False)
        return t

    for _ in range(20):
        changed = 0
        for n in ids23:
            best = min(cand[n], key=lambda m: total(n, m))
            if best != f[n]:
                f[n] = best
                changed += 1
        if not changed:
            break
    return np.vectorize(f.get)(A)


def quilt(R, road, city):
    """Fill each cell from the remap or a shifted City Arena copy."""
    B = city.grid
    labels = OFFSETS + [REMAP]
    rows, cols = R.shape

    def src(y, x, l):
        if l == REMAP:
            return int(R[y, x])
        yy, xx = y+l[1], x+l[0]
        if (0 <= yy < B.shape[0] and 0 <= xx < B.shape[1]
                and city.valid(int(B[yy, xx]))):
            return int(B[yy, xx])
        return None

    def data(y, x, l):
        s = src(y, x, l)
        if s is None:
            return 1e9
        if road[y, x]:
            return 0.0 if s == R[y, x] else 1e9
        return 1.0 if l == REMAP else 0.0

    def smooth(y1, x1, l1, y2, x2, l2, horiz):
        if l1 == l2 and l1 != REMAP:
            return 0.0
        return city.cost(src(y1, x1, l1), src(y2, x2, l2), horiz)

    L = np.empty(R.shape, dtype=object)
    for y in range(rows):
        for x in range(cols):
            L[y, x] = min(labels,
                          key=lambda l: data(y, x, l)+0.01*labels.index(l))

    def local(y, x, l):
        t = data(y, x, l)
        if t >= 1e9:
            return t
        if x > 0:
            t += smooth(y, x-1, L[y, x-1], y, x, l, True)
        if x+1 < cols:
            t += smooth(y, x, l, y, x+1, L[y, x+1], True)
        if y > 0:
            t += smooth(y-1, x, L[y-1, x], y, x, l, False)
        if y+1 < rows:
            t += smooth(y, x, l, y+1, x, L[y+1, x], False)
        return t

    for _ in range(15):
        changed = 0
        for y in range(rows):
            for x in range(cols):
                b = min(labels, key=lambda l: local(y, x, l))
                if b != L[y, x] and local(y, x, b) < local(y, x, L[y, x])-1e-9:
                    L[y, x] = b
                    changed += 1
        if not changed:
            break
    return np.array([[src(y, x, L[y, x]) for x in range(cols)]
                     for y in range(rows)])


def patch(M, city):
    M = M.copy()
    for r, c, s in PATCHES:
        M[r, c] = int(city.grid[s[1], s[2]]) if isinstance(s, tuple) else s
    M[M == OOB_FROM] = OOB_TO
    return M


def labelled(im, rows, cols, scale=2):
    """Scale up and draw the cell grid with row,col labels."""
    im = im.resize((im.width*scale, im.height*scale), Image.NEAREST)
    d = ImageDraw.Draw(im)
    c = 32*scale
    for y in range(rows+1):
        d.line([(0, y*c), (im.width, y*c)], fill=(255, 255, 0))
    for x in range(cols+1):
        d.line([(x*c, 0), (x*c, im.height)], fill=(255, 255, 0))
    for y in range(rows):
        for x in range(cols):
            d.text((x*c+2, y*c+1), f"{y},{x}", fill=(255, 0, 0))
    return im


def main():
    parser = argparse.ArgumentParser(
        description="Reconstruct MSUSA extra slot 23 (conjectural).")
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path,
                        default=ROOT/"images/reconstructed/MSUSA_extras")
    parser.add_argument("--debug", type=Path,
                        help="also write grid, labelled and overlay images")
    parser.add_argument("--city-grid", type=Path, metavar="FILE",
                        help="also write a labelled City Arena grid PNG")
    args = parser.parse_args()
    entry = json.loads((ROOT/"data/msusa_extras.json").read_text())["23"]
    rom = read_rom("msusa", args.rom_dir)
    cs = {c.index: c for c in courses("msusa", rom, include_extras=True)}
    c23, c24 = cs[23], cs[24]
    city = City(c24, rom)
    if args.city_grid:
        args.city_grid.parent.mkdir(parents=True, exist_ok=True)
        labelled(city.render(city.grid), *city.grid.shape).save(args.city_grid)

    # Road-coded cells: any pixel with terrain code 0.
    codes = terrain_map(c23)
    rows, cols = cell_ids(c23).shape
    road = (codes.reshape(rows, 32, cols, 32) == 0).any(axis=(1, 3))

    M = patch(quilt(solve(c23, c24, city), road, city), city)
    im = city.render(M)
    args.output.mkdir(parents=True, exist_ok=True)
    out = args.output/entry["reconstruction"]["filename"]
    im.save(out)
    print(f"msusa:23 {im.width}x{im.height} {out.name} "
          f"({len(PATCHES)} patches)")

    if args.debug:
        args.debug.mkdir(parents=True, exist_ok=True)
        np.save(args.debug/"slot23_cells.npy", M)
        labelled(im, rows, cols).save(args.debug/"slot23_grid.png")
        edge = np.zeros_like(codes, bool)
        edge[:, 1:] |= codes[:, 1:] != codes[:, :-1]
        edge[1:, :] |= codes[1:, :] != codes[:-1, :]
        a = np.array(im)
        a[edge] = (255, 32, 160)
        Image.fromarray(a).save(args.debug/"slot23_terrain_overlay.png")


if __name__ == "__main__":
    main()
