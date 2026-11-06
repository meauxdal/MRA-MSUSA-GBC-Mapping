"""Source terrain regions, decoded from both games' original point lookups.

Codes are deliberately numeric: terrain dispatch behavior is not yet labeled.
This is a static point classification, not a vehicle-sized reachability mask.
"""
import numpy as np
from maps import CONFIG, bank20, be16, far

TERRAIN = {
    "msusa": dict(lookup=0x1f08, pointer=0xc60a, profiles=0x3980),
    "mra": dict(lookup=0x2308, pointer=0xc62a, profiles=0x3380),
}


def resource(course):
    g = bank20(be16(course.rom, CONFIG[course.game]["graphics"] + course.selectors[1]*2))
    return far(course.rom, g+1)


def cell_ids(course):
    n = course.width * course.height
    low = np.frombuffer(course.rom, dtype=np.uint8, count=n, offset=course.low_offset+2)
    high = np.frombuffer(course.rom, dtype=np.uint8, count=n, offset=course.high_offset+2)
    return (low.astype(np.uint16) + high.astype(np.uint16)*256).reshape(course.height, course.width)


def template(course, cell):
    """Raw selected terrain byte at every integer point in a 32x32 cell.

    Translation of MSUSA 00:1f48..1fda / MRA 00:2348..23da,
    including unsigned arithmetic and carry.
    Upper bits are retained here; callers may mask to the dispatch code (0..63).
    """
    r = course.rom
    base = resource(course) + 2*(int(cell) + int(cell)//2)
    # The CPU adds a 16-bit offset without switching banks.
    if base//0x4000 != resource(course)//0x4000 or (base+5)//0x4000 != base//0x4000:
        raise ValueError(f"Terrain descriptor leaves ROM bank for cell {cell}")
    result = np.empty((32,32), dtype=np.uint8)
    y, x = np.indices((32,16))
    for half in range(2):
        shape, first, second = r[base+half*3:base+half*3+3]
        u = 15-x if first & 0x40 else x
        family = (shape >> 1) & 0x70
        if family == 0x70:
            choose_second = u < (shape & 31)
        else:
            heights = np.frombuffer(r, dtype=np.uint8, count=16,
                                    offset=TERRAIN[course.game]["profiles"]+family)
            value = ((shape & 31)*4 - 64 + heights[u].astype(np.int16)) & 255
            if first & 0x80:
                boundary = np.where(value & 128, 0, np.minimum(value,32))
                choose_second = y < boundary
            else:
                inverse = (32-value) & 255
                boundary = np.where(inverse & 32, 32, inverse)
                choose_second = np.where(value <= 32, y >= boundary, (inverse & 128) != 0)
        result[:,half*16:(half+1)*16] = np.where(choose_second, second, first)
    return result


def terrain_map(course):
    ids = cell_ids(course)
    result = np.empty((course.height*32,course.width*32),dtype=np.uint8)
    cache = {int(n):template(course,int(n)) & 63 for n in np.unique(ids)}
    for y in range(course.height):
        for x in range(course.width):
            result[y*32:(y+1)*32,x*32:(x+1)*32] = cache[int(ids[y,x])]
    return result
