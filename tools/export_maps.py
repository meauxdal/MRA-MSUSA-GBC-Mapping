"""Export native-size background maps; originals remain untouched."""
import argparse
import hashlib
import json
import time
from pathlib import Path
from PIL import Image, ImageDraw
from maps import ROOT, read_rom, courses, render, animation_patches

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",choices=["mra","msusa","all"],default="all")
    parser.add_argument("--rom-dir",type=Path,default=ROOT/"local")
    parser.add_argument("--output",type=Path,default=ROOT/"images/reconstructed")
    parser.add_argument("--index",type=int)
    parser.add_argument("--extras",action="store_true",help="Export MSUSA slots 21-24 separately, with unresolved status")
    args=parser.parse_args()
    if args.extras and args.game=="mra":
        parser.error("--extras applies only to MSUSA")
    catalog=json.loads((ROOT/"data/catalog.json").read_text())
    if args.extras:
        catalog["msusa"]=json.loads((ROOT/"data/msusa_extras.json").read_text())
    for game in (["msusa"] if args.extras else ["mra","msusa"] if args.game=="all" else [args.game]):
        started=time.perf_counter()
        data=read_rom(game,args.rom_dir)
        patches={} if args.extras else animation_patches(game)
        group=game.upper()+("_extras" if args.extras else "")
        dest=args.output/group
        dest.mkdir(parents=True,exist_ok=True)
        manifest=[]
        thumbs=[]
        for course in courses(game,data,include_extras=args.extras):
            if args.extras and course.index<21:
                continue
            if args.index is not None and args.index!=course.index:
                continue
            entry=catalog[game][str(course.index)]
            im=render(course,patches.get(str(course.index),[]))
            unmapped=set()
            course.tile_pairs(unmapped)
            filename=entry["filename"]
            im.save(dest/filename)
            thumb=im.copy()
            thumb.thumbnail((360,260),Image.Resampling.LANCZOS)
            thumbs.append((thumb,entry["name"],course.index))
            manifest.append(dict(index=course.index,name=entry["name"],file=filename,
                status=entry.get("status","background reconstruction; objects and runtime changes not included"),
                width=im.width,height=im.height,descriptor=f"0x{course.descriptor:06x}",
                selectors=list(course.selectors),
                low_plane=f"0x{course.low_offset:06x}",high_plane=f"0x{course.high_offset:06x}",
                metatile_bank=f"0x{course.metatile_bank:02x}",
                graphics=[f"0x{x:06x}" if x is not None else None for x in course.graphics_offsets],
                palette=f"0x{course.palette_offset:06x}",
                animation_uploads=len(patches.get(str(course.index),[])),
                unmapped_8px_tiles=len(unmapped),
                sha256=hashlib.sha256((dest/filename).read_bytes()).hexdigest()))
            if "reconstruction" in entry:
                manifest[-1]["reconstruction"]=entry["reconstruction"]
            print(f"{game}:{course.index:02d} {im.width}x{im.height} {filename}",flush=True)
        (dest/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
        if thumbs:
            rows=(len(thumbs)+3)//4
            grid=Image.new("RGB",(1504,rows*300),(20,20,20))
            draw=ImageDraw.Draw(grid)
            for n,(thumb,label,index) in enumerate(thumbs):
                x=n%4*376+8;y=n//4*300+8
                grid.paste(thumb,(x,y))
                draw.text((x,y+264),label,fill="white")
                draw.text((x,y+280),f"Engine index {index:02d} | background layer",fill=(170,170,170))
            grid.save(args.output/f"{group}_grid.png")
        print(f"{game}: {len(manifest)} maps in {time.perf_counter()-started:.2f}s",flush=True)

if __name__=="__main__":
    main()
