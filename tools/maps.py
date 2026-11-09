"""Read Rare's two-plane GBC course maps from user-supplied ROMs.

No ROM data is embedded. See docs/FORMAT.md for the traced loader addresses.
"""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "mra": dict(pattern="*Racing Adventure*.gbc", count=23, planes=0x800C8,
                graphics=0x80152, palettes=0x80297,
                sha256="b289e0f55c6d3e8c230e2ccaa29f821e417e7a19e5b31d35b61c5f0516ccdca1"),
    "msusa": dict(pattern="*Speedway USA*.gbc", count=21, planes=0x800E1,
                  graphics=0x80177, palettes=0x802E5,
                  sha256="9263a2138f5852177ea8a2436c6ddf6ec4ad41fc155d184b1773749533d6a470"),
}

def be16(data, offset):
    return int.from_bytes(data[offset:offset+2], "big")

def far(data, offset):
    bank, high, low = data[offset:offset+3]
    if not 0x40 <= high < 0x80:
        raise ValueError(f"Invalid far pointer at {offset:#x}")
    return bank * 0x4000 + (high - 0x40) * 256 + low

def bank20(pointer):
    if not 0x4000 <= pointer < 0x8000:
        raise ValueError(f"Invalid bank 20 pointer {pointer:#x}")
    return 0x80000 + pointer - 0x4000

def read_rom(game, directory=ROOT / "local"):
    paths = list(Path(directory).glob(CONFIG[game]["pattern"]))
    if len(paths) != 1:
        raise ValueError(f"Expected one {game} ROM in {directory}, found {len(paths)}")
    data = paths[0].read_bytes()
    if hashlib.sha256(data).hexdigest() != CONFIG[game]["sha256"]:
        raise ValueError(f"Unsupported ROM revision for {game}: {paths[0].name}")
    return data

