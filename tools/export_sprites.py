"""Export Mickey's Racing Adventure's character sprites from the ROM.

The overworld characters are real hardware sprites (OAM, 8x16 mode). Their
frames live in banks 6c-7f as "animation tables", all in one layout:

    table   byte  frames-1
            byte  0
            u16   record pointer per frame (bank-relative, 0x4000-0x7fff)
    record  byte  a, byte b      (not understood; kept in the manifest)
            u16   tile data pointer (same bank, 16-byte aligned)
            K x (dy, dx, attr)   signed offsets from the frame's anchor point
                                 and the OAM attribute byte (bit 3 = VRAM bank
                                 1, bits 0-2 = palette, bit 5/6 = X/Y flip),
                                 padded with zeroes up to the tile data
    tiles   K x 32 bytes         uncompressed 2bpp; entry i is the 8x16 sprite
                                 made of tiles 2i and 2i+1

K is the number of entries before the zero padding that aligns the tile data
to 16 bytes; the next record starts right after the tiles, padded likewise. A table with a single frame is
a pose; the games keep several copies of the same pose in different banks.

All characters share one set of eight OBJ palettes (BGR555, four colours each)
at 6c:4200 (file offset 0x1b0200); the game copies it to 63:7900, 66:7700,
67:7a00 and 69:7900 as well. The attribute's palette bits select from it.

Each sheet puts the frames in a grid with one common cell size and anchor, so
frames line up. The tables are listed by hand (found with a scan for the layout
above; see docs/FORMAT.md).
"""
import argparse
import hashlib
import json
from pathlib import Path
from PIL import Image
from maps import ROOT, read_rom

PALETTE_AT = 0x1b0200
COLUMNS = 10

# (file stem, description, [(bank, address)...], single-frame poses?)
SHEETS = [
    ("Mickey_Walk_Front", "Mickey walking toward the camera", [(0x70, 0x4000)]),
    ("Mickey_Walk_Side", "Mickey walking sideways (faces left; mirror for right)", [(0x71, 0x4000)]),
    ("Mickey_Walk_Back", "Mickey walking away", [(0x72, 0x4000)]),
    ("Mickey_Poses", "Mickey standing poses (front, side, back)",
     [(0x6d, 0x7400), (0x6d, 0x7800), (0x6d, 0x7c00),
      (0x6e, 0x6400), (0x6e, 0x6800), (0x6e, 0x6c00)]),
    ("Pete_Walk_Front", "Pete walking toward the camera", [(0x6d, 0x4c00)]),
    ("Pete_Walk_Side", "Pete walking sideways", [(0x6e, 0x4000)]),
    ("Pete_Walk_Back", "Pete walking away", [(0x6f, 0x4000)]),
    ("Daisy_Walk_Front", "Daisy walking toward the camera", [(0x73, 0x4000)]),
    ("Daisy_Walk_Side", "Daisy walking sideways", [(0x74, 0x4000)]),
    ("Daisy_Walk_Back", "Daisy walking away", [(0x75, 0x4000)]),
    ("Daisy_Poses", "Daisy standing poses",
     [(0x6e, 0x7200), (0x6e, 0x7600), (0x6e, 0x7a00),
      (0x6f, 0x6300), (0x6f, 0x6700), (0x6f, 0x6b00)]),
    ("Donald_Walk_Front", "Donald walking toward the camera", [(0x76, 0x4000)]),
    ("Donald_Walk_Side", "Donald walking sideways", [(0x77, 0x4000)]),
    ("Donald_Walk_Back", "Donald walking away", [(0x78, 0x4000)]),
    ("Donald_Poses", "Donald standing poses",
     [(0x6f, 0x7200), (0x6f, 0x7600), (0x6f, 0x7a00),
      (0x70, 0x6c00), (0x70, 0x7000), (0x70, 0x7400)]),
    ("Goofy_Walk_Front", "Goofy walking toward the camera", [(0x7a, 0x4000)]),
    ("Goofy_Walk_Side", "Goofy walking sideways", [(0x7b, 0x4000)]),
    ("Goofy_Walk_Back", "Goofy walking away", [(0x7c, 0x4000)]),
    ("Goofy_Poses", "Goofy standing poses",
     [(0x72, 0x7800), (0x72, 0x7c00), (0x73, 0x7b00),
      (0x75, 0x7c00), (0x76, 0x7000), (0x76, 0x7400)]),
    ("Minnie_Walk_Front", "Minnie walking toward the camera", [(0x7d, 0x4000)]),
    ("Minnie_Walk_Side", "Minnie walking sideways", [(0x7e, 0x4000)]),
    ("Minnie_Walk_Back", "Minnie walking away", [(0x7f, 0x4000)]),
    ("Minnie_Poses", "Minnie standing poses",
     [(0x76, 0x7b00), (0x77, 0x7200), (0x77, 0x7600),
      (0x77, 0x7900), (0x77, 0x7d00), (0x79, 0x6900)]),
    ("Pluto_Anim_1", "Pluto animation", [(0x72, 0x6100)]),
    ("Pluto_Anim_2", "Pluto animation", [(0x73, 0x6b00)]),
    ("Pluto_Anim_3", "Pluto animation", [(0x74, 0x7000)]),
    ("Pluto_Anim_4", "Pluto lying down", [(0x75, 0x6400)]),
    ("Pluto_Anim_5", "Pluto animation", [(0x78, 0x6a00)]),
    ("Pluto_Anim_6", "Pluto animation", [(0x79, 0x4000)]),
    ("Pluto_Anim_7", "Pluto animation (red palette)", [(0x79, 0x5800)]),
    ("Pluto_Poses", "Pluto standing poses",
     [(0x70, 0x7b00), (0x71, 0x7200), (0x71, 0x7500),
      (0x71, 0x7800), (0x71, 0x7b00), (0x72, 0x7200)]),
    ("Item_Burger", "small food item", [(0x6c, 0x7100)]),
    ("Item_Blue", "small blue item", [(0x6c, 0x7600)]),
    ("Item_Pink", "small pink item", [(0x6c, 0x7b00)]),
    ("Money", "banknote", [(0x6d, 0x4000)]),
    ("Train", "toy train", [(0x7f, 0x6b00)]),
]
# Same animation stored again elsewhere; listed so the manifest can say so.
COPIES = {(0x6c, 0x7100): [(0x79, 0x7000), (0x79, 0x7500)]}


