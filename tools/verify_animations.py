"""Check recovered timing against original ROM updates over complete cycles."""
import argparse
import json
from animations import ROUTINES, metadata_path, initialize, prepare_update, patches_at, state_at
from emulator import Machine
from maps import ROOT


def check(game, entries, special=False):
    machine=Machine(game)
    p=machine.p
    cfg=ROUTINES[game]
    report=[]
    events=[]

    def upload(_):
        z=p.register_file
        events.append(dict(dest=z.B*256+z.C,bank=z.D,source=z.HL,vram_bank=z.A,tiles=z.E))

    p.hook_register(0,cfg["upload"],upload,None)
    try:
        for key,animation in entries.items():
            index=int(key)
            initialize(machine,game,index,special)
            period=animation["period_ticks"]
            uploads=0
            for tick in range(1,max(1,period)+1):
                events.clear()
                prepare_update(p,game)
                machine.call(cfg["bank"],cfg["update"])
                if game=="msusa":
                    p.memory[0xff70]=5
                expected=[]
                for stream,frame,patch in zip(animation["streams"],state_at(animation,tick),patches_at(animation,tick)):
                    acc=(stream["initial_accumulator"]+tick*stream["speed"])%256
                    addr=stream["counter"]
                    if (p.memory[addr],p.memory[addr+1])!=(acc,frame):
                        raise AssertionError(f"{game}:{index} tick {tick}: counter/frame differs")
                    if acc<stream["speed"]:
                        expected.append(patch)
                if events!=expected:
                    raise AssertionError(f"{game}:{index} tick {tick}: uploads differ: {events} != {expected}")
                uploads+=len(events)
            report.append(dict(index=index,ticks=max(1,period),uploads=uploads,result="exact"))
            print(f"PASS {game}:{index:02d}: {max(1,period)} original updates, {uploads} uploads",flush=True)
    finally:
        p.hook_deregister(0,cfg["upload"])
        machine.close()
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--special",action="store_true")
    args=parser.parse_args()
    metadata=json.loads(metadata_path(args.special).read_text())
    result=dict(method="Compare every accumulator, frame index and upload request with original ROM code over one complete combined cycle per course.",
        limits="Isolated nominal updates; excludes gameplay stalls, MRA LY gate skips, sprites and runtime map edits.",
        games={game:check(game,entries,args.special) for game,entries in metadata["games"].items()})
    suffix="_special" if args.special else ""
    (ROOT/"data"/f"animation_verification{suffix}.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":
    main()
