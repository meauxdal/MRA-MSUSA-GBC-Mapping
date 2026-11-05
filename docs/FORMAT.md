# Map formats and evidence

The decoder targets the two exact ROM revisions identified in `tools/maps.py`
by SHA-256. ROMs are supplied by the user under ignored `local/`; none are
embedded in the tools. Addresses below are hexadecimal. A banked CPU address
`bb:aaaa` converts to file offset `bb * 4000 + aaaa - 4000` for `4000..7fff`.

## Race backgrounds

Both games use the same fundamental format. Bank `20` starts with a table of
**big-endian** 16-bit descriptor pointers. A descriptor has seven selector bytes.
Selector 0 chooses two far pointers, each encoded **bank, high, low**, to the map
planes. Each plane begins with one byte of width and one byte of height, followed
by `width * height` bytes in row order. These are not terrain categories: the two
bytes at each coordinate combine into an offset into a metatile definition bank.

| Table / routine | MRA file offset | MSUSA file offset |
| --- | --- | --- |
| Descriptor pointer table | `080000` | `080000` |
| Plane-pointer pairs, 6 bytes/entry | `0800c8` | `0800e1` |
| Graphics descriptor pointer table | `080152` | `080177` |
| Palette far pointers | `080297` | `0802e5` |
| Main race-map loader | `001d23` | `001921` |
| Horizontal terrain renderer | `001a40` | `001622` |
| Map row lookup | `001c43` | `001825` |

MRA has 23 descriptor slots, with slot 7 null, yielding 22 known courses. The
first 21 MSUSA slots correspond to the 21 existing named courses. Additional
MSUSA slots 21–24 exist, with shorter graphics descriptors in several cases;
they export separately as research backgrounds (see below).
Engine order is different from the numbered filenames. `data/catalog.json`
matches the old PNG names using the map-plane offsets printed in the old grids.

Selector 1 chooses the graphics descriptor, whose first byte is the metatile
definition bank. Its next three bytes are an additional resource pointer (not
used for the base-background raster). Its following two far pointers select
background tile graphics for VRAM banks 0 and 1. Each graphics resource begins
with a block count; zero means 256. Each block is 16 bytes: one native 8×8,
two-bitplane Game Boy tile. Selector 4 chooses a 64-byte RGB555 palette resource.

For a map cell `(x,y)`, let `L` and `H` be the bytes in the two planes. Its 32×32
pixel metatile contains 16 native tiles. Subtile `(sx,sy)`, each in `0..3`, is the
two-byte `(tile_id, CGB_attribute)` pair at this **file offset**:

```text
metatile_bank * 0x4000 + L + H * 0x100 + sx * 0x400 + sy * 0x1000
```

CGB attribute bits select palette (0–2), graphics bank (3), horizontal flip (5),
vertical flip (6), and sprite priority (7). Priority does not change a background
pixel's color. The game uses signed background addressing: tile 0 begins at
VRAM `9000`, while tile 128 begins at `8800`. The raw graphics resources are
already ordered by tile ID.

The exported RGB channels are the original five-bit components shifted left
three bits (0–248), matching the tested PyBoy rasterizer. No display tint,
color correction, antialiasing, or resizing is applied to the full-size PNGs.
Overview grids alone are resized for browsing.

### Animation uploads

The static graphics resources contain placeholders for some animated tiles.
`tools/trace_animations.py` executes the game's own animation routine with frame
counters forced to wrap to frame zero, then records source/destination pointer
metadata at the graphics-upload routine. `tools/maps.py` applies those uploads
to the raw tile set before rasterization.

| Routine | MRA bank:address | MSUSA bank:address |
| --- | --- | --- |
| Animation dispatch | `1e:421f` (bypasses the LY gate at `4215`) | `10:41e2` |
| Upload queue hook | `00:1477` | `00:10e5` |

MRA's selector is `ce7b`; MSUSA's is `ce8c`. MSUSA animation counters occupy
WRAM bank 5 at `dca0..dcb7`, including Yellowstone's 12 separate streams. The
default capture uses `ce60=0`. A separate `msusa_animations_special.json` captures
the `ce60=1` branch, which changes Nebraska's animation uploads. The gameplay
meaning of that branch is not yet established; it is not silently applied to the
default maps. Animation phase and game state still matter; a static map is not
a complete representation of every frame or gameplay mode.

### Unmapped margins

Pete's Dungeon contains 144 subtile lookups that land outside the switchable
ROM window, in the far-right margin of the declared map rectangle. Those tiles
are transparent, not guessed. Their exact behavior depends on non-ROM memory;
the exporter records the count in the manifest. Other known course backgrounds
have no such unmapped lookups. These margins have not been established as
reachable camera space.

### Four additional MSUSA slots

`tools/export_maps.py --extras` exports engine indices 21–24 to
`images/reconstructed/MSUSA_extras/`, without changing the named-course set.
`data/msusa_extras.json` supplies descriptive labels and per-slot limitations.

| Slot | Descriptor | Graphics descriptor | Bytes | Source rendering |
| --- | --- | --- | --- | --- |
| 21 | `0800c5` | `08027b` | 7 | Coherent walled garden, 1248×704 |
| 22 | `0800cc` | `080282` | 7 | Coherent log arena, 1024×864 |
| 23 | `0800d3` | `080289` | 7 | Scrambled graphics, 1216×864; unresolved |
| 24 | `0800da` | `080290` | 10 | City arena, 1376×928; 145 transparent non-ROM subtiles |

