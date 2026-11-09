"""Export full-screen backgrounds: MRA world maps, MSUSA course cards and US map.

Everything is decoded from the user's ROMs; see docs/FORMAT.md for addresses.
The game copies 256 raw tiles per VRAM bank (00:1f82 in MRA, 00:1baa in
MSUSA) into WRAM, then to VRAM 0x8800-0x97ff with signed tile addressing, so
tile id n sits at byte n*16 of each copied block.
"""
import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from maps import ROOT, read_rom, render_tiles

def offset(bank, address):
    return bank*0x4000+address-0x4000

def le16(data, at):
    return int.from_bytes(data[at:at+2], "little")

def copy_tiles(rom, bank, address, count=256):
    # Mirrors the banked copy: crossing 0x8000 continues at the next bank.
    out=bytearray()
    for _ in range(count*16):
        out.append(rom[offset(bank, address)])
        address+=1
        if address==0x8000:
            bank+=1
            address=0x4000
    return out

def colors(rom, at):
    result=[]
    for i in range(32):
        value=le16(rom, at+i*2)
        result.append(tuple(((value>>shift)&31)<<3 for shift in (0, 5, 10)))
    return result

def interleave(ids, attrs):
    pairs=bytearray(len(ids)*2)
    pairs[0::2]=ids
    pairs[1::2]=attrs
    return bytes(pairs)

@dataclass
class Parts:
    """Decoded screen: planes, both VRAM tile blocks, palette offset."""
    width: int
    height: int
    ids: bytes
    attrs: bytes
    gfx: list
    palette: int

    def render(self, rom):
        return render_tiles(self.width, self.height,
                            interleave(self.ids, self.attrs), self.gfx,
                            colors(rom, self.palette))

# MRA world maps, reached from the train station. Hard-coded loaders in bank 0a.
WORLDS=[
    (0x56f3, "Castle"),
    (0x5207, "Pirate"),
    (0x4fea, "Wild West"),
    (0x53f7, "Sweets"),
    (0x4dbe, "Fairground"),
]
PLANES=re.compile(rb"\x06(.)\x21(..)\x11\x00\xd0\x3e(.)\xe0\x94\x0e\x00"
                  rb"(?:\x3e(.)\xe0\x96)?", re.S)
ATTRS=re.compile(rb"\x21(..)\x11\x00\xd4", re.S)
TILES=re.compile(rb"\x21(..)\x11\x00\xd0\x3e(.)\x06(.)\x0e(.)\xcd\x82\x1f", re.S)
PALETTE=re.compile(rb"\x06\x08\x11(..)\xcd\x47\x31", re.S)

def mra_worlds(rom):
    for n, (entry, name) in enumerate(WORLDS, 1):
        code=rom[offset(0x0a, entry):offset(0x0a, entry)+0x140]
        planes=PLANES.search(code)
        height, width=planes.group(1)[0], planes.group(3)[0]
        plane_bank=planes.group(4)[0] if planes.group(4) else 0x0a
        ids_at=offset(plane_bank, le16(planes.group(2), 0))
        attrs_at=offset(plane_bank,
                        le16(ATTRS.search(code, planes.end()).group(1), 0))
        gfx=[bytearray(4096), bytearray(4096)]
        sources=[None, None]
        for copy in TILES.finditer(code):
            bank, wram, count=copy.group(2)[0], copy.group(3)[0], copy.group(4)[0]
            address=le16(copy.group(1), 0)
            gfx[wram-1]=copy_tiles(rom, bank, address, count or 256)
            sources[wram-1]=offset(bank, address)
        palette=offset(0x0a, le16(PALETTE.search(code).group(1), 0))
        size=width*height
        ids, attrs=rom[ids_at:ids_at+size], rom[attrs_at:attrs_at+size]
        bank1=sum(1 for a in attrs if a&8)
        if bank1 and sources[1] is None:
            raise ValueError(f"{name}: {bank1} cells use VRAM bank 1 but no "
                             "bank 1 tiles are loaded")
        yield dict(index=n, name=f"{name} World",
                   file=f"{n:02d}_{name.replace(' ', '_')}_World.png",
                   loader=f"0a:{entry:04x}", width=width, height=height,
                   tile_ids=f"0x{ids_at:06x}", attributes=f"0x{attrs_at:06x}",
                   graphics=[f"0x{s:06x}" if s is not None else None for s in sources],
                   palette=f"0x{palette:06x}"), \
            Parts(width, height, ids, attrs, gfx, palette)

# MSUSA course cards, loader 12:52b7. Card order is ce5e (west to east on the
# US map), not the race catalog order. 20-22 are the French and German name
# variants the loader substitutes for Gulf Coast and Louisiana.
CARDS=["Los Angeles", "Grand Canyon", "Yosemite", "San Francisco", "Seattle",
       "Montana", "Yellowstone", "Utah", "Milwaukee", "Colorado", "Nebraska",
       "Texas", "Gulf Coast", "Louisiana", "Indianapolis", "Boston",
       "Smoky Mountains", "Florida Everglades", "Daytona Beach",
       "Washington D.C.", "Golfe du Mexique", "Louisiane", "Golfküste"]
