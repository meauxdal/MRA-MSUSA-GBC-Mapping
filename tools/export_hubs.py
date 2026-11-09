"""Export the six MRA exploration base backgrounds."""
import hashlib
import json
from PIL import Image,ImageDraw
from maps import ROOT,read_rom
from hubs import hubs

# Area names as players know them.
NAMES=["Ludwig Von Drake's Garage", "Mickey's Hometown", "Casey Junior Junction",
       "Magica De Spell's House", "Chip 'n' Dale's Treehouse Glade",
       "Casey Junior Junction Railway"]

def main():
    out=ROOT/"images/reconstructed/MRA_hubs"
    out.mkdir(parents=True,exist_ok=True)
    manifest=[]
    grid=Image.new("RGB",(1200,820),(20,20,20))
    draw=ImageDraw.Draw(grid)
    for hub in hubs(read_rom("mra")):
        im=hub.render()
        filename=f"{hub.index:02d}_{NAMES[hub.index].replace(' ','_')}.png"
        im.save(out/filename)
        manifest.append(dict(index=hub.index,name=NAMES[hub.index],identification="area name used by players; no on-screen title",
            file=filename,width=im.width,height=im.height,map=f"0x{hub.map_offset:06x}",
            graphics=f"0x{hub.graphics_offset:06x}",palette=f"0x{hub.palette_offset:06x}",
            status="base background; runtime map edits, sprites, and animation changes not included",
            sha256=hashlib.sha256((out/filename).read_bytes()).hexdigest()))
        im.thumbnail((384,360),Image.Resampling.LANCZOS)
        x=hub.index%3*400+8;y=hub.index//3*410+8
        grid.paste(im,(x,y))
        draw.text((x,y+366),f"{hub.index:02d} {NAMES[hub.index]}",fill="white")
        draw.text((x,y+382),"Exploration base background",fill=(170,170,170))
        print(f"hub:{hub.index} {hub.width*8}x{hub.height*8} {filename}")
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    grid.save(out.parent/"MRA_hubs_grid.png")

if __name__=="__main__":
    main()