The first three graphics descriptors end after the bank-0 graphics pointer.
Their extents follow from the next graphics-descriptor pointers in the table.
The regular loader at `00:1921` does **not** respect these extents: it reads a
second far pointer from the next descriptor's first three bytes. The isolated
loader records bank-1 source CPU addresses `2371`, `2375`, and `2271`, which lie
in fixed ROM rather than the switchable bank. These reads are not valid declared
bank-1 resources. All mapped subtiles in slots 21–23 select VRAM bank 0, so these
bank-1 reads do not affect the exported source backgrounds. The exporter treats
the absent bank-1 resource as absent; it does not fabricate pointers.

`tools/verify_msusa_extras.py` calls the original regular loader with LCD enabled
(its graphics-transfer path waits for VBlank), checks both complete loaded map
planes and the declared graphics bytes staged before VRAM transfer, then checks
six terrain-renderer samples and three rasterizer windows per slot. Every mapped
subtile uses graphics within its declared resource. Slot 23's declared bank-0
resource is exactly what this loader stages, but renders scrambled terrain; a
passing source check is not evidence that its assets are correct. Slot 24's
non-ROM reads depend on other memory and remain transparent. Results are in
`data/msusa_extras_verification.json`.

No normal gameplay path to these four slots, in-game names, or alternative
loader has been established. Their status as active arenas versus unused
remnants remains unresolved. No animation uploads are assumed for these slots.
The grid includes slot 23 explicitly as an unresolved diagnostic image.

## MRA exploration backgrounds

The exploration engine is separate and copies executable routines from ROM into
WRAM. Six 17-byte map descriptors begin at file offset `194997` (bank `65:4997`).
Their pointers use **bank, low, high**, unlike the race format. The graphics
selector chooses a 16-byte resource descriptor at `194500`.

A map resource begins with a mode byte (all six are zero), width and height in
native 8-pixel tiles, an attribute dictionary pointer, and a token-stream pointer.
The tile-ID dictionary starts immediately after the seven-byte header. Each
dictionary entry gives four consecutive tiles. The token stream expands as:

| Token | Meaning |
| --- | --- |
| `00..fc` | Four-tile dictionary entry |
| `fe xx` | Entry `253 + xx` |
| `fd ll hh` | Entry `hhll` |
| `ff token count` | Repeat the following entry `count` times (zero means 256) |

The original decompressor is at file `1902d5`, executed at WRAM `c4d5`. It writes
attributes to WRAM banks 2–4 and tile IDs to banks 5–7. This plane order matters.

The graphics resource has three 16-bit pointers: the primary dictionary,
secondary stream, and secondary dictionary. The primary stream begins at byte 6.
Graphics tokens emit pairs: `00` two zero bytes, `01` two `ff` bytes, `02` four
zero bytes, `03` four `ff` bytes, `fe` two literal bytes, `04..fd` a dictionary
pair, and `ff` ends the stream. The secondary stream loads VRAM bank 1 first;
the primary loads bank 0 and may continue into bank 1. `tools/hubs.py` preserves
that order, including streams that cross the bank boundary within a token.

The palette pointer is part of the selected graphics descriptor. Exports use
the same RGB555 conversion as the race maps. Names assigned to these six maps
are visual descriptions, not verified in-game titles.

### Pluto holes

The source exploration layouts include filled and open Pluto holes. In the
observed fresh town state, runtime map edits replace five 4×4-tile hole patches
with grass: 80 tiles total. Those account for all map differences between the
source town layout and the captured live RAM. The source-layout export preserves
the holes. Whether a particular hole is visible depends on game state; a map
should not imply that all holes are simultaneously visible during play.

## Validation and limits

- `tools/verify_maps.py`: calls the **original ROM horizontal renderer** at six
  coordinate samples per known course and compares emitted tile IDs/attributes.
  All 43 pass. Results: `data/verification.json`.
- `tools/verify_pixels.py`: loads the decoded tile bytes and original palettes
  into the emulator, with sprites disabled, and compares three rasterized windows
  per course against the actual exported PNG. All 43 pass; transparent unmapped
  pixels are excluded. Results: `data/pixel_verification.json`.
- `tools/verify_hubs.py`: calls the **original RAM decompression routines** and
  compares complete map planes plus 8,192 graphics bytes for all six hubs. All
  six pass exactly. Results: `data/hub_verification.json`.
- `tools/verify_msusa_extras.py`: separately checks the four extra MSUSA slots
  against the original regular loader, renderer and CGB rasterizer, subject to
  the unresolved graphics and non-ROM-read limits described above.

These checks distinguish source decoding from gameplay completeness. Current
exports are background layers. Sprites, pickups, opponents, some start/finish
markers, state-dependent scenery, animated map changes, and special-mode
variants require further tracing. The checks do not establish every map pixel
against a naturally reached gameplay camera position.

The emulator interface and memory APIs are documented by
[PyBoy](https://docs.pyboy.dk/api/pyboy.html). LR35902 opcode facts for the range
disassembler are read from the locally installed
[PyBoy opcode definitions](https://github.com/Baekalfen/PyBoy). Generated ROM
listings and save states are kept under ignored `local/`.