def bank_at(bank, address):
    return bank*0x4000+address-0x4000


def read_palettes(rom):
    palettes=[]
    for p in range(8):
        palettes.append([tuple(((rom[PALETTE_AT+p*8+c*2]
                                 |rom[PALETTE_AT+p*8+c*2+1]<<8)>>shift&31)<<3
                               for shift in (0, 5, 10))
                         for c in range(4)])
    return palettes


def signed(v):
    return v-256 if v>127 else v


def read_table(rom, bank, address):
    """Return the table's frames: dicts with entries, data offset and header."""
    at=bank_at(bank, address)
    count=rom[at]+1
    assert rom[at+1]==0, "not an animation table"
    pointers=[int.from_bytes(rom[at+2+2*i:at+4+2*i], "little")
              for i in range(count)]
    assert pointers[0]==address+2+2*count, "unexpected table layout"
    frames=[]
    for i, pointer in enumerate(pointers):
        record=bank_at(bank, pointer)
        data=int.from_bytes(rom[record+2:record+4], "little")
        k=(data-pointer-4)//3
        while k and rom[record+4+3*(k-1):record+4+3*k]==bytes(3):
            k-=1
        if i+1<count:
            # The next record follows this frame's tiles, padded to 16 bytes.
            gap=pointers[i+1]-(data+32*k)
            assert 0<=gap<16, f"{bank:02x}:{address:04x} frame {i}: gap {gap}"
        entries=[tuple(rom[record+4+3*e:record+7+3*e]) for e in range(k)]
        frames.append(dict(table=f"{bank:02x}:{address:04x}", index=i,
                           record=record, header=(rom[record], rom[record+1]),
                           data=bank_at(bank, data), entries=entries))
    return frames


def frame_key(rom, frame):
    k=len(frame["entries"])
    return (tuple(frame["entries"]), rom[frame["data"]:frame["data"]+32*k])