@dataclass
class Course:
    game: str
    index: int
    descriptor: int
    selectors: bytes
    width: int
    height: int
    low_offset: int
    high_offset: int
    metatile_bank: int
    graphics_offsets: list
    palette_offset: int
    rom: bytes

    def tile_pairs(self, unmapped=None):
        """Row-major 8x8 tile IDs and CGB attribute bytes, at native map size."""
        w, h = self.width, self.height
        result = bytearray(w * h * 16 * 2)
        for y in range(h):
            for x in range(w):
                i = y*w+x
                address = (self.metatile_bank*0x4000 + self.rom[self.low_offset+2+i]
                           + self.rom[self.high_offset+2+i]*256)
                for sy in range(4):
                    for sx in range(4):
                        src = address + sx*0x400 + sy*0x1000
                        dest = ((y*4+sy)*w*4+x*4+sx)*2
                        if src+1 >= (self.metatile_bank+1)*0x4000:
                            if unmapped is None:
                                raise ValueError(f"Metatile outside bank: {src:#x}")
                            unmapped.add(dest//2)
                            continue
                        result[dest:dest+2] = self.rom[src:src+2]
        return bytes(result)

    def graphics(self, patches=()):
        result = []
        lengths = []
        for offset in self.graphics_offsets:
            if offset is None:
                result.append(bytearray(4096))
                lengths.append(0)
                continue
            n = (self.rom[offset] or 256)*16
            result.append(bytearray(self.rom[offset+1:offset+1+n]) + bytearray(4096-n))
            lengths.append(n)
        for patch in patches:
            # The engines address these background tiles in signed mode at $9000.
            dest = patch["dest"] - 0x9000
            dest %= 4096
            n = patch["tiles"]*16
            source = patch["bank"]*0x4000 + patch["source"] - 0x4000
            bank = patch["vram_bank"]
            if bank not in (0,1) or dest+n>4096 or source<0:
                raise ValueError(f"Unsupported animation upload: {patch}")
            result[bank][dest:dest+n] = self.rom[source:source+n]
        return result, lengths

    def palette(self, full_range=False):
        result=[]
        for i in range(32):
            color=int.from_bytes(self.rom[self.palette_offset+i*2:self.palette_offset+i*2+2],"little")
            values=[(color>>shift)&31 for shift in (0,5,10)]
            result.append(tuple(v*255//31 if full_range else v<<3 for v in values))
        return result

def courses(game, data, *, include_extras=False):
    cfg=CONFIG[game]
    count=25 if game=="msusa" and include_extras else cfg["count"]
    for index in range(count):
        pointer=be16(data,0x80000+index*2)
        if not pointer:
            continue
        desc=bank20(pointer)
        selectors=data[desc:desc+7]
        low=far(data,cfg["planes"]+selectors[0]*6)
        high=far(data,cfg["planes"]+selectors[0]*6+3)
        w,h=data[low:low+2]
        if not w or not h or data[high:high+2]!=bytes((w,h)):
            raise ValueError(f"Invalid plane dimensions for {game}:{index}")
        g=bank20(be16(data,cfg["graphics"]+selectors[1]*2))
        offsets=[far(data,g+4)]
        # MSUSA's extra slots 21-23 have seven-byte descriptors. Reading a
        # second pointer there would consume bytes from the next descriptor.
        size=10
        if game=="msusa" and selectors[1]<24:
            next_g=bank20(be16(data,cfg["graphics"]+(selectors[1]+1)*2))
            size=next_g-g
        if size not in (7,10):
            raise ValueError(f"Unexpected graphics descriptor size: {size}")
        offsets.append(far(data,g+7) if size==10 and data[g+8:g+10]!=b'\0\0' else None)
        yield Course(game,index,desc,selectors,w,h,low,high,data[g],offsets,
                     far(data,cfg["palettes"]+selectors[4]*3),data)

# Subtile lookups past the metatile bank read CPU $8000 (VRAM) on hardware, so
# the ROM alone doesn't decide them. Where gameplay footage shows what appears
# there, that colour is drawn; the rest stay transparent. Pete's Dungeon: the
# bottom-right subtile of its margin filler cell shows black in play.
OBSERVED_FILL = {("mra", 4): (0, 0, 0)}

def render(course, patches=(), full_range=False):
    unmapped=set()
    pairs=course.tile_pairs(unmapped)
    gfx,lengths=course.graphics(patches)
    colors=course.palette(full_range)
    fill=OBSERVED_FILL.get((course.game,course.index))
    return render_tiles(course.width*4,course.height*4,pairs,gfx,colors,unmapped,fill)

def render_tiles(width,height,pairs,gfx,colors,unmapped=None,fill=None):
    from PIL import Image
    unmapped=unmapped or set()
    cache={}
    result=Image.new("RGBA" if unmapped and not fill else "RGB",(width*8,height*8))
    tw=width
    for i in range(0,len(pairs),2):
        if i//2 in unmapped:
            if fill:
                t=i//2
                result.paste(fill,((t%tw)*8,(t//tw)*8,(t%tw)*8+8,(t//tw)*8+8))
            continue
        n,a=pairs[i:i+2]
        key=(n,a & 0x6f)  # bit 7 is sprite priority, not a background color change
        if key not in cache:
            raw=gfx[(a>>3)&1][n*16:n*16+16]
            tile=Image.new("RGB",(8,8))
            px=tile.load()
            for y in range(8):
                for x in range(8):
                    xx=7-x if a&32 else x
                    yy=7-y if a&64 else y
                    v=((raw[yy*2]>>(7-xx))&1)+2*((raw[yy*2+1]>>(7-xx))&1)
                    px[x,y]=colors[(a&7)*4+v]
            cache[key]=tile
        tile_number=i//2
        result.paste(cache[key],((tile_number%tw)*8,(tile_number//tw)*8))
    return result

def animation_patches(game):
    path=ROOT / "data" / f"{game}_animations.json"
    return json.loads(path.read_text()) if path.exists() else {}
