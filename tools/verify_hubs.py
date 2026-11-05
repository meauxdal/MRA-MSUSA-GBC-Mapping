"""Compare all six hub decompressions against the game's original RAM routines."""
import json
from maps import ROOT,read_rom
from hubs import hubs,decode_graphics,le16
from emulator import Machine

def prepare(machine,data):
    machine.reset()
    p=machine.p
    p.memory[0xff40]=0  # The real loader disables LCD access restrictions.
    p.memory[0xc020:0xc0c0]=list(data[0x198000:0x1980a0])
    p.memory[0xc200:0xc700]=list(data[0x190000:0x190500])

def main():
    data=read_rom("mra")
    machine=Machine("mra")
    p=machine.p
    report=[]
    try:
        for hub in hubs(data):
            prepare(machine,data)
            base=hub.map_offset//0x4000*0x4000-0x4000
            pointer=hub.map_offset-base
            p.register_file.B=le16(data,hub.map_offset+3)>>8
            p.register_file.C=le16(data,hub.map_offset+3)&255
            p.register_file.D=(pointer+7)>>8
            p.register_file.E=(pointer+7)&255
            p.register_file.HL=le16(data,hub.map_offset+5)
            machine.call(hub.map_offset//0x4000,0xc4d5,max_frames=120)
            planes=[]
            for start in (2,5):
                plane=bytearray()
                for b in range(start,start+3):
                    p.memory[0xff70]=b
                    plane+=bytes(p.memory[0xd000:0xe000])
                planes.append(plane[:hub.width*hub.height])
            expected=hub.tile_pairs()
            assert planes[0]==expected[1::2],f"Hub {hub.index} attributes differ"
            assert planes[1]==expected[0::2],f"Hub {hub.index} tile IDs differ"
            gfx=hub.graphics()
            prepare(machine,data)
            # Emulate the load order: secondary bank 1, then primary bank 0.
            for secondary in (True,False):
                bank=hub.graphics_offset//0x4000
                pointer=hub.graphics_offset%0x4000+0x4000
                dictionary=le16(data,hub.graphics_offset+(4 if secondary else 0))
                stream=le16(data,hub.graphics_offset+2) if secondary else pointer+6
                p.register_file.B=dictionary>>8
                p.register_file.C=dictionary&255
                p.register_file.D=stream>>8
                p.register_file.E=stream&255
                p.memory[0xff4f]=int(secondary)
                machine.call(bank,0xc42e,max_frames=120)
            for bank in (0,1):
                p.memory[0xff4f]=bank
                actual=bytes(p.memory[0x9000:0x9800])+bytes(p.memory[0x8800:0x9000])
                if actual!=gfx[bank]:
                    bad=[i for i,(a,b) in enumerate(zip(actual,gfx[bank])) if a!=b]
                    raise AssertionError(f"Hub {hub.index} graphics bank {bank} differs: {len(bad)} bytes, first {bad[:20]}")
            report.append(dict(index=hub.index,map_bytes=hub.width*hub.height*2,graphics_bytes=8192,result="exact"))
            print(f"PASS hub:{hub.index}: full map planes and 8192 graphics bytes",flush=True)
    finally:
        machine.close()
    (ROOT/"data/hub_verification.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    main()
