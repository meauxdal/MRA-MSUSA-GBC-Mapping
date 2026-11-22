"""Check export_sprites.py against the game running in PyBoy.

1. Every exported sheet is re-rendered from the ROM and must match its
   manifest hash.
2. The game's own OAM is compared with the ROM tables. Savestates are not part
   of the repository, so this step reads whatever local/research/mra/*.state
   files exist (town and Pluto scenes) and then walks Mickey in each direction
   from the first state that has him. A live frame matches a ROM frame when the
   OAM entries (relative position, attribute), their tile ids (2i, 2i+1) and
   the VRAM tile bytes all equal the table, and the OBJ palettes in use equal
   the ROM palette set.
"""
import hashlib
import io
import json
import sys
from maps import ROOT, read_rom
import export_sprites as sprites

sys.path.insert(0, str(ROOT/"local/tools/python"))
from pyboy import PyBoy


def table_frames(rom):
    frames=[]
    for _, _, tables in sprites.SHEETS:
        for bank, address in tables:
            frames.extend(sprites.read_table(rom, bank, address))
    return frames


def check_sheets(rom, palettes):
    manifest=json.loads((ROOT/"images/sprites/MRA/manifest.json").read_text())
    bad=0
    for entry in manifest:
        frames=[]
        seen=set()
        for _, _, tables in [s for s in sprites.SHEETS
                             if s[0].replace("_", " ")==entry["name"]]:
            for bank, address in tables:
                for frame in sprites.read_table(rom, bank, address):
                    key=sprites.frame_key(rom, frame)
                    if key not in seen:
                        seen.add(key)
                        frames.append(frame)
        image, _, _=sprites.sheet(rom, palettes, frames)
        path=ROOT/"images/sprites/MRA"/entry["file"]
        ok=(len(frames)==len(entry["frames"])
            and hashlib.sha256(path.read_bytes()).hexdigest()==entry["sha256"]
            and image.tobytes()==sprites.Image.open(path).convert("RGBA").tobytes())
        if not ok:
            bad+=1
            print("MISMATCH", entry["file"])
    print(f"sheets: {len(manifest)-bad}/{len(manifest)} match the ROM")
    return bad


def live(p):
    m=p.memory
    sprites_=[]
    for i in range(40):
        y, x, tile, attr=(m[0xfe00+i*4+k] for k in range(4))
        if 0<y<160 and 0<x<168:
            sprites_.append((y, x, tile, attr))
    palette=[]
    for i in range(64):
        m[0xff6a]=i
        palette.append(m[0xff6b])
    vram=[bytes(m[b, 0x8000:0x9800]) for b in (0, 1)]
    return sprites_, bytes(palette), vram


def match(rom, frames, state):
    sprites_, palette, vram=state
    if not sprites_:
        return None
    y0, x0, t0, _=sprites_[0]
    for frame in frames:
        entries=frame["entries"]
        if len(entries)!=len(sprites_):
            continue
        ok=True
        for i, ((dy, dx, attr), (y, x, tile, live_attr)) in enumerate(
                zip(entries, sprites_)):
            if (attr!=live_attr or tile!=t0+2*i
                    or (y-y0)&255!=(sprites.signed(dy)-sprites.signed(entries[0][0]))&255
                    or (x-x0)&255!=(sprites.signed(dx)-sprites.signed(entries[0][1]))&255):
                ok=False
                break
            bank=attr>>3&1
            data=rom[frame["data"]+i*32:frame["data"]+i*32+32]
            if vram[bank][tile*16:tile*16+32]!=data:
                ok=False
                break
        if ok:
            for _, _, _, attr in sprites_:
                p=attr&7
                if palette[p*8:p*8+8]!=rom[sprites.PALETTE_AT+p*8:
                                           sprites.PALETTE_AT+p*8+8]:
                    return (frame, False)
            return (frame, True)
    return None


def main():
    rom=read_rom("mra")
    palettes=sprites.read_palettes(rom)
    failures=check_sheets(rom, palettes)
    states=sorted((ROOT/"local/research/mra").glob("*.state"))
    if not states:
        print("no savestates in local/research/mra: emulator check skipped")
        return failures
    frames=table_frames(rom)
    rom_path=next((ROOT/"local").glob("*Racing Adventure*.gbc"))
    p=PyBoy(str(rom_path), window="null", sound_emulated=False,
            ram_file=io.BytesIO(bytes(128*1024)), log_level="ERROR")
    p.set_emulation_speed(0)
    hits, misses, palette_bad=set(), [], 0
    walker=None
    for path in states:
        p.load_state(path.open("rb"))
        p.tick(30, False)
        state=live(p)
        if not state[0]:
            continue
        result=match(rom, frames, state)
        if result is None:
            misses.append(path.name)
            continue
        hits.add((result[0]["table"], result[0]["index"]))
        palette_bad+=not result[1]
        if walker is None and result[0]["table"].startswith("6d:7"):
            walker=path
    print(f"states: {len(hits)} distinct ROM frames seen in OAM; "
          f"no ROM match for: {', '.join(misses) or 'none'}")
    if walker:
        walked=set()
        p.load_state(walker.open("rb"))
        p.tick(10, False)
        for button in ("down", "left", "up", "right"):
            p.button_press(button)
            for _ in range(60):
                p.tick(1, False)
                result=match(rom, frames, live(p))
                if result:
                    walked.add((result[0]["table"], result[0]["index"]))
                    palette_bad+=not result[1]
            p.button_release(button)
            p.tick(5, False)
        print(f"walking from {walker.name}: {len(walked)} distinct ROM frames seen")
        failures+=len(walked)<40
    failures+=palette_bad
    print(f"palette mismatches: {palette_bad}")
    p.stop(save=False)
    print("OK" if not failures else f"FAILED ({failures})")
    return failures


if __name__=="__main__":
    sys.exit(1 if main() else 0)
