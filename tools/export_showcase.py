"""Cut the README showcase GIFs from the exported animated courses.

Each showcase is a fixed crop of one full-course GIF in images/animated/,
keeping every frame and its duration, so it loops exactly like the original.
Run export_animations.py first. Writes images/showcase/.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageSequence
from maps import ROOT

# (output name, source GIF, x, y, width, height), in source pixels.
SHOWCASE = [
    ("MRA_Round_Table_Trouble.gif", "MRA/01_Round_Table_Trouble.gif",
     1209, 772, 400, 300),
    ("MSUSA_Los_Angeles.gif", "MSUSA/01_Los_Angeles.gif",
     844, 676, 400, 300),
    ("MRA_Swashbuckling_Sand_Chase.gif",
     "MRA/13_Swashbuckling_Sand_Chase.gif", 969, 454, 400, 300),
    ("MSUSA_Florida_Everglades.gif", "MSUSA/18_Florida_Everglades.gif",
     653, 175, 400, 300),
]


def crop_gif(src, dst, box):
    im = Image.open(src)
    frames, durations = [], []
    for fr in ImageSequence.Iterator(im):
        frames.append(fr.convert("RGB").crop(box))
        durations.append(fr.info["duration"])
    # One shared palette with every colour used, so no frame is dithered.
    colours = sorted({c for f in frames for _, c in f.getcolors(1 << 16)})
    if len(colours) > 256:
        raise SystemExit(f"{src.name}: {len(colours)} colours in crop")
    flat = [v for c in colours for v in c]
    pal = Image.new("P", (1, 1))
    pal.putpalette(flat + [0]*(768-len(flat)))
    # Every colour is in the palette, so undithered quantize is exact.
    out = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    out[0].save(dst, save_all=True, append_images=out[1:],
                duration=durations, loop=0, disposal=1)
    return len(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, default=ROOT/"images/showcase")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, src, x, y, w, h in SHOWCASE:
        dst = args.output/name
        n = crop_gif(ROOT/"images/animated"/src, dst, (x, y, x+w, y+h))
        print(f"{name} {w}x{h} {n} frames {dst.stat().st_size//1024} KiB")


if __name__ == "__main__":
    main()
