"""Recover frame-zero background uploads by executing original animation code.

Only pointer metadata is written; ROM bytes and emulator states stay private.
"""
import argparse
import json
from emulator import Machine
from maps import ROOT,CONFIG
from animations import CE60

def trace(game):
    machine=Machine(game)
    p=machine.p
    result={}
    try:
        for level in range(CONFIG[game]["count"]):
            if game=="mra" and level==7:
                continue
            machine.reset()
            p.memory[0xff40]=0
            if game=="mra":
                p.memory[0xce7b]=level
                for address in [0xc6fb,0xc6fc,*range(0xc840,0xc852)]:
                    p.memory[address]=255
                bank,address,dma=30,0x421f,0x1477
            else:
                p.memory[0xce8c]=level
                p.memory[0xce60]=CE60[game]
                p.memory[0xff70]=5
                for address in range(0xdca0,0xdcb8):
                    p.memory[address]=255
                bank,address,dma=16,0x41e2,0x10e5
            events=[]
            def callback(_):
                z=p.register_file
                events.append(dict(dest=z.B*256+z.C,bank=z.D,source=z.HL,vram_bank=z.A,tiles=z.E))
            p.hook_register(0,dma,callback,None)
            try:
                machine.call(bank,address)
            finally:
                p.hook_deregister(0,dma)
            result[str(level)]=events
            print(f"{game}:{level:02d}: {len(events)} animation uploads",flush=True)
    finally:
        machine.close()
    (ROOT/"data"/f"{game}_animations.json").write_text(json.dumps(result,indent=2)+"\n")

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",choices=["mra","msusa","all"],default="all")
    args=parser.parse_args()
    for game in (["mra","msusa"] if args.game=="all" else [args.game]):
        trace(game)
