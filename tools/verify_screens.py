"""Check export_screens.py against the game's own loaders run in PyBoy.

Each loader is called in isolation; afterwards the BG palette RAM, the VRAM
tiles the screen uses and its tile map (VRAM 9800, or the WRAM planes for the
scrolling US map) must match the ROM decode byte for byte.
"""
import json
from emulator import Machine
from maps import ROOT, read_rom
import export_screens as screens

def run(machine, bank, address, setup=None, frames=300):
    # Like Machine.call, but reports a loader that never returns instead of
    # raising, so the comparison still shows what it managed to load.
    machine.reset()
    if setup:
        setup(machine.p.memory)
    try:
        machine.call(bank, address, frames)
        return True
    except RuntimeError:
        return False

def palette_ram(memory):
    out=bytearray()
    for i in range(64):
        memory[0xff68]=i
        out.append(memory[0xff69])
    return bytes(out)

def palette_found(memory, raw):
    # Loaders do not write palette RAM. They unpack the RGB555 palette into a
    # fade buffer of r,g,b bytes at cc40 (MRA 00:3147 stores 5-bit values,
    # MSUSA 00:2b84 the same values times 8), which the VBlank fade uploads
    # later; interrupts are off here, so check the buffer.
    if palette_ram(memory)==raw:
        return "palette RAM"
    wram=bytes(memory[0xc000:0xd000])
    for scale in (1, 8):
        unpacked=bytearray()
        for i in range(32):
            value=int.from_bytes(raw[i*2:i*2+2], "little")
            unpacked+=bytes(((value>>shift)&31)*scale for shift in (0, 5, 10))
        at=wram.find(unpacked)
        if at>=0:
            return f"fade buffer {0xc000+at:04x}"
    return None

def tile_mismatches(memory, parts):
    bad=set()
    for tile, attr in zip(parts.ids, parts.attrs):
        bank=attr>>3&1
        address=0x9000+tile*16 if tile<0x80 else 0x8800+(tile-0x80)*16
        vram=bytes(memory[bank, address:address+16])
        if vram!=bytes(parts.gfx[bank][tile*16:tile*16+16]):
            bad.add((bank, tile))
    return len(bad)

def bg_mismatches(memory, parts):
    bad=0
    for y in range(min(parts.height, 32)):
        for x in range(min(parts.width, 32)):
            n=y*parts.width+x
            if (memory[0, 0x9800+y*32+x], memory[1, 0x9800+y*32+x])!=(parts.ids[n], parts.attrs[n]):
                bad+=1
    return bad

def wram_mismatches(memory, parts):
    size=parts.width*parts.height
    ids=bytes(memory[2, 0xd000:0xd000+size])
    attrs=bytes(memory[2, 0xd000+size:0xd000+size*2])
    return sum(a!=b for a, b in zip(ids+attrs, parts.ids+parts.attrs))

def check(name, memory, parts, rom, returned, plane, static_palette=None):
    result=dict(name=name, returned=returned,
                palette=palette_found(memory, rom[parts.palette:parts.palette+64]) or static_palette,
                tile_mismatches=tile_mismatches(memory, parts),
                plane_mismatches=plane(memory, parts))
    result["ok"]=bool(result["palette"]) and not result["tile_mismatches"] and not result["plane_mismatches"]
    print(f"{'ok  ' if result['ok'] else 'FAIL'} {name}: returned={returned} "
          f"palette={result['palette']} tiles={result['tile_mismatches']} "
          f"plane={result['plane_mismatches']}", flush=True)
    return result

def main():
    results=[]
    rom=read_rom("mra")
    machine=Machine("mra")
    for (entry, parts), (address, _) in zip(screens.mra_worlds(rom), screens.WORLDS):
        returned=run(machine, 0x0a, address)
        results.append(check(entry["name"], machine.p.memory, parts, rom, returned, bg_mismatches))
    machine.close()

    rom=read_rom("msusa")
    machine=Machine("msusa")
    variants={20: (12, 0x81), 21: (13, 0x81), 22: (12, 0x82)}
    for entry, parts in screens.msusa_cards(rom):
        course, language=variants.get(entry["index"], (entry["index"], 0))
        def setup(memory, course=course, language=language):
            memory[0xce5e]=course
            memory[0xce38]=language
        returned=run(machine, 0x12, 0x52b7, setup)
        results.append(check(f"card {entry['name']}", machine.p.memory, parts, rom, returned, bg_mismatches))
    for progress, label in screens.US_MAPS:
        def setup(memory, progress=progress):
            memory[0xce5e]=progress
        returned=run(machine, 0x09, 0x6252, setup)
        # The map's palette is set by the screen's wider init, not by the
        # loader: 09:6786 is LD B,8 / LD DE,6ce6 / CALL 2b84. Check that code.
        static=("static: 09:6786 loads 09:6ce6"
                if rom[0x26786:0x2678e]==bytes.fromhex("060811e66ccd842b") else None)
        results.append(check(f"US map {label}", machine.p.memory, screens.us_map(rom, progress),
                             rom, returned, wram_mismatches, static))
    machine.close()

    (ROOT/"data/screen_verification.json").write_text(json.dumps(results, indent=2)+"\n")
    failed=[r["name"] for r in results if not r["ok"]]
    print(f"{len(results)-len(failed)}/{len(results)} screens match" + (f"; failed: {failed}" if failed else ""))

if __name__=="__main__":
    main()
