"""Export MRA's Pluto digging stages: 7 worlds of 4 stages, decoded from ROM.

Pluto digs into a hole in town and the stage engine in bank f0 builds the
level. All offsets below are banked addresses (bank:address).

- f0:568a: one pointer per world (7) to a world block. The block starts with
  a pointer to the world header, then four 5-byte stage entries whose first
  three bytes are a far pointer (bank, low, high) to the stage data. The
  stage index ff fe is world*4+stage.
- World header (f0): metatile bank and high byte, graphics far pointer
  (bank, high, low; data starts 0x10 bytes in), more far pointers, then five
  palette pointers (the second one is the level palette, bank f0) and five
  VRAM addresses of animated 2x2 tile groups.
- Stage data: a 12-byte header, 16 object entries of 2 bytes, width and
  height in 32x32 metatiles, then one metatile id per cell (RAM c9e0, copied
  from f0:484e).
- Metatile e is 4x4 tiles. Pair k (row-major) of e is the (tile, attribute)
  at metatile_base + e*2 + k*0x200; attribute bit 4 is cleared on load.
- Tiles use signed addressing: ids 0-127 at 9000, 128-255 at 8800, all in
  VRAM bank 0. The graphics block is copied in the order 9000, 9400, 8800,
  8c00, so it is indexed by the unsigned tile id.
- Palette: the fade-in (f0:7cb5) stops one step short of full, at 245/256,
  so every channel shows as (v*245+128)>>8.
- Animation: slot 0 is the bone, 5 frames at f7:6000 played back and forth;
  slot 3 is a second object, 4 frames at f7:6440. Each frame is 4 tiles
  (0x40 bytes). The PNGs use the first frame of each.
"""
import argparse
import hashlib
import json
from pathlib import Path
from maps import ROOT, read_rom, render_tiles

WORLDS=7
BONE_FRAMES=[0x6000, 0x6040, 0x6080, 0x60c0, 0x6100]
ITEM_FRAMES=[0x6440, 0x6480, 0x64c0, 0x6500]
ANIMATIONS=((0, BONE_FRAMES), (3, ITEM_FRAMES))  # (slot, frames)

def offset(bank, address):
    return bank*0x4000+(address-0x4000 if address>=0x4000 else address)

def le16(rom, at):
    return rom[at]|rom[at+1]<<8

def world_header(rom, world):
    block=le16(rom, offset(0xf0, 0x568a)+world*2)
    return block, le16(rom, offset(0xf0, block))

def fade(rom, at):
    """Level palette as shown on screen, after the short fade-in."""
    colors=[]
    for i in range(32):
        value=le16(rom, at+i*2)
        colors.append(tuple((((value>>shift)&31)*245+128>>8)<<3
                            for shift in (0, 5, 10)))
    return colors

def slot_tile(address):
    """Unsigned tile id of an animated group's VRAM address."""
    return (address-0x9000)//16 if address>=0x9000 else 128+(address-0x8800)//16

