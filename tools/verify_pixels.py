"""Validate exported pixels against PyBoy's CGB rasterizer, with sprites disabled.

Three terrain windows per course exercise the exact exported PNG, both tile
banks, RGB555 palette conversion, and CGB horizontal/vertical flip attributes.
This deliberately validates the background layer, not full gameplay scenes.
"""
import json
import sys
from PIL import Image
from maps import ROOT,CONFIG,read_rom,courses,animation_patches
from emulator import Machine
import numpy as np

def check(game, *, extras=False):
    machine=Machine(game)
    p=machine.p
    report=[]
    catalog=json.loads((ROOT/"data/catalog.json").read_text())[game]
    if extras:
        catalog=json.loads((ROOT/"data/msusa_extras.json").read_text())
    patches={} if extras else animation_patches(game)
    try:
        for course in courses(game,read_rom(game),include_extras=extras):
            if extras and course.index<21:
                continue
            missing=set()
            pairs=np.frombuffer(course.tile_pairs(missing),dtype=np.uint8).reshape(course.height*4,course.width*4,2)
            gfx,_=course.graphics(patches.get(str(course.index),[]))
            group=game.upper()+("_extras" if extras else "")
            exported=Image.open(ROOT/"images/reconstructed"/group/catalog[str(course.index)]["filename"]).convert("RGBA")
            samples=[(0,0),(course.width*2,course.height*2),(course.width*4-32,course.height*4-32)]
            total=0
            for x,y in samples:
                machine.reset()
                p.memory[0xff40]=0
                for bank in (0,1):
                    p.memory[0xff4f]=bank
                    p.memory[0x9000:0x9800]=list(gfx[bank][:2048])
                    p.memory[0x8800:0x9000]=list(gfx[bank][2048:])
                    p.memory[0x9800:0x9c00]=pairs[y:y+32,x:x+32,bank].flatten().tolist()
                for i,value in enumerate(course.rom[course.palette_offset:course.palette_offset+64]):
                    p.memory[0xff68]=i
                    p.memory[0xff69]=value
                p.memory[0xff42]=0
                p.memory[0xff43]=0
                p.memory[0xff4b]=167
                p.memory[0xff4f]=0
                p.register_file.PC=0x100
                p.memory[0xff40]=0x81
                p.tick(3,True)
                actual=np.array(p.screen.image.convert("RGB"))
                wanted=np.array(exported.crop((x*8,y*8,x*8+160,y*8+144)))
                # Lookups outside the ROM have no source data to emulate;
                # they are either transparent or an observed fill (maps.py).
                valid=wanted[:,:,3]!=0
                for t in missing:
                    ty,tx=divmod(t,course.width*4)
                    if x<=tx<x+20 and y<=ty<y+18:
                        valid[(ty-y)*8:(ty-y)*8+8,(tx-x)*8:(tx-x)*8+8]=False
                unequal=np.any(actual!=wanted[:,:,:3],axis=2)&valid
                if unequal.any():
                    pos=np.argwhere(unequal)[0]
                    raise AssertionError(f"{game}:{course.index} {unequal.sum()} pixel mismatches in window ({x},{y}); first {pos.tolist()}")
                total+=int(valid.sum())
            report.append(dict(index=course.index,windows=len(samples),pixels=total,result="exact"))
            print(f"PASS {game}:{course.index:02d}: {total} exported RGB pixels",flush=True)
    finally:
        machine.close()
    return report

def main():
    report={"method":"Three windows per course rendered by PyBoy 2.9.0 with original tile bytes/palettes and sprites disabled.",
            "limits":"Background rasterization check; source-plane indexing is checked separately against original ROM code. Does not prove gameplay state, sprites, animation timing, or all map pixels.",
            "games":{game:check(game) for game in CONFIG}}
    (ROOT/"data/pixel_verification.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    main()
