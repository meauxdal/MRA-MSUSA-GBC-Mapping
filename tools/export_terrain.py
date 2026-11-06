"""Export native terrain-code masks, boundary overlays and browsing grids."""
import argparse
import json
import hashlib
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from maps import ROOT, CONFIG, read_rom, courses, render, animation_patches
from terrain import TERRAIN, terrain_map, resource


COLORS = [(40,170,230),(240,125,55),(170,95,220),(245,215,55)]
LIMITS = "Static integer-point terrain classes, not vehicle clearance, dynamic objects, camera bounds, or reachable-area proof. Numeric behavior labels are unverified."


def export_course(course, entry, out):
    game = course.game
    stem = entry["filename"][:-4]
    codes = terrain_map(course)
    # Grayscale pixel values are the numeric terrain codes, not display colors.
    Image.fromarray(codes).save(out/(stem+"_codes.png"))
    regions = Image.fromarray(codes).convert("P")
    palette = [channel for n in range(256) for channel in
               (COLORS[n] if n < len(COLORS) else
                ((n*97)%256,(n*57)%256,(n*137)%256))]
    regions.putpalette(palette)
    regions.save(out/(stem+"_regions.png"))
    boundary = np.zeros_like(codes,dtype=bool)
    boundary[:,1:] |= codes[:,1:] != codes[:,:-1]
    boundary[1:,:] |= codes[1:,:] != codes[:-1,:]
    patches = animation_patches(game).get(str(course.index),[])
    base_background = render(course,patches).convert("RGBA")
    rgba = np.zeros((*codes.shape,4),dtype=np.uint8)
    rgba[boundary] = (255,32,160,255)
    background = Image.alpha_composite(base_background,Image.fromarray(rgba))
    background.save(out/(stem+"_boundaries.png"))
    preview = base_background.convert("RGB")
    preview.thumbnail((1100,800),Image.Resampling.LANCZOS)
    # Thicken only the browsing preview; the native boundary image stays 1 px.
    preview_edges = Image.fromarray(boundary.astype(np.uint8)*255).filter(ImageFilter.MaxFilter(3))
    preview_edges = preview_edges.resize(preview.size,Image.Resampling.NEAREST)
    preview.paste((255,32,160),(0,0,preview.width,preview.height),preview_edges)
    canvas = Image.new("RGB",(preview.width,preview.height+74),"#171d27")
    canvas.paste(preview,(0,74))
    draw = ImageDraw.Draw(canvas)
    draw.text((12,8),entry["name"]+" | source terrain boundaries",fill="white")
    draw.text((12,27),"Pink: numeric terrain-code changes. Behavior labels and vehicle clearance unverified.",fill="white")
    values,counts = np.unique(codes,return_counts=True)
    for i,value in enumerate(values):
        n = int(value)
        x = 12+i*100
        color = tuple(palette[n*3:n*3+3])
        draw.rectangle((x,48,x+12,60),fill=color)
        draw.text((x+18,48),f"Code {n}",fill="white")
    canvas.save(out/(stem+"_preview.png"))
    report = dict(game=game,index=course.index,rom_sha256=CONFIG[game]["sha256"],name=entry["name"],width=course.width*32,height=course.height*32,
        resource_offset=resource(course),lookup=f"00:{TERRAIN[game]['lookup']:04x}",codes={str(int(v)):int(n) for v,n in zip(values,counts)},
        limits=LIMITS)
    report["files"] = {kind:dict(file=stem+"_"+kind+".png",
        sha256=hashlib.sha256((out/(stem+"_"+kind+".png")).read_bytes()).hexdigest())
        for kind in ("codes","regions","boundaries","preview")}
    (out/(stem+".json")).write_text(json.dumps(report,indent=2)+"\n")
    return report


def grid(out, manifests, kind):
    columns = 4
    canvas = Image.new("RGB",(1504,((len(manifests)+columns-1)//columns)*310+50),"#171d27")
    draw = ImageDraw.Draw(canvas)
    draw.text((12,10),out.name+" | source terrain "+kind,fill="white")
    draw.text((12,28),"Numeric codes; behavior and racer clearance unverified. Code 0 blue, 1 orange, 2 purple, 3 yellow.",fill="white")
    for i,entry in enumerate(manifests):
        path = out/entry["files"][kind]["file"]
        with Image.open(path) as source:
            thumb = source.convert("RGB")
        thumb.thumbnail((360,260),Image.Resampling.NEAREST if kind == "regions" else Image.Resampling.LANCZOS)
        x,y = i%columns*376+8,i//columns*310+58
        canvas.paste(thumb,(x,y))
        draw.text((x,y+264),entry["name"],fill="white")
        draw.text((x,y+280),"Codes: "+", ".join(entry["codes"]),fill="#bdc6d5")
    canvas.save(out.parent/(out.name+"_"+kind+"_grid.png"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",choices=["mra","msusa","all"],default="all")
    parser.add_argument("--index",type=int,help="Engine course index; default is all named courses")
    args = parser.parse_args()
    catalog = json.loads((ROOT/"data/catalog.json").read_text())
    for game in (["mra","msusa"] if args.game == "all" else [args.game]):
        started = time.perf_counter()
        out = ROOT/"images/terrain"/game.upper()
        out.mkdir(parents=True,exist_ok=True)
        selected = [c for c in courses(game,read_rom(game)) if args.index is None or c.index == args.index]
        if not selected:
            parser.error(f"No course {game}:{args.index}")
        manifests = []
        for course in selected:
            entry = export_course(course,catalog[game][str(course.index)],out)
            manifests.append(entry)
            print(f"{game}:{course.index:02d} {entry['name']} | codes {','.join(entry['codes'])}",flush=True)
        if args.index is None:
            (out/"manifest.json").write_text(json.dumps(manifests,indent=2)+"\n")
            grid(out,manifests,"regions")
            grid(out,manifests,"boundaries")
        print(f"{game}: {len(manifests)} courses in {time.perf_counter()-started:.2f}s",flush=True)


if __name__ == "__main__":
    main()
