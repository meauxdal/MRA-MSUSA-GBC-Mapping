"""Decode MRA exploration maps and their compressed background graphics."""
from dataclasses import dataclass
from maps import Course

def le16(data, offset):
    return int.from_bytes(data[offset:offset+2], "little")

def far_le(data, offset):
    bank=data[offset]
    pointer=le16(data,offset+1)
    if not 0x4000<=pointer<0x8000:
        raise ValueError(f"Invalid hub pointer at {offset:#x}")
    return bank*0x4000+pointer-0x4000

def decode_graphics(data, offset, second=False):
    bank_base=offset//0x4000*0x4000-0x4000
    dictionary=bank_base+le16(data,offset+(4 if second else 0))
    pos=bank_base+le16(data,offset+2) if second else offset+6
    result=bytearray()
    # The engine can continue from bank 0 to bank 1, so retain both when present.
    while len(result)<8192:
        token=data[pos]
        pos+=1
        if token==255:
            break
        if token in (0,1,2,3):
            result+=bytes([255 if token&1 else 0])*(4 if token>=2 else 2)
        elif token==254:
            result+=data[pos:pos+2]
            pos+=2
        else:
            source=dictionary+(token-4)*2
            result+=data[source:source+2]
    return bytes(result),pos

def decode_map(data, offset):
    mode,width,height=data[offset:offset+3]
    if mode:
        raise ValueError(f"Unsupported direct-ROM hub mode {mode}")
    base=offset//0x4000*0x4000-0x4000
    attributes=base+le16(data,offset+3)
    graphics=offset+7
    pos=base+le16(data,offset+5)
    ids=bytearray()
    attrs=bytearray()
    while len(ids)<width*height:
        token=data[pos]
        pos+=1
        repeat=1
        if token==255:
            token=data[pos]
            repeat=data[pos+1] or 256
            pos+=2
        if token==254:
            index=data[pos]+253
            pos+=1
        elif token==253:
            index=le16(data,pos)
            pos+=2
        else:
            index=token
        ids+=data[graphics+index*4:graphics+index*4+4]*repeat
        attrs+=data[attributes+index*4:attributes+index*4+4]*repeat
        if len(ids)>width*height+1024:
            raise ValueError("Map run exceeds declared dimensions")
    pairs=bytearray(width*height*2)
    pairs[0::2]=ids[:width*height]
    pairs[1::2]=attrs[:width*height]
    return width,height,bytes(pairs),pos

@dataclass
class Hub:
    index: int
    width: int
    height: int
    map_offset: int
    graphics_offset: int
    palette_offset: int
    rom: bytes

    def tile_pairs(self):
        return decode_map(self.rom,self.map_offset)[2]

    def graphics(self):
        # Bank 1 is loaded first, followed by the primary bank 0 stream.
        secondary,_=decode_graphics(self.rom,self.graphics_offset,True)
        primary,_=decode_graphics(self.rom,self.graphics_offset)
        result=[bytearray(4096),bytearray(4096)]
        result[1][:min(4096,len(secondary))]=secondary[:4096]
        result[0][:min(4096,len(primary))]=primary[:4096]
        if len(primary)>4096:
            result[1][:len(primary)-4096]=primary[4096:]
        return result

    def palette(self):
        # Share the race decoder's RGB555 conversion without inventing a tint.
        return Course.palette(self)

    def render(self):
        from maps import render_tiles
        return render_tiles(self.width,self.height,self.tile_pairs(),self.graphics(),self.palette())

def hubs(data):
    for index in range(6):
        descriptor=0x194997+index*17
        map_offset=far_le(data,descriptor)
        selector=data[descriptor+6]
        graphics_descriptor=0x194500+((selector&15)<<4)+(selector>>4)
        yield Hub(index,data[map_offset+1],data[map_offset+2],map_offset,
                  far_le(data,graphics_descriptor),far_le(data,graphics_descriptor+3),data)
