"""Export the "Game Boy Color only" warning screen shown on a monochrome Game Boy.

Both games check for a Game Boy Color at start-up. On any other model they draw
this plain 4-shade screen instead of booting. It is stored raw: a 20x18 map of
tile ids (one byte per cell, no attributes), followed directly by the tiles
(2bpp, ids 0.. at 0x9000 with signed addressing, BGP e4 = identity shades).

    MRA    map 0x224b0 (08:64b0), tiles 0x21ed0 (08:5ed0), 94 tiles
    MSUSA  map 0x13068 (04:7068), tiles 0x131d0 (04:71d0), 91 tiles

The tile data comes just before the map in MRA and just after it in MSUSA.
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from maps import ROOT, read_rom

SHADES=[255, 153, 85, 0]  # BGP e4 with the grays a PyBoy DMG capture shows
SCREENS=[
    ("mra", "MRA_warning", 0x224b0, 0x21ed0, 94,
     "Mickey's Racing Adventure"),
    ("msusa", "MSUSA_warning", 0x13068, 0x131d0, 91,
     "Mickey's Speedway USA"),
]

def render(rom, map_at, tiles_at, count, width=20, height=18):
    ids=rom[map_at:map_at+width*height]
    assert max(ids)<count, "map refers past the tile data"
    image=Image.new("L", (width*8, height*8))
    px=image.load()
    for cell, tile in enumerate(ids):
        raw=rom[tiles_at+tile*16:tiles_at+tile*16+16]
        for y in range(8):
            for x in range(8):
                v=(raw[y*2]>>(7-x)&1)|(raw[y*2+1]>>(7-x)&1)<<1
                px[cell%width*8+x, cell//width*8+y]=SHADES[v]
    return image

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path, default=ROOT/"images/screens")
    args=parser.parse_args()
    dest=args.output/"DMG_warning"
    dest.mkdir(parents=True, exist_ok=True)
    manifest=[]
    for n, (game, stem, map_at, tiles_at, count, name) in enumerate(SCREENS, 1):
        rom=read_rom(game, args.rom_dir)
        image=render(rom, map_at, tiles_at, count)
        file=f"{n:02d}_{stem}.png"
        image.save(dest/file)
        manifest.append(dict(index=n, name=f"{name} (Game Boy Color required)",
                             file=file, width=20, height=18,
                             tile_ids=f"0x{map_at:06x}",
                             graphics=f"0x{tiles_at:06x}", tile_count=count,
                             sha256=hashlib.sha256((dest/file).read_bytes()).hexdigest()))
        print(f"{file} {image.width}x{image.height}")
    (dest/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__=="__main__":
    main()
