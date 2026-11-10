"""Export MSUSA full-screen story stills, newspapers and menus.

Each image has its own hard-coded loader, like the MRA cutscenes (see
export_cutscenes.py and docs/FORMAT.md), but with different helper routines:

    LD HL,tiles / LD DE,d000 / LD A,bank / LD B,wram / LD C,0 / CALL 1baa
    LD B,h / LD HL,ids   / LD DE,d000 / LD A,20 / LDH (94),A / LD C,0
        LD A,plane bank / LDH (96),A / LD A,1 / CALL 1aea
    LD B,h / LD HL,attrs / LD DE,d400 / ... same ...
    ... LD B,8 / LD DE,palette / CALL 2b84

The tile copies sit up to ~200 bytes before the id plane that the entry address
marks (B=1 and B=2 are the two VRAM tile blocks) and the palette comes after
the attribute plane.

The people stills (phone calls and so on) reserve their bottom two tile rows
for the dialogue box, whose graphics the game writes at run time. Those rows
are cropped (160x128) because the ROM data alone renders them as noise.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from maps import ROOT, read_rom
from export_screens import (PLANES, Parts, copy_tiles, le16, offset, save)

TILES=re.compile(rb"\x21(..)\x11\x00\xd0\x3e(.)\x06(.)\x0e(.)\xcd\xaa\x1b", re.S)
ATTRS=re.compile(rb"\x06(.)\x21(..)\x11\x00\xd4\x3e(.)\xe0\x94\x0e\x00"
                 rb"\x3e(.)\xe0\x96", re.S)
PALETTE=re.compile(rb"\x06\x08\x11(..)\xcd\x84\x2b", re.S)

# (bank, loader address, file name, description). Names say what is on
# screen; the game gives none of these a title.
SCREENS=[
    (0x08, 0x410b, "Game_Over", "GAME OVER on a checkerboard"),
    (0x08, 0x4351, "Weasels_in_Jail", "the weasels behind bars"),
    (0x08, 0x4438, "Diamond_Collar", "a diamond collar"),
    (0x08, 0x4540, "Newspaper_Weasels_Jailed", "Hometown Herald: WEASELS JAILED"),
    (0x08, 0x463e, "Newspaper_Pluto_Rescued", "Hometown Herald: PLUTO RESCUED"),
    (0x08, 0x473c, "Newspaper_Race_Ends", "Hometown Herald: RACE ENDS!"),
    (0x08, 0x6665, "Ludwig_Von_Drake", "Ludwig Von Drake waving"),
    (0x08, 0x674c, "Minnie_on_Phone", "Minnie on the phone"),
    (0x08, 0x6a3f, "Goofy_on_Phone", "Goofy on the phone"),
    (0x08, 0x6b39, "Pete_on_Phone", "Pete on the phone"),
    (0x08, 0x6c30, "Donald_on_Phone", "Donald on the phone"),
    (0x08, 0x6d18, "Daisy_on_Phone", "Daisy on the phone"),
    (0x08, 0x6dff, "Mickey_on_Phone", "Mickey on the phone"),
    (0x08, 0x6ee6, "Mickey_with_Letter", "Mickey reading a letter by a doghouse"),
    # The ransom note is one loader (08:68c9-695a) that picks tiles and planes
    # from the language byte ce38: 80 English, 81 French, 82 German, 83
    # Spanish. The tile copies are in the dispatcher, not before each plane.
    (0x08, 0x695a, "Ransom_Note_(English)", "the weasels' ransom note (English)",
     [(0x75b0, 0x90, 1), (0x45b0, 0x91, 2)]),
    (0x08, 0x68c9, "Ransom_Note_(French)", "the weasels' ransom note (French)",
     [(0x40b0, 0x76, 1)]),
    (0x08, 0x68fa, "Ransom_Note_(German)", "the weasels' ransom note (German)",
     [(0x5050, 0x76, 1), (0x6050, 0x76, 2)]),
    (0x08, 0x692a, "Ransom_Note_(Spanish)", "the weasels' ransom note (Spanish)",
     [(0x6140, 0x76, 1)]),
    (0x05, 0x4ec2, "Yellow_Machine", "a yellow machine on black"),
    (0x04, 0x4e1c, "Trophy_Case_(French)", "trophy case (French)"),
    (0x04, 0x4e81, "Trophy_Case_(German)", "trophy case (German)"),
    (0x04, 0x4ee6, "Trophy_Case_(Spanish)", "trophy case (Spanish)"),
    (0x04, 0x4f4b, "Trophy_Case_(English)", "trophy case (English)"),
    (0x12, 0x6d66, "Language_Select", "language selection"),
]

# Loaders whose bottom two tile rows hold the dialogue box.
DIALOGUE=(0x4351, 0x4438, 0x6665, 0x674c, 0x6a3f, 0x6b39, 0x6c30, 0x6d18,
          0x6dff, 0x6ee6, 0x4ec2)

def decode(rom, bank, entry, tiles=None):
    """Decode one loader; tiles is [(address, bank, wram block)] when the
    tile copies are not in the usual spot just before the id plane."""
    at=offset(bank, entry)
    ids=PLANES.match(rom, at)
    attrs=ATTRS.match(rom, ids.end()+5)
    height, width=ids.group(1)[0], ids.group(3)[0]
    assert attrs.group(1)==ids.group(1), entry
    gfx=[bytearray(4096), bytearray(4096)]
    sources=[None, None]
    if tiles is None:
        tiles=[(le16(copy.group(1), 0), copy.group(2)[0], copy.group(3)[0])
               for copy in TILES.finditer(rom, at-200, at)]
    for address, tile_bank, wram in tiles:
        gfx[wram-1]=copy_tiles(rom, tile_bank, address, 256)
        sources[wram-1]=offset(tile_bank, address)
    palette=PALETTE.search(rom, at, at+0x300)
    palette=offset(bank, le16(palette.group(1), 0))
    ids_at=offset(ids.group(4)[0], le16(ids.group(2), 0))
    attrs_at=offset(attrs.group(4)[0], le16(attrs.group(2), 0))
    size=width*height
    id_data, attr_data=rom[ids_at:ids_at+size], rom[attrs_at:attrs_at+size]
    cropped=bank==0x08 and entry in DIALOGUE or (bank, entry)==(0x05, 0x4ec2)
    if cropped:
        height-=2
        id_data, attr_data=id_data[:width*height], attr_data[:width*height]
    info=dict(loader=f"{bank:02x}:{entry:04x}", width=width, height=height,
              tile_ids=f"0x{ids_at:06x}", attributes=f"0x{attrs_at:06x}",
              graphics=[f"0x{s:06x}" if s is not None else None for s in sources],
              palette=f"0x{palette:06x}")
    if cropped:
        info["note"]="bottom two tile rows (dialogue box) cropped"
    return info, Parts(width, height, id_data, attr_data, gfx, palette)

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path, default=ROOT/"images/screens")
    args=parser.parse_args()
    rom=read_rom("msusa", args.rom_dir)
    dest=args.output/"MSUSA_cutscenes"
    manifest=[]
    for n, (bank, entry, stem, description, *tiles) in enumerate(SCREENS, 1):
        info, parts=decode(rom, bank, entry, *tiles)
        entry_info=dict(index=n, name=stem.replace("_", " "),
                        file=f"{n:02d}_{stem}.png", identification=description,
                        **info)
        manifest.append(save(parts, rom, dest, entry_info))
    (dest/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__=="__main__":
    main()