CARD_PALETTE={20: 12, 21: 13, 22: 12}  # palette index stays ce5e

def far_be(rom, at):
    bank, high, low=rom[at:at+3]
    return bank, high<<8|low

def msusa_cards(rom):
    for card, name in enumerate(CARDS):
        gfx=[]
        sources=[]
        for k in (0, 3):
            bank, address=far_be(rom, offset(0x12, 0x6923)+card*6+k)
            gfx.append(copy_tiles(rom, bank, address))
            sources.append(offset(bank, address))
        planes=[offset(*far_be(rom, offset(0x12, 0x69ad)+card*6+k)) for k in (0, 3)]
        index=CARD_PALETTE.get(card, card)
        palette=offset(0x12, le16(rom, offset(0x12, 0x6a37)+index*2))
        ids, attrs=(rom[at:at+20*18] for at in planes)
        stem=name.replace(" ", "_").replace(".", "").replace("ü", "ue")
        filename=f"{card+1:02d}_{stem}.png"
        yield dict(index=card, name=name, file=filename, loader="12:52b7",
                   width=20, height=18, tile_ids=f"0x{planes[0]:06x}",
                   attributes=f"0x{planes[1]:06x}",
                   graphics=[f"0x{s:06x}" for s in sources],
                   palette=f"0x{palette:06x}"), \
            Parts(20, 18, bytes(ids), bytes(attrs), gfx, palette)

# MSUSA US map, loader 09:628d. 09:63b0 then draws a 2x2 marker per state by
# overwriting the graphics of the map's placeholder tiles, which show as plain
# squares in the raw ROM data. A state is drawn reached (table 6479) when its
# index is at most the progress byte ce5e, else unreached (table 64a1).
def us_map(rom, progress):
    ids=bytearray(rom[0x27016:0x27016+0x460])
    attrs=bytearray(rom[0x27476:0x27476+0x460])
    gfx=[copy_tiles(rom, 0xa0, 0x5730), copy_tiles(rom, 0xa0, 0x6730)]
    for state in range(20):
        table=0x6479 if state<=progress else 0x64a1
        slot=rom[offset(0x09, 0x64f1)+state]>>2
        source=le16(rom, offset(0x09, table)+slot*2)
        target=le16(rom, offset(0x09, 0x64c9)+slot*2)
        for sub in range(4):
            src=source+(sub&1)+(0x14 if sub&2 else 0)
            cell=target+(sub&1)+(0x28 if sub&2 else 0)
            vram_bank=attrs[cell]>>3&1
            attrs[cell]=attrs[cell]&0x98|rom[offset(0x09, 0x7aa2+src)]&0x67
            tile=rom[offset(0x09, 0x78d6+src)]
            graphic=copy_tiles(rom, 0xa0+(0x1200+tile*16)//0x4000,
                               0x4000+(0x1200+tile*16)%0x4000, 1)
            gfx[vram_bank][ids[cell]*16:ids[cell]*16+16]=graphic
    return Parts(40, 28, bytes(ids), bytes(attrs), gfx, offset(0x09, 0x6ce6))

US_MAPS=[(0, "Start"), (19, "Complete")]  # (ce5e, label)

def save(parts, rom, dest, entry):
    image=parts.render(rom)
    dest.mkdir(parents=True, exist_ok=True)
    image.save(dest/entry["file"])
    entry["sha256"]=hashlib.sha256((dest/entry["file"]).read_bytes()).hexdigest()
    print(f"{dest.name}/{entry['file']} {image.width}x{image.height}", flush=True)
    return entry

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rom-dir", type=Path, default=ROOT/"local")
    parser.add_argument("--output", type=Path, default=ROOT/"images/screens")
    args=parser.parse_args()
    groups={}
    rom=read_rom("mra", args.rom_dir)
    groups["MRA_worlds"]=[save(parts, rom, args.output/"MRA_worlds", e)
                          for e, parts in mra_worlds(rom)]
    rom=read_rom("msusa", args.rom_dir)
    groups["MSUSA_cards"]=[save(parts, rom, args.output/"MSUSA_cards", e)
                           for e, parts in msusa_cards(rom)]
    groups["MSUSA_us_map"]=[
        save(us_map(rom, progress), rom, args.output/"MSUSA_us_map",
             dict(index=n, name=f"US map, {label.lower()}",
                  file=f"{n+1:02d}_US_Map_{label}.png",
                  loader="09:6252", width=40, height=28, tile_ids="0x027016",
                  attributes="0x027476", graphics=["0x281730", "0x282730"],
                  palette="0x026ce6", markers="09:63b0", progress=progress))
        for n, (progress, label) in enumerate(US_MAPS)]
    for name, manifest in groups.items():
        (args.output/name/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")

if __name__=="__main__":
    main()
