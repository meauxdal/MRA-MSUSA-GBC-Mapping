"""Bounded source-decoding checks for MSUSA's four additional map slots.

Passing does not resolve slot 23's graphics or establish gameplay reachability.
The regular loader is called in isolation with LCD enabled for its VBlank waits.
"""
import json
from emulator import Machine
from maps import ROOT, CONFIG, read_rom, courses
from verify_maps import check as check_maps
from verify_pixels import check as check_pixels


def check_loader():
    machine=Machine("msusa")
    p=machine.p
    results=[]
    try:
        for course in courses("msusa",read_rom("msusa"),include_extras=True):
            if course.index<21:
                continue
            machine.reset()
            p.memory[0xff40]=0x81
            p.memory[0xce8c]=course.index
            events=[]
            staged=[]

            def upload(_):
                z=p.register_file
                events.append(dict(bank=z.A,source=z.HL,wram_bank=z.B))

            def inspect(_):
                # The two declared graphics resources have been staged in WRAM,
                # before the real transfer routine overwrites the map planes.
                graphics,lengths=course.graphics()
                for bank,offset in enumerate(course.graphics_offsets):
                    if offset is None:
                        continue
                    p.memory[0xff70]=bank+1
                    n=lengths[bank]
                    actual=bytes(p.memory[0xd000:0xd000+n])
                    if actual!=graphics[bank][:n]:
                        raise AssertionError(f"Extra {course.index}: staged graphics bank {bank}")
                    staged.append(dict(vram_bank=bank,bytes=n))

            p.hook_register(0,0x1bbd,upload,None)
            p.hook_register(0,0x1999,inspect,None)
            try:
                machine.call(0,0x1921,max_frames=30)
            finally:
                p.hook_deregister(0,0x1bbd)
                p.hook_deregister(0,0x1999)
            if len(staged)!=sum(o is not None for o in course.graphics_offsets):
                raise AssertionError("Graphics staging hook did not run")
            if bytes(p.memory[0xc614:0xc617])!=bytes((course.metatile_bank,course.width,course.height)):
                raise AssertionError(f"Extra {course.index}: loaded dimensions/metatile bank")
            for plane,offset in enumerate((course.low_offset,course.high_offset)):
                n=course.width*course.height
                p.memory[0xff70]=plane+1
                if bytes(p.memory[0xd000:0xd000+n])!=course.rom[offset+2:offset+2+n]:
                    raise AssertionError(f"Extra {course.index}: loaded map plane {plane}")
            missing=set()
            pairs=course.tile_pairs(missing)
            _,lengths=course.graphics()
            undefined=sum(1 for t in range(len(pairs)//2) if t not in missing
                          and pairs[t*2]*16>=lengths[(pairs[t*2+1]>>3)&1])
            results.append(dict(index=course.index,staged_graphics=staged,
                loaded_map_plane_bytes=course.width*course.height*2,
                loader_graphics_reads=events,unloaded_graphics_tile_uses=undefined,
                unmapped_subtiles=len(missing)))
            print(f"PASS extra {course.index}: original loader planes and declared graphics",flush=True)
    finally:
        machine.close()
    return results


def main():
    report=dict(method="Isolated original regular loader, six renderer samples and three CGB raster windows per extra slot.",
        limits="Source-decoding checks only. Slot 23 remains visually scrambled; slot 24 has non-ROM reads. Names, reachability, alternative loaders, objects and runtime changes remain unverified.",
        rom_sha256=CONFIG["msusa"]["sha256"],
        loader=check_loader(),renderer=check_maps("msusa",extras=True),
        pixels=check_pixels("msusa",extras=True))
    (ROOT/"data/msusa_extras_verification.json").write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    main()
