"""Bounded, stateful PyBoy research runner. All generated state stays under local/."""
import argparse
import io
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local/tools/python"))
from pyboy import PyBoy

parser = argparse.ArgumentParser()
parser.add_argument("game", choices=["mra", "msusa"])
parser.add_argument("script", type=Path)
parser.add_argument("--state", default="current")
parser.add_argument("--fresh", action="store_true")
args = parser.parse_args()
rom = next((ROOT / "local").glob("*" + ("Racing Adventure" if args.game == "mra" else "Speedway USA") + "*.gbc"))
out = ROOT / "local/research" / args.game
out.mkdir(parents=True, exist_ok=True)
state = out / (args.state + ".state")
p = PyBoy(str(rom), window="null", sound_emulated=False, ram_file=io.BytesIO(bytes(128 * 1024)), log_level="ERROR")
p.set_emulation_speed(0)
if state.exists() and not args.fresh:
    with state.open("rb") as f:
        p.load_state(f)
def tick(n=1, render=True):
    p.tick(n, render)
def press(key, n=1, after=60):
    p.button_press(key)
    tick(n)
    p.button_release(key)
    tick(after)
def shot(name="screen"):
    p.screen.image.save(out / (name + ".png"))
def save(name):
    with (out / (name + ".state")).open("wb") as f:
        p.save_state(f)
_session_started = time.perf_counter()
try:
    exec(compile(args.script.read_text(encoding="utf-8"), str(args.script), "exec"))
    with state.open("wb") as f:
        p.save_state(f)
    shot()
finally:
    p.stop(save=False)
    print(f"Elapsed: {time.perf_counter()-_session_started:.3f}s", flush=True)
