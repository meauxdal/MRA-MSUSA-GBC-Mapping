"""Small LR35902 range disassembler for targeted research (not code discovery).

Opcode facts are read from the locally installed PyBoy opcode definitions.
PyBoy: https://github.com/Baekalfen/PyBoy (LGPL-3.0).
No game code or generated ROM listings are bundled with this tool.
"""
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = (ROOT / "local/tools/python/pyboy/core/opcodes.py").read_text()
OPS = {int(n, 16): name.strip() for n, name in re.findall(r"^def .*?# ([0-9A-F]{2,3}) (.+)$", source, re.M)}

def decode(data, off):
    op = data[off]
    if op == 0xCB:
        return 2, OPS.get(0x100 + data[off+1], "illegal")
    name = OPS.get(op, f"db ${op:02x}")
    n = 3 if "d16" in name or "a16" in name else 2 if any(x in name for x in ("d8", "a8", "r8")) or op == 0x10 else 1
    v = int.from_bytes(data[off+1:off+n], "little")
    name = re.sub(r"d16|a16|d8|a8", lambda _: f"${v:0{(n-1)*2}x}", name)
    pc = off if off < 0x4000 else 0x4000 + off % 0x4000
    rel = data[off+1] if n == 2 else 0
    rel -= 256 if rel > 127 else 0
    name = name.replace("r8", f"${(pc+2+rel)&65535:04x}" if op in (0x18,0x20,0x28,0x30,0x38) else str(rel))
    return n, name

def listing(data, start, end):
    while start < end:
        n, name = decode(data, start)
        pc = start if start < 0x4000 else 0x4000 + start % 0x4000
        yield f"{start:06x} {start//0x4000:02x}:{pc:04x}  {data[start:start+n].hex(' '):8} {name}"
        start += n

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("game", choices=["mra", "msusa"])
    p.add_argument("start", type=lambda s: int(s, 0))
    p.add_argument("end", type=lambda s: int(s, 0))
    args = p.parse_args()
    rom = next((ROOT / "local").glob("*" + ("Racing Adventure" if args.game == "mra" else "Speedway USA") + "*.gbc"))
    print("\n".join(listing(rom.read_bytes(), args.start, args.end)))
