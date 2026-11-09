"""Check GIF structure/timing, lossless delta compositing, and indexed rendering."""
import argparse
import hashlib
import json
import struct
import numpy as np
from PIL import Image
from maps import ROOT, read_rom, courses, render
from animations import metadata_path, patches_at, timeline
from export_animations import IndexedMap, centiseconds


def gif_frames(path):
    """Read frame rectangles and delays without decompressing full map canvases."""
    data=path.read_bytes()
    if data[:6]!=b"GIF89a":
        raise AssertionError("Missing GIF89a header")
    width,height,packed=struct.unpack_from("<HHB",data,6)
    pos=13+(3*(2**((packed&7)+1)) if packed&128 else 0)
    delay=None
    frames=[]
    loop=None

    def blocks(offset):
        chunks=[]
        while data[offset]:
            n=data[offset]
            chunks.append(data[offset+1:offset+1+n])
            offset+=n+1
        return offset+1,b"".join(chunks)

    while data[pos]!=0x3b:
        if data[pos]==0x21:
            label=data[pos+1]
            pos,payload=blocks(pos+2)
            if label==0xf9:
                flags,delay,transparent=struct.unpack("<BHB",payload)
                if flags!=5 or transparent!=32:
                    raise AssertionError("Incorrect disposal/transparency")
            elif label==0xff and payload.startswith(b"NETSCAPE2.0"):
                loop=int.from_bytes(payload[12:14],"little")
        elif data[pos]==0x2c:
            left,top,w,h,flags=struct.unpack_from("<HHHHB",data,pos+1)
            if flags or left+w>width or top+h>height or delay is None or delay<=0:
                raise AssertionError("Invalid frame bounds/timing/local palette")
            frames.append(dict(left=left,top=top,width=w,height=h,duration_ms=delay*10))
            pos+=11  # separator, descriptor, LZW minimum code size
            pos,_=blocks(pos)
            delay=None
        else:
            raise AssertionError(f"Unknown GIF block at {pos}")
    if pos!=len(data)-1 or loop!=0:
        raise AssertionError("Invalid trailer or infinite-loop extension")
    return (width,height),frames


def check(game):
    directory=ROOT/"images/animated"/game.upper()
    manifest=json.loads((directory/"manifest.json").read_text())
    metadata=json.loads(metadata_path().read_text())["games"][game]
    course_by_index={c.index:c for c in courses(game,read_rom(game))}
    results=[]
    for entry in manifest:
        if not entry["file"]:
            continue
        course=course_by_index[entry["index"]]
        animation=metadata[str(course.index)]
        path=directory/entry["file"]
        dimensions,encoded=gif_frames(path)
        if dimensions!=(course.width*32,course.height*32) or len(encoded)!=entry["encoded_frames"]:
            raise AssertionError(f"{path}: wrong size/frame count")
        duration=sum(f["duration_ms"] for f in encoded)
        if duration!=centiseconds(animation["period_ticks"])*10 or duration!=entry["duration_ms"]:
            raise AssertionError(f"{path}: timing drift")
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
            raise AssertionError(f"{path}: hash mismatch")
        # Independently rasterize first/middle/last phases through the original
        # PIL tile renderer, checking the new indexed incremental renderer.
        renderer=IndexedMap(course)
        ticks=sorted(set([0,animation["period_ticks"]//2,animation["period_ticks"]-1]))
        for tick in ticks:
            patches=patches_at(animation,tick)
            image=renderer.image(renderer.frame(patches))
            image.info["transparency"]=32
            if image.convert("RGBA").tobytes()!=render(course,patches).convert("RGBA").tobytes():
                raise AssertionError(f"{path}: indexed raster mismatch at tick {tick}")
        # Decode the first three distinct stored frames, including delta
        # compositing and transparent unmapped margins, at full native size.
        renderer=IndexedMap(course)
        previous=None
        decoded=0
        with Image.open(path) as gif:
            for start,end in timeline(animation):
                array=renderer.frame(patches_at(animation,start))
                if previous is not None and np.array_equal(array,previous):
                    continue
                gif.seek(decoded)
                expected=renderer.image(array)
                expected.info["transparency"]=32
                if gif.convert("RGBA").tobytes()!=expected.convert("RGBA").tobytes():
                    raise AssertionError(f"{path}: GIF composite mismatch at frame {decoded}")
                previous=array
                decoded+=1
                if decoded==min(3,entry["encoded_frames"]):
                    break
        results.append(dict(index=course.index,frames=len(encoded),duration_ms=duration,
            raster_phases=ticks,decoded_native_frames=decoded,result="exact"))
        print(f"PASS {game.upper()}:{course.index:02d}: {len(encoded)} GIF frames, timing, raster and composites",flush=True)
    return results


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    games=["mra","msusa"]
    result=dict(method="Every GIF frame header, duration and hash; three independent native raster phases and first three decoded composites per GIF.",
        limits="Later GIF frames checked structurally, not exhaustively decompressed; source timing is verified separately over full cycles.",
        games={g:check(g) for g in games})
    (ROOT/"data"/"animation_export_verification.json").write_text(json.dumps(result,indent=2)+"\n")


if __name__=="__main__":
    main()
