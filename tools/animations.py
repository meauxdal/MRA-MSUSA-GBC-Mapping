"""Recover course tile-animation streams and their native accumulator timing.

Metadata contains pointers, not ROM graphics. One tick is one nominal gameplay
update (70224 / 4194304 seconds); gameplay stalls and pauses are not reproduced.
"""
import argparse
import json
import math
from maps import ROOT, CONFIG, read_rom, courses
from emulator import Machine

TICK_SECONDS = 70224 / 4194304
# MSUSA mode flag ce60 is set to 1 by a menu routine (09:5918) before racing;
# with 0, Nebraska's windmills stay still. Normal play has them spinning. MRA
# keeps its previous capture value.
CE60 = {"mra": 0, "msusa": 1}
ROUTINES = {
    "mra": dict(bank=30, init=0x4045, update=0x421f, selector=0xce7b,
                helpers=[(30,0x453e),(31,0x6578)], upload=0x1477),
    "msusa": dict(bank=16, init=0x404b, update=0x41e2, selector=0xce8c,
                  helpers=[(16,0x4407),(17,0x7f95),(23,0x48f9)], upload=0x10e5),
}


def initialize(machine, game, index):
    machine.reset()
    p=machine.p
    cfg=ROUTINES[game]
    p.memory[0xff40]=0
    p.memory[cfg["selector"]]=index
    p.memory[0xce60]=CE60[game]
    if game=="msusa":
        # A canonical steady-state loop must not inherit boot/menu RAM. The ROM
        # initializer resets only nine frame-index bytes, although Yellowstone
        # uses twelve streams. Preserve its accumulator phases after clearing.
        p.memory[0xff70]=5
        p.memory[0xdca0:0xdcb8]=[0]*24
    machine.call(cfg["bank"],cfg["init"])


def prepare_update(p, game):
    # Prevent upload queues from accumulating across isolated calls. The hooks
    # observe requests at routine entry, before queueing or immediate transfer.
    if game=="msusa":
        p.memory[0xc636]=0
        p.memory[0xc637]=255
        p.memory[0xc4a2]=0
    else:
        p.memory[0xc65e]=0
        p.memory[0xc65f]=0


def collect(game):
    rom=read_rom(game)
    cfg=ROUTINES[game]
    machine=Machine(game)
    p=machine.p
    result={}
    try:
        for course in courses(game,rom):
            initialize(machine,game,course.index)
            streams=[]

            def inspect(bank):
                z=p.register_file
                offset=bank*0x4000+z.D*256+z.E-0x4000
                dest,tiles,n=rom[offset:offset+3]
                sources=[int.from_bytes(rom[offset+3+i*2:offset+5+i*2],"little") for i in range(n)]
                if not (z.A and 0<n<=32 and tiles and dest+tiles<=256
                        and all(0x4000<=s and s+tiles*16<=0x8000 for s in sources)):
                    raise ValueError(f"Unsupported animation stream at {offset:#x}")
                streams.append(dict(bank=bank,table=offset,counter=z.HL,
                    initial_accumulator=p.memory[z.HL],initial_frame=p.memory[z.HL+1],
                    speed=z.A,dest=0x9000+dest*16,tiles=tiles,vram_bank=0,sources=sources,
                    period_ticks=256*n//math.gcd(z.A,256*n)))

            for bank,address in cfg["helpers"]:
                signature=rom[bank*0x4000+address-0x4000:bank*0x4000+address-0x4000+5]
                if signature!=bytes.fromhex("8622304134"):
                    raise ValueError("Unsupported animation helper revision")
                p.hook_register(bank,address,inspect,bank)
            try:
                prepare_update(p,game)
                machine.call(cfg["bank"],cfg["update"])
            finally:
                for bank,address in cfg["helpers"]:
                    p.hook_deregister(bank,address)
            occupied=set()
            for stream in streams:
                region=set(range(stream["dest"],stream["dest"]+stream["tiles"]*16))
                if region & occupied:
                    raise ValueError("Overlapping streams need ordered upload replay")
                occupied.update(region)
            period=math.lcm(*(s["period_ticks"] for s in streams)) if streams else 0
            result[str(course.index)]=dict(period_ticks=period,streams=streams)
            print(f"{game}:{course.index:02d}: {len(streams)} streams, {period} update ticks",flush=True)
    finally:
        machine.close()
    return result


def state_at(animation, tick):
    return tuple((s["initial_frame"]+(s["initial_accumulator"]+tick*s["speed"])//256)%len(s["sources"])
                 for s in animation["streams"])


def patches_at(animation, tick):
    return [dict(dest=s["dest"],tiles=s["tiles"],vram_bank=s["vram_bank"],bank=s["bank"],source=s["sources"][frame])
            for s,frame in zip(animation["streams"],state_at(animation,tick))]


def timeline(animation):
    period=animation["period_ticks"]
    if period>10000:
        raise ValueError(f"Refusing unbounded animation export: {period} ticks")
    if not period:
        return []
    boundaries=[0]
    previous=state_at(animation,0)
    for tick in range(1,period):
        state=state_at(animation,tick)
        if state!=previous:
            boundaries.append(tick)
            previous=state
    return list(zip(boundaries,boundaries[1:]+[period]))


def metadata_path():
    return ROOT/"data"/"animation_sequences.json"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    games=list(CONFIG)
    report=dict(tick_cycles=70224,clock_hz=4194304,
        timing="Nominal one animation update per display frame; no gameplay lag or pauses.",
        initialization="ROM initializer accumulator phases; canonical frame-zero indices, without inherited boot/menu RAM.",
        rom_sha256={g:CONFIG[g]["sha256"] for g in games},
        games={g:collect(g) for g in games})
    metadata_path().write_text(json.dumps(report,indent=2)+"\n")


if __name__=="__main__":
    main()
