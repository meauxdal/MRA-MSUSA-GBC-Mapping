"""Export lossless native-size course GIFs using recovered ROM animation timing.

Only two full indexed frames are retained by the writer; unchanged pixels in
delta rectangles are transparent. Pillow's GIF encoder is pinned in requirements.
"""
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from PIL import Image, GifImagePlugin
from maps import ROOT, OBSERVED_FILL, read_rom, courses
from animations import TICK_SECONDS, metadata_path, patches_at, timeline


class IndexedMap:
    def __init__(self, course):
        self.course=course
        missing=set()
        pairs=np.frombuffer(course.tile_pairs(missing),dtype=np.uint8).reshape(-1,2)
        self.width=course.width*4
        self.height=course.height*4
        self.array=np.full((self.height*8,self.width*8),32,dtype=np.uint8)
        self.view=self.array.reshape(self.height,8,self.width,8)
        self.positions={}
        for n,a in np.unique(pairs,axis=0):
            positions=np.flatnonzero((pairs[:,0]==n)&(pairs[:,1]==a))
            if missing:
                positions=positions[~np.isin(positions,list(missing))]
            self.positions[int(n),int(a)]=(positions//self.width,positions%self.width)
        self.previous=None
        colors=course.palette()
        self.palette=[v for rgb in colors for v in rgb]+[0]*(768-96)
        fill=OBSERVED_FILL.get((course.game,course.index))
        if fill and missing:
            # Observed colour for lookups outside the ROM; see maps.py.
            index=colors.index(fill)
            for t in missing:
                self.view[t//self.width,:,t%self.width,:]=index

    def frame(self, patches):
        gfx,_=self.course.graphics(patches)
        changed={(bank,n) for bank in (0,1) for n in range(256)
                 if self.previous is None or gfx[bank][n*16:n*16+16]!=self.previous[bank][n*16:n*16+16]}
        for (n,a),(ys,xs) in self.positions.items():
            bank=(a>>3)&1
            if (bank,n) not in changed:
                continue
            raw=np.frombuffer(gfx[bank][n*16:n*16+16],dtype=np.uint8).reshape(8,2)
            bits=np.arange(7,-1,-1,dtype=np.uint8)
            tile=((raw[:,0,None]>>bits)&1)+2*((raw[:,1,None]>>bits)&1)+(a&7)*4
            if a&32:
                tile=tile[:,::-1]
            if a&64:
                tile=tile[::-1]
            self.view[ys,:,xs,:]=tile
        self.previous=gfx
        return self.array.copy()

    def image(self, array):
        image=Image.fromarray(array)
        image.putpalette(self.palette)
        return image


def centiseconds(tick):
    # Round absolute boundaries, not each duration: avoids cumulative drift.
    return round(tick*70224*100/4194304)


def write_gif(path, renderer, animation):
    frames=timeline(animation)
    if not frames:
        return None
    written=0
    duration=0
    previous=None

    def flush(fp, array, start, end):
        nonlocal previous,written,duration
        ms=(centiseconds(end)-centiseconds(start))*10
        if not ms:
            raise ValueError("Animation transition is below GIF timing resolution")
        if previous is None:
            image=renderer.image(array)
            for block in GifImagePlugin._get_global_header(image,dict(loop=0,transparency=32,background=32)):
                fp.write(block)
            offset=(0,0)
        else:
            changed=array!=previous
            ys,xs=np.nonzero(changed)
            left,top,right,bottom=int(xs.min()),int(ys.min()),int(xs.max())+1,int(ys.max())+1
            rectangle=array[top:bottom,left:right].copy()
            rectangle[~changed[top:bottom,left:right]]=32
            image=renderer.image(rectangle)
            offset=(left,top)
        GifImagePlugin._write_frame_data(fp,image,offset,dict(duration=ms,disposal=1,transparency=32))
        previous=array
        written+=1
        duration+=ms

    # Write a temporary file so interruption cannot leave a seemingly finished GIF.
    temporary=path.with_suffix(".gif.tmp")
    try:
        with temporary.open("wb") as fp:
            pending=None
            for start,end in frames:
                array=renderer.frame(patches_at(animation,start))
                if pending is not None and np.array_equal(array,pending[0]):
                    pending=(pending[0],pending[1],end)
                    continue
                if pending is not None:
                    flush(fp,*pending)
                pending=(array,start,end)
            flush(fp,*pending)
            fp.write(b";")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return dict(encoded_frames=written,duration_ms=duration,
        timing_error_ms=duration-animation["period_ticks"]*TICK_SECONDS*1000,
        bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game",choices=["mra","msusa","all"],default="all")
    parser.add_argument("--index",type=int)
    parser.add_argument("--output",type=Path,default=ROOT/"images/animated")
    args=parser.parse_args()
    metadata=json.loads(metadata_path().read_text())
    catalog=json.loads((ROOT/"data/catalog.json").read_text())
    games=list(metadata["games"]) if args.game=="all" else [args.game]
    for game in games:
        dest=args.output/game.upper()
        dest.mkdir(parents=True,exist_ok=True)
        manifest=[]
        for course in courses(game,read_rom(game)):
            if args.index is not None and args.index!=course.index:
                continue
            animation=metadata["games"][game][str(course.index)]
            entry=catalog[game][str(course.index)]
            row=dict(index=course.index,name=entry["name"],file=None,
                period_ticks=animation["period_ticks"],streams=len(animation["streams"]),
                width=course.width*32,height=course.height*32,
                status="No tile-animation streams in the selected course dispatch")
            if animation["streams"]:
                start=time.perf_counter()
                filename=Path(entry["filename"]).with_suffix(".gif").name
                result=write_gif(dest/filename,IndexedMap(course),animation)
                row.update(result,file=filename,status="Native background tile animation; nominal update cadence; sprites and runtime map edits excluded")
                print(f"{game}:{course.index:02d} {result['encoded_frames']} frames, {result['duration_ms']}ms, {result['bytes']/1024:.0f}KiB in {time.perf_counter()-start:.2f}s",flush=True)
            else:
                print(f"{game}:{course.index:02d} static",flush=True)
            manifest.append(row)
        # Indexed research runs must not overwrite a complete collection manifest.
        name="manifest.json" if args.index is None else f"manifest_{args.index:02d}.json"
        (dest/name).write_text(json.dumps(manifest,indent=2)+"\n")


if __name__=="__main__":
    main()
