"""Bounded isolated calls into original ROM routines for reproducible validation."""
import io
import sys
from maps import ROOT,CONFIG

sys.path.insert(0,str(ROOT/"local/tools/python"))
from pyboy import PyBoy

class Machine:
    def __init__(self,game):
        rom=next((ROOT/"local").glob(CONFIG[game]["pattern"]))
        self.p=PyBoy(str(rom),window="null",sound_emulated=False,
                     ram_file=io.BytesIO(bytes(128*1024)),log_level="ERROR")
        self.p.set_emulation_speed(0)
        self.p.tick(1200,False)
        self.base=io.BytesIO()
        self.p.save_state(self.base)
        # Temporary emulator ROM override, never written to the source ROM file.
        self.p.memory[0,0x100]=0x18
        self.p.memory[0,0x101]=0xfe

    def reset(self):
        self.base.seek(0)
        self.p.load_state(self.base)
        self.p.memory[0xffff]=0
        self.p.memory[0xff0f]=0

    def call(self,bank,address,max_frames=20):
        p=self.p
        p.memory[0x2000]=bank
        p.memory[0xff8a]=bank
        p.register_file.SP=0xcffc
        p.memory[0xcffc]=0
        p.memory[0xcffd]=1
        p.register_file.PC=address
        for _ in range(max_frames):
            p.tick(1,False)
            if p.register_file.PC==0x100:
                return
        raise RuntimeError(f"Routine {bank:02x}:{address:04x} did not return in {max_frames} frames; PC={p.register_file.PC:04x}")

    def close(self):
        self.p.stop(save=False)
