"""Export MRA full-screen story, menu and interior images.

Each image has its own hard-coded loader in ROM banks 06-09, 16, 18 and 19, in
the same style as the world-map loaders (see export_screens.py and
docs/FORMAT.md). The loader code is laid out as

    LD HL,tiles / LD DE,d000 / LD A,bank / LD B,1 / LD C,0 / CALL 1f82   (x1-2)
    ... far calls ...
    LD B,h / LD HL,ids / ... LD A,w / ... LD A,plane bank / ...          (ids)
    LD B,h / LD HL,attrs / ... LD A,w / ... LD A,plane bank / ...        (attrs)
    ... LD B,8 / LD DE,palette / CALL 3147

so the tile copies sit 35-65 bytes *before* the plane copy that the entry
address marks, and the palette is a little after it. The tile blocks go to VRAM
banks 0 and 1 at 8800 like the world maps.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from maps import ROOT, read_rom
from export_screens import (PLANES, TILES, PALETTE, Parts, copy_tiles, le16,
                            offset, save)

ATTRS=re.compile(rb"\x06(.)\x21(..)\x11\x00[\xd4\xd8]\x3e(.)\xe0\x94\x0e\x00"
                 rb"\x3e(.)\xe0\x96", re.S)

# Wider panoramas: further plane copies into d800 (ids) and dc00 (attributes)
# hold extra columns that the game scrolls in to the right of the 32-tile map.
EXTRA=re.compile(rb"\x06(.)\x21(..)\x11\x00([\xd8\xdc])\x3e(.)\xe0\x94\x0e\x00"
                 rb"\x3e(.)\xe0\x96", re.S)

# (bank, loader address, file name, description). Names say what is on
# screen; the game gives none of these a title.
SCREENS=[
    (0x08, 0x42ac, "Title_Screen", "title screen"),
    (0x08, 0x46d4, "Opening_Group", "opening panorama: the friends at the party (320 px wide)"),
    (0x08, 0x48db, "Opening_Hills", "opening panorama: hills and a tree (256 px wide)"),
    (0x08, 0x4a9b, "Pluto_and_Mickey", "Pluto and Mickey"),
    (0x08, 0x4c0e, "Wrecked_Parade", "wrecked parade floats"),
    (0x08, 0x4d45, "Mickey_Oh_No", "Mickey clutching his head"),
    (0x08, 0x4e7c, "Pete's_Note", "Pete's ransom note"),
    (0x08, 0x5062, "Dusty_Scuffle", "the gang in a cloud of dust"),
    (0x08, 0x51f7, "Pete's_Gang_Driving", "toy car on the road"),
    (0x08, 0x533d, "Pete's_Hideout", "Pete and his gang in the hideout"),
    (0x08, 0x5486, "Pete_Window", "Pete at a round window"),
    (0x08, 0x55cf, "Pete_Spyglass", "Pete looking through a spyglass"),
    (0x08, 0x5715, "Mansion_Door", "stairs behind open doors"),
    (0x08, 0x5941, "Pete's_Mansion", "tall image, 160x432: road up a hill to Pete's tower"),
    (0x16, 0x5261, "Medieval_Pete", "Pete in armor (puzzle picture)"),
    (0x16, 0x5371, "Wonderland_Pete", "Pete with candy canes (puzzle picture)"),
    (0x16, 0x5481, "Frontier_Pete", "Pete as a cowboy (puzzle picture)"),
    (0x16, 0x5591, "Pirate_Pete", "Pete as a pirate (puzzle picture)"),
    (0x16, 0x56a1, "Fairground_Pete", "Pete as a ringmaster (puzzle picture)"),
    (0x16, 0x580d, "Mansion_Pete", "Pete in a purple cape (puzzle picture)"),
    (0x09, 0x4889, "Clarabel's_Booth", "ticket booth"),
    (0x09, 0x5009, "Mickey's_House", "interior with blue walls and stairs"),
    (0x09, 0x5460, "Minnie's_House", "interior with pink walls and stairs"),
    (0x09, 0x5852, "Donald's_House", "interior with green and yellow walls"),
    (0x09, 0x5c7e, "Goofy's_House", "interior with wooden stairs and a red rug"),
    (0x09, 0x60d5, "Daisy's_House", "interior with pink walls and an arched door"),
    (0x09, 0x64de, "Pluto's_Doghouse", "inside a doghouse"),
    (0x09, 0x73d4, "Ludwig_Von_Drake's_Garage", "toy racers at the exit"),
    (0x09, 0x75ce, "Ludwig_Von_Drake's_Laboratory", "laboratory"),
    (0x16, 0x458d, "Wreath", "holly wreath on black"),
    (0x16, 0x47dc, "Sign", "blank signboard"),
    (0x16, 0x49cd, "Speech_Bubble", "blank speech bubble"),
    (0x16, 0x4fc0, "Print_Shop", "desk with a computer"),
    (0x16, 0x757e, "Language_Select", "language selection"),
    (0x18, 0x4833, "File_Select", "three empty picture frames with name plates"),
    (0x18, 0x565e, "Name_Entry", "name entry"),
    (0x18, 0x664e, "Chip_'n'_Dale's_Treehouse", "treasure cave"),
    (0x18, 0x7379, "Magica_De_Spell's_House", "Donald on a stage"),
    (0x19, 0x44b0, "Butch_Growl", "bulldog"),
    (0x19, 0x4be4, "Mickey's_Garage", "hallway with a shelf"),
    (0x19, 0x5d6c, "Letter", "blank letter"),
    (0x19, 0x6097, "Parcel_Shelf", "shelf of toys"),
    (0x19, 0x6447, "Post_Office", "post office"),
]

def decode(rom, bank, entry):
    at=offset(bank, entry)
    ids=PLANES.match(rom, at)
    attrs=ATTRS.search(rom, ids.end(), ids.end()+0x40)
    height, width=ids.group(1)[0], ids.group(3)[0]
    assert attrs.group(1)==ids.group(1) and attrs.group(2)!=b"", entry
    gfx=[bytearray(4096), bytearray(4096)]
    sources=[None, None]
    for copy in TILES.finditer(rom, at-65, at):
        tile_bank, wram, count=copy.group(2)[0], copy.group(3)[0], copy.group(4)[0]
        address=le16(copy.group(1), 0)
        gfx[wram-1]=copy_tiles(rom, tile_bank, address, count or 256)
        sources[wram-1]=offset(tile_bank, address)
    palette=PALETTE.search(rom, at, at+0x200)
    palette=offset(bank, le16(palette.group(1), 0))
    id_bank, attr_bank=ids.group(4)[0], attrs.group(4)[0]
    ids_at=offset(id_bank, le16(ids.group(2), 0))
    attrs_at=offset(attr_bank, le16(attrs.group(2), 0))
    size=width*height
    ids_data, attrs_data=rom[ids_at:ids_at+size], rom[attrs_at:attrs_at+size]
    extra={}
    for more in EXTRA.finditer(rom, attrs.end(), attrs.end()+0x80):
        if more.group(1)!=ids.group(1):
            continue  # a different-sized overlay, not extra columns
        more_width=more.group(4)[0]
        more_at=offset(more.group(5)[0], le16(more.group(2), 0))
        extra[more.group(3)]=(more_width, rom[more_at:more_at+more_width*height])
    if b"\xd8" in extra and b"\xdc" in extra:
        extra_width=extra[b"\xd8"][0]
        assert extra[b"\xdc"][0]==extra_width, entry
        def widen(base, more):
            return b"".join(
                base[r*width:(r+1)*width]+more[r*extra_width:(r+1)*extra_width]
                for r in range(height))
        ids_data=widen(ids_data, extra[b"\xd8"][1])
        attrs_data=widen(attrs_data, extra[b"\xdc"][1])
        width+=extra_width
    entry_info=dict(loader=f"{bank:02x}:{entry:04x}", width=width, height=height,
                    tile_ids=f"0x{ids_at:06x}", attributes=f"0x{attrs_at:06x}",
                    graphics=[f"0x{s:06x}" if s is not None else None
                              for s in sources],
                    palette=f"0x{palette:06x}")
    return entry_info, Parts(width, height, ids_data, attrs_data, gfx, palette)

def screens(rom):
    seen={}
    for bank, entry, stem, description in SCREENS:
        info, parts=decode(rom, bank, entry)
        key=(info["tile_ids"], info["attributes"], tuple(info["graphics"]),
             info["palette"])
        if key in seen:
            continue
        seen[key]=stem
        yield info, description, stem, parts

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path, default=ROOT/"images/screens")
    args=parser.parse_args()
    rom=read_rom("mra", args.rom_dir)
    dest=args.output/"MRA_cutscenes"
    manifest=[]
    for n, (info, description, stem, parts) in enumerate(screens(rom), 1):
        entry=dict(index=n, name=stem.replace("_", " "),
                   file=f"{n:02d}_{stem}.png", identification=description, **info)
        manifest.append(save(parts, rom, dest, entry))
    (dest/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__=="__main__":
    main()
