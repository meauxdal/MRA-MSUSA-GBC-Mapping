"""Compare exported map indexing against both games' original renderer routines."""
import json
from maps import ROOT,CONFIG,read_rom,courses
from emulator import Machine

def check(game, *, extras=False):
    machine=Machine(game)
    p=machine.p
    checks=[]
    try:
        for c in courses(game,read_rom(game),include_extras=extras):
            if extras and c.index<21:
                continue
            missing=set()
            expected=c.tile_pairs(missing)
            # Each test calls the original horizontal renderer, including row
            # lookup, WRAM banking, 4x4 metatile addressing and tile attributes.
            samples=[(0,0),(1,1),(2,2),(3,3),
                     (c.width*2,c.height*2),(c.width*4-27,c.height*4-1)]
            compared=0
            for x,y in samples:
                machine.reset()
                for plane,offset in enumerate((c.low_offset,c.high_offset)):
                    raw=c.rom[offset+2:offset+2+c.width*c.height]
                    for chunk in range(2):
                        p.memory[0xff70]=1+plane+chunk*2
                        block=raw[chunk*4096:(chunk+1)*4096]
                        if block:
                            p.memory[0xd000:0xd000+len(block)]=list(block)
                for row in range(c.height):
                    offset=row*c.width
                    dest=0xc8d2+row*3
                    p.memory[dest:dest+3]=[1+(offset//4096)*2,0xd0+(offset%4096)//256,offset%256]
                field=0xc634 if game=="mra" else 0xc614
                p.memory[field:field+3]=[c.metatile_bank,c.width,c.height]
                p.register_file.B=x>>8
                p.register_file.C=x&255
                p.register_file.D=y>>8
                p.register_file.E=y&255
                machine.call(0,0x1a40 if game=="mra" else 0x1622)
                # The routine processes 27-x%4 tiles in its unrolled loop.
                count=27-x%4
                for k in range(count):
                    tile=y*c.width*4+x+k
                    if tile in missing:
                        continue
                    actual=bytes([p.memory[0xc7a0+k],p.memory[0xc8a0+k]])
                    wanted=expected[tile*2:tile*2+2]
                    if actual!=wanted:
                        raise AssertionError(f"{game}:{c.index} ({x+k},{y}) emulator={actual.hex()} decoder={wanted.hex()}")
                    compared+=1
            checks.append(dict(index=c.index,samples=len(samples),tile_attribute_pairs=compared,unmapped=len(missing)))
            print(f"PASS {game}:{c.index:02d}: {compared} original-renderer tile/attribute pairs",flush=True)
    finally:
        machine.close()
    return checks

def main():
    report={"method":"Isolated original-ROM horizontal renderer; six coordinate samples per course.",
            "limits":"Validates background tile IDs/attributes, not every rendered pixel, objects, or gameplay state.",
            "rom_sha256":{game:cfg["sha256"] for game,cfg in CONFIG.items()},
            "games":{game:check(game) for game in CONFIG}}
    out=ROOT/"data/verification.json"
    out.write_text(json.dumps(report,indent=2)+"\n")
    print(f"Wrote {out}")

if __name__=="__main__":
    main()