def decode(rom, index, frames=(0, 0)):
    """Decode stage index (ff fe). frames picks the bone and item frame."""
    world, number=index>>2, index&3
    block, header=world_header(rom, world)
    h=offset(0xf0, header)
    meta_bank, meta_high=rom[h], rom[h+2]
    gfx_at=offset(rom[h+3], (rom[h+5]<<8|rom[h+4])+0x10)
    palette=offset(0xf0, le16(rom, h+17))
    slots=[le16(rom, h+25+2*i) for i in range(5)]
    entry=offset(0xf0, block)+2+number*5
    data=offset(rom[entry], rom[entry+1]|rom[entry+2]<<8)
    width, height=rom[data+44], rom[data+45]
    cells=rom[data+46:data+46+width*height]
    pairs=bytearray(width*4*height*4*2)
    for i, metatile in enumerate(cells):
        base=offset(meta_bank, (meta_high<<8)+metatile*2)
        for k in range(16):
            at=base+k*0x200
            x=(i%width)*4+k%4
            y=(i//width)*4+k//4
            n=(y*width*4+x)*2
            pairs[n]=rom[at]
            pairs[n+1]=rom[at+1]&~0x10
    gfx=bytearray(rom[gfx_at:gfx_at+0x1000])
    for (slot, sequence), frame in zip(ANIMATIONS, frames):
        source=offset(0xf7, sequence[frame])
        tile=slot_tile(slots[slot])
        gfx[tile*16:tile*16+64]=rom[source:source+64]
    entry_info=dict(index=index, world=world+1, stage=number+1,
                    width=width*32, height=height*32,
                    metatiles=f"{width}x{height}",
                    stage_data=f"0x{data:06x}", world_header=f"0x{h:06x}",
                    metatile_defs=f"0x{offset(meta_bank, meta_high<<8):06x}",
                    graphics=f"0x{gfx_at:06x}", palette=f"0x{palette:06x}",
                    animated_tiles={"bone": f"0x{slot_tile(slots[0]):02x}",
                                    "item": f"0x{slot_tile(slots[3]):02x}"})
    return entry_info, bytes(pairs), [bytes(gfx), bytes(0x1000)], fade(rom, palette)

# Titles from each stage's title card in the game, in stage index order.
NAMES=[
    "Let's Get Started", "Squares", "Meet Butch", "Bash the Bully",
    "Jawbreaker Roll", "Butch Chase", "Candy Columns", "One Chance Candy Smash",
    "Pieces of Nineteen", "Barrels Away", "Butch's Slimy Demise",
    "Double Barrel Drop",
    "Pluto's Panic", "From the Top", "Keep Diggin'", "Boulder Drop",
    "Back and Forth", "Rock and Roll", "Quick Dig", "Harrowing Rock Hollow",
    "Root of the Problem", "Circle of Growth", "Log Jam", "Quick Slime",
    "Ducks in a Row", "Domino Ducks", "Duck Drop", "Duck!",
]

# Bone cycle: the game steps the frame every 8 video frames (Game Boy Color
# refresh is 4194304/70224 Hz), ping-ponging through the five frames.
BONE_ORDER=[0, 1, 2, 3, 4, 3, 2, 1]
STEP_CENTISECONDS=8*70224*100/4194304

def write_bone_gif(path, rom, index):
    """Lossless looping GIF of the stage with its bones spinning."""
    import numpy as np
    from PIL import Image
    images=[]
    for frame in BONE_ORDER:
        entry, pairs, gfx, colors=decode(rom, index, (frame, 0))
        images.append(np.asarray(render_tiles(entry["width"]//8,
                                              entry["height"]//8, pairs, gfx, colors)))
    palette=sorted({tuple(c) for a in images for c in a.reshape(-1, 3)})
    lookup={c: i for i, c in enumerate(palette)}
    flat=[v for c in palette for v in c]
    frames=[]
    for a in images:
        p=Image.fromarray(np.array([[lookup[tuple(c)] for c in row] for row in a],
                                   dtype=np.uint8), "P")
        p.putpalette(flat)
        frames.append(p)
    # Round absolute boundaries so the loop length does not drift.
    edges=[round(STEP_CENTISECONDS*i) for i in range(len(frames)+1)]
    durations=[(edges[i+1]-edges[i])*10 for i in range(len(frames))]
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=durations, optimize=False, disposal=1)
    return sum(durations)

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path,
                        default=ROOT/"images/screens/MRA_dig")
    args=parser.parse_args()
    rom=read_rom("mra", args.rom_dir)
    args.output.mkdir(parents=True, exist_ok=True)
    manifest=[]
    for index in range(WORLDS*4):
        entry, pairs, gfx, colors=decode(rom, index)
        w, h=entry["width"]//8, entry["height"]//8
        entry["name"]=NAMES[index]
        entry["file"]=f"{index+1:02d}_{NAMES[index].replace(' ', '_')}.png"
        render_tiles(w, h, pairs, gfx, colors).save(args.output/entry["file"])
        entry["sha256"]=hashlib.sha256((args.output/entry["file"]).read_bytes()).hexdigest()
        entry["gif"]=Path(entry["file"]).with_suffix(".gif").name
        entry["gif_duration_ms"]=write_bone_gif(args.output/entry["gif"], rom, index)
        print(f"{entry['file']} {entry['width']}x{entry['height']}", flush=True)
        manifest.append(entry)
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__=="__main__":
    main()
