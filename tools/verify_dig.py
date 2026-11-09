"""Check export_dig.py against the game's own stage loader run in PyBoy.

The dig engine only runs after Pluto enters a hole, so this replays that from
a local save state (Pluto standing over a dug hole in town, made with the
user's own save file) and forces the stage index ff fe when f0:416c starts
the load. For every stage it checks, against the ROM decode:

- WRAM banks 1-4 when the build is done (f0:41f8): the metatile grid,
- the faded-in BG palette buffer c256 (hardware palettes 4-7 are read too;
  0-3 are swapped for the HUD mid-frame),
- every BG tile the stage uses in VRAM: static tiles must equal the
  graphics block, animated groups must equal one of their f7 frames.
"""
import argparse
import io
import json
import sys
from maps import ROOT, read_rom
import export_dig as dig

sys.path.insert(0, str(ROOT/"local/tools/python"))
from pyboy import PyBoy

def wram_rows(pairs, width):
    """Lay the tile grid out the way the builder stores it in banks 1-4."""
    banks=[bytearray() for _ in range(4)]
    cells=width*(len(pairs)//2//(width*16))
    for i in range(cells):
        for r in range(4):
            y=(i//width)*4+r
            x=(i%width)*4
            n=(y*width*4+x)*2
            banks[r]+=pairs[n:n+8]
    return [bytes(b) for b in banks]

def raw_fade(rom, at):
    out=bytearray()
    for i in range(32):
        value=dig.le16(rom, at+i*2)
        shown=0
        for shift in (0, 5, 10):
            shown|=(((value>>shift)&31)*245+128>>8)<<shift
        out+=bytes([shown&255, shown>>8])
    return bytes(out)

def main():
    parser=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state",
                        default=str(ROOT/"local/research/mra/dug.state"))
    parser.add_argument("--sram", default=str(ROOT/"local/MMRACINGADV.srm"))
    args=parser.parse_args()
    rom=read_rom("mra")
    path=next((ROOT/"local").glob("*Racing*.gbc"))
    sram=bytearray(open(args.sram, "rb").read())
    sram+=bytes(128*1024-len(sram))
    p=PyBoy(str(path), window="null", sound_emulated=False,
            ram_file=io.BytesIO(bytes(sram)), log_level="ERROR")
    p.set_emulation_speed(0)
    m=p.memory
    current={}
    def force(_):
        m[0xfffe]=current["index"]
    def built(_):
        current["banks"]=[bytes(m[b, 0xd000:0xd000+current["size"]])
                          for b in (1, 2, 3, 4)]
    p.hook_register(0xf0, 0x416c, force, None)
    p.hook_register(0xf0, 0x41f8, built, None)
    def hold(key, frames):
        p.button_press(key)
        p.tick(frames, False)
        p.button_release(key)
    results=[]
    ok_all=True
    for index in range(dig.WORLDS*4):
        entry, pairs, gfx, _=dig.decode(rom, index)
        width=entry["width"]//32
        current.clear()
        current.update(index=index, size=len(pairs)//4)
        with open(args.state, "rb") as f:
            p.load_state(f)
        for _ in range(12):           # walk Pluto down into the hole
            hold("down", 8)
            p.tick(2, False)
            if m[0xc000]!=1:
                break
        p.tick(600, False)            # title card
        hold("a", 4)
        p.tick(600, False)
        banks_ok=current.get("banks")==wram_rows(pairs, width)
        palette_ok=bytes(m[0xc256:0xc296])==raw_fade(rom, int(entry["palette"], 16))
        hw=bytearray()
        for i in range(64):
            m[0xff68]=i
            hw.append(m[0xff69])
        hardware_ok=bytes(hw[32:])==raw_fade(rom, int(entry["palette"], 16))[32:]
        # VRAM bank 0, 8800-97ff, re-indexed by unsigned tile id.
        live=bytes(m[0, 0x8800:0x97ff])+bytes([m[0, 0x97ff]])
        vram=live[0x800:]+live[:0x800]
        static=bytes(gfx[0])
        animated={}
        for (slot, frames), key in zip(dig.ANIMATIONS, ("bone", "item")):
            tile=int(entry["animated_tiles"][key], 16)
            options={rom[dig.offset(0xf7, a):dig.offset(0xf7, a)+64] for a in frames}
            animated.update({tile+k: (options, k) for k in range(4)})
        used=sorted({pairs[i] for i in range(0, len(pairs), 2)})
        bad=[]
        for t in used:
            tile=vram[t*16:t*16+16]
            if t in animated:
                options, k=animated[t]
                group=vram[(t-k)*16:(t-k)*16+64]
                if group not in options:
                    bad.append(t)
            elif tile!=static[t*16:t*16+16]:
                bad.append(t)
        ok=banks_ok and palette_ok and hardware_ok and not bad
        ok_all&=ok
        results.append(dict(index=index, name=dig.NAMES[index],
                            metatiles=banks_ok, palette=palette_ok,
                            hardware_palettes_4_7=hardware_ok,
                            tiles_checked=len(used),
                            tile_mismatches=[f"0x{t:02x}" for t in bad], ok=ok))
        print(f"{'ok  ' if ok else 'FAIL'} stage {index:02d}: metatiles={banks_ok} "
              f"palette={palette_ok} hw4-7={hardware_ok} tiles={len(used)} bad={bad}",
              flush=True)
    p.stop(save=False)
    (ROOT/"data/dig_verification.json").write_text(json.dumps(results, indent=2)+"\n")
    print(f"{sum(r['ok'] for r in results)}/{len(results)} stages match")
    sys.exit(0 if ok_all else 1)

if __name__=="__main__":
    main()