def extent(frames):
    xs=[signed(dx) for f in frames for _, dx, _ in f["entries"]]
    ys=[signed(dy) for f in frames for dy, _, _ in f["entries"]]
    return min(xs), min(ys), max(xs)+8, max(ys)+16


def draw(rom, palettes, frame, image, left, top, ax, ay):
    px=image.load()
    for i, (dy, dx, attr) in enumerate(frame["entries"]):
        flip_x, flip_y, palette=attr&0x20, attr&0x40, attr&7
        for half in range(2):
            tile=2*i+(half^(1 if flip_y else 0))
            raw=rom[frame["data"]+tile*16:frame["data"]+tile*16+16]
            for y in range(8):
                for x in range(8):
                    sx=7-x if flip_x else x
                    sy=7-y if flip_y else y
                    v=(raw[sy*2]>>(7-sx)&1)|(raw[sy*2+1]>>(7-sx)&1)<<1
                    if v:
                        px[left+ax+signed(dx)+x,
                           top+ay+signed(dy)+half*8+y]=palettes[palette][v]+(255,)


def sheet(rom, palettes, frames):
    x0, y0, x1, y1=extent(frames)
    width, height=x1-x0, y1-y0
    rows=(len(frames)+COLUMNS-1)//COLUMNS
    columns=min(COLUMNS, len(frames))
    image=Image.new("RGBA", (columns*width, rows*height), (0, 0, 0, 0))
    cells=[]
    for n, frame in enumerate(frames):
        cell=Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw(rom, palettes, frame, cell, 0, 0, -x0, -y0)
        image.paste(cell, (n%COLUMNS*width, n//COLUMNS*height))
        cells.append(cell)
    return image, cells, (width, height, -x0, -y0)


def gif(cells, path):
    frames=[]
    for cell in cells:
        background=Image.new("RGBA", cell.size, (255, 0, 255, 255))
        background.alpha_composite(cell)
        frames.append(background.convert("RGB").quantize(
            colors=64, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
    # Magenta is the key colour: find its index per frame and mark it clear.
    key=None
    for f in frames:
        palette=f.getpalette()
        for i in range(len(palette)//3):
            if palette[i*3:i*3+3]==[255, 0, 255]:
                key=i
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=100, transparency=key, disposal=2)


def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path, default=ROOT/"images/sprites")
    args=parser.parse_args()
    rom=read_rom("mra", args.rom_dir)
    palettes=read_palettes(rom)
    dest=args.output/"MRA"
    dest.mkdir(parents=True, exist_ok=True)
    manifest=[]
    for n, (stem, name, tables) in enumerate(SHEETS, 1):
        frames, seen=[], {}
        for bank, address in tables:
            for frame in read_table(rom, bank, address):
                key=frame_key(rom, frame)
                if key in seen:
                    seen[key]["also_at"].append(frame["table"]+f"[{frame['index']}]")
                    continue
                frame["also_at"]=[]
                seen[key]=frame
                frames.append(frame)
        image, cells, (width, height, ax, ay)=sheet(rom, palettes, frames)
        file=f"{n:02d}_{stem}.png"
        image.save(dest/file)
        entry=dict(index=n, name=stem.replace("_", " "), file=file,
                   identification=name, cell_width=width, cell_height=height,
                   anchor=[ax, ay], columns=min(COLUMNS, len(frames)),
                   palette="0x%06x"%PALETTE_AT,
                   copies=[f"{b:02x}:{a:04x}" for b, a in
                           COPIES.get(tables[0], [])],
                   frames=[dict(table=f["table"], frame=f["index"],
                                header=list(f["header"]), record="0x%06x"%f["record"],
                                tiles="0x%06x"%f["data"], pieces=len(f["entries"]),
                                also_at=f["also_at"]) for f in frames])
        if len(tables)==1 and len(frames)>1:
            entry["gif"]=file.replace(".png", ".gif")
            gif(cells, dest/entry["gif"])
        entry["sha256"]=hashlib.sha256((dest/file).read_bytes()).hexdigest()
        manifest.append(entry)
        print(f"{file} {len(frames)} frames, cell {width}x{height}")
    (dest/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


if __name__=="__main__":
    main()
