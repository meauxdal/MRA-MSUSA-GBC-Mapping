"""Compare decoded point classifications with original ROM lookup routines."""
import argparse
import json
import time
import hashlib
import numpy as np
from PIL import Image
from maps import ROOT, CONFIG, read_rom, courses, bank20, be16
from terrain import TERRAIN, resource, cell_ids, template
from emulator import Machine


def check(course, machine, limit=0, exports=False):
    game = course.game
    started = time.perf_counter()
    checks = 0
    try:
        machine.reset()
        p = machine.p
        for plane,offset in enumerate((course.low_offset,course.high_offset)):
            raw = course.rom[offset+2:offset+2+course.width*course.height]
            for chunk in range(2):
                p.memory[0xff70] = 1+plane+chunk*2
                block = raw[chunk*4096:(chunk+1)*4096]
                if block:
                    p.memory[0xd000:0xd000+len(block)] = list(block)
        for row in range(course.height):
            offset = row*course.width
            dest = 0xc8d2+row*3
            p.memory[dest:dest+3] = [1+(offset//4096)*2,0xd0+(offset%4096)//256,offset%256]
        g = bank20(be16(course.rom,CONFIG[game]["graphics"]+course.selectors[1]*2))
        pointer = TERRAIN[game]["pointer"]
        p.memory[pointer:pointer+3] = list(course.rom[g+1:g+4])
        ids = cell_ids(course)
        exported = None
        if exports:
            catalog = json.loads((ROOT/"data/catalog.json").read_text())
            stem = catalog[game][str(course.index)]["filename"][:-4]
            folder = ROOT/"images/terrain"/game.upper()
            metadata = json.loads((folder/(stem+".json")).read_text())
            for artifact in metadata["files"].values():
                if hashlib.sha256((folder/artifact["file"]).read_bytes()).hexdigest() != artifact["sha256"]:
                    raise AssertionError("Export hash mismatch")
            with Image.open(folder/(stem+"_codes.png")) as source:
                if source.mode != "L" or source.size != (course.width*32,course.height*32):
                    raise AssertionError("Incorrect numeric mask format or dimensions")
                exported = np.array(source)
            with Image.open(folder/(stem+"_regions.png")) as source:
                if source.mode != "P" or not np.array_equal(np.array(source),exported):
                    raise AssertionError("Colored region indices differ from numeric codes")
            with Image.open(folder/(stem+"_boundaries.png")) as source:
                if source.size != (course.width*32,course.height*32):
                    raise AssertionError("Incorrect boundary overlay dimensions")
        rng = np.random.default_rng(20261105)
        for cell in ([] if exports else np.unique(ids)):
            cy,cx = np.argwhere(ids == cell)[0]
            expected = template(course,int(cell))
            points = [(x,y) for x in (0,15,16,31) for y in (0,31)]
            points += [tuple(map(int,xy)) for xy in rng.integers(0,32,size=(8,2))]
            # Explicitly exercise both sides of every class transition in this
            # shape at several columns, in addition to independent random points.
            for x in (0,7,15,16,23,31):
                for y in np.flatnonzero(expected[1:,x] != expected[:-1,x])+1:
                    points.extend([(x,int(y)-1),(x,int(y))])
            for x,y in points:
                wx,wy = int(cx)*32+x,int(cy)*32+y
                p.register_file.B = wx>>8
                p.register_file.C = wx&255
                p.register_file.D = wy>>8
                p.register_file.E = wy&255
                machine.call(0,TERRAIN[game]["lookup"],max_frames=2)
                actual = p.memory[p.register_file.HL]
                if actual != int(expected[y,x]):
                    raise AssertionError(f"Cell {cell} point {wx},{wy}: ROM={actual:02x}, decoder={expected[y,x]:02x}")
                checks += 1
                if limit and checks >= limit:
                    break
            if limit and checks >= limit:
                break
        # Independent full-map samples also cover repeated cells, far rows and
        # the WRAM plane-bank transition, rather than only first occurrences.
        if not limit:
            world_points = [(int(x),int(y)) for x,y in rng.integers(
                [0,0],[course.width*32,course.height*32],size=(128,2))]
            world_points += [(x,y) for x in (0,course.width*32-1)
                             for y in (0,course.height*32-1)]
            for wx,wy in world_points:
                cell = int(ids[wy//32,wx//32])
                expected = template(course,cell)[wy%32,wx%32]
                p.register_file.B,p.register_file.C = wx>>8,wx&255
                p.register_file.D,p.register_file.E = wy>>8,wy&255
                machine.call(0,TERRAIN[game]["lookup"],max_frames=2)
                actual = p.memory[p.register_file.HL]
                if actual != int(expected):
                    raise AssertionError(f"{game}:{course.index} world point {wx},{wy}: ROM={actual:02x}, decoder={expected:02x}")
                if exported is not None and exported[wy,wx] != (actual & 63):
                    raise AssertionError(f"Saved mask differs from ROM at {wx},{wy}")
                checks += 1
    except Exception as exc:
        raise RuntimeError(f"{game}:{course.index} verification failed") from exc
    report = dict(game=game,index=course.index,rom_sha256=CONFIG[game]["sha256"],
        lookup=f"00:{TERRAIN[game]['lookup']:04x}",
        method=("Saved PNG vs original ROM at 132 seeded full-map points; complete numeric/region index equality, native dimensions and all artifact hashes." if exports else
                "Original ROM with source planes/resource pointer; corners, seeded random points and transition neighbors per unique cell, plus 132 full-map samples."),
        unique_cells=int(len(np.unique(ids))),samples=checks,elapsed_seconds=round(time.perf_counter()-started,3),
        complete_sample_set=not bool(limit),resource_offset=resource(course),
        limits="Sampled point-lookup equivalence, not exhaustive per-pixel emulation or terrain behavior/reachability validation.")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",choices=["mra","msusa","all"],default="msusa")
    parser.add_argument("--index",type=int,help="Engine course index; default is all named courses")
    parser.add_argument("--limit",type=int,default=0,help="Bounded timing probe per course; zero runs the full sample set")
    parser.add_argument("--exports",action="store_true",help="Check saved PNGs against ROM at 132 full-map points per course")
    args = parser.parse_args()
    if args.exports and args.limit:
        parser.error("--exports cannot be combined with --limit")
    games = list(CONFIG) if args.game == "all" else [args.game]
    reports = []
    for game in games:
        machine = Machine(game)
        try:
            selected = [c for c in courses(game,read_rom(game)) if args.index is None or c.index == args.index]
            if not selected:
                parser.error(f"No course {game}:{args.index}")
            for course in selected:
                report = check(course,machine,args.limit,args.exports)
                reports.append(report)
                print(f"PASS {game}:{course.index:02d}: {report['samples']} points / {report['unique_cells']} cells in {report['elapsed_seconds']}s",flush=True)
                if not args.limit and not args.exports:
                    (ROOT/"data"/f"terrain_verification_{game}_{course.index:02d}.json").write_text(json.dumps(report,indent=2)+"\n")
        finally:
            machine.close()
    if args.index is None and not args.limit:
        prefix = "terrain_export_verification" if args.exports else "terrain_verification"
        (ROOT/"data"/f"{prefix}_{args.game}.json").write_text(json.dumps(reports,indent=2)+"\n")


if __name__ == "__main__":
    main()
