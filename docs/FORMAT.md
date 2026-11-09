# Map formats and evidence

The tools target the two ROM revisions whose SHA-256 hashes are pinned in `tools/maps.py`. You supply the ROMs under the ignored `local/` folder; none are embedded. All addresses are hexadecimal. A banked CPU address `bb:aaaa` in `4000..7fff` is file offset `bb * 4000 + aaaa - 4000`. Routines and RAM traced so far are indexed in [ENGINE.md](ENGINE.md).

## Race backgrounds

Both games use the same format. Bank `20` starts with a table of **big-endian** 16-bit descriptor pointers. Each descriptor has seven selector bytes. Selector 0 picks two far pointers, each stored as **bank, high, low**, to the two map planes. Each plane is one width byte, one height byte, then `width * height` bytes in row order. The two plane bytes at each cell combine into an offset into a metatile definition bank.

| Table / routine | MRA file offset | MSUSA file offset |
| --- | --- | --- |
| Descriptor pointer table | `080000` | `080000` |
| Plane-pointer pairs, 6 bytes/entry | `0800c8` | `0800e1` |
| Graphics descriptor pointer table | `080152` | `080177` |
| Palette far pointers | `080297` | `0802e5` |
| Main race-map loader | `001d23` | `001921` |
| Horizontal terrain renderer | `001a40` | `001622` |
| Map row lookup | `001c43` | `001825` |

MRA has 23 descriptor slots; slot 7 is null, leaving 22 courses. MSUSA's first 21 slots are the 21 named courses, and slots 21–24 are extra slots exported separately (see below). Engine order differs from the course numbering used in filenames; `data/catalog.json` maps each engine index to its course name and file.

Selector 1 picks the graphics descriptor. Its first byte is the metatile definition bank. The next three bytes are a far pointer to the course's terrain resource (see [Terrain](#terrain)). The following two far pointers select the background tile graphics for VRAM banks 0 and 1. Each graphics resource starts with a block count, where zero means 256, followed by 16-byte blocks: one native 8×8 two-bitplane Game Boy tile each. Selector 4 picks a 64-byte RGB555 palette resource.

For map cell `(x,y)`, let `L` and `H` be the bytes from the two planes. The cell is a 32×32-pixel metatile made of 16 native tiles. Subtile `(sx,sy)`, each in `0..3`, is the two-byte `(tile_id, CGB_attribute)` pair at this **file offset**:

```text
metatile_bank * 0x4000 + L + H * 0x100 + sx * 0x400 + sy * 0x1000
```

CGB attribute bits select the palette (0–2), the graphics bank (3), horizontal flip (5), vertical flip (6) and priority (7). Priority does not change a background pixel's color. The games use signed background tile addressing: tile 0 starts at VRAM `9000` and tile 128 at `8800`. The raw graphics resources are already in tile-ID order.

Exported RGB values are the original five-bit components shifted left by three (0–248), matching PyBoy's rasterizer. Full-size images have no tint, color correction, antialiasing or resizing; only the overview grids are resized.

### Animation uploads

Some animated tiles are placeholders in the static graphics. `tools/trace_animations.py` runs the game's own animation routine with the frame counters forced to frame zero, and records each upload's source and destination at the graphics-upload routine. `tools/maps.py` applies those uploads before rasterizing.

| Routine | MRA | MSUSA |
| --- | --- | --- |
| Animation dispatch | `1e:421f` (skips the LY gate at `4215`) | `10:41e2` |
| Upload queue hook | `00:1477` | `00:10e5` |

The animation selector is at `ce7b` in MRA and `ce8c` in MSUSA. MSUSA's animation counters are in WRAM bank 5 at `dca0..dcb7`, including Yellowstone's 12 separate streams. MSUSA captures use `ce60=1`, the value a menu routine (`09:5918`) sets before racing. With `ce60=0` Nebraska's windmills don't animate, and in normal play they spin; no other course depends on the flag.

### Animated course loops

`tools/animations.py` hooks the games' stream helpers to recover each stream's destination tile range, frame source pointers, rate and starting phase. The helpers are MRA `1e:453e` / `1f:6578` and MSUSA `10:4407` / `11:7f95` / `17:48f9`. Results go to `data/animation_sequences.json`.

Each update adds an 8-bit rate to an 8-bit accumulator. On overflow, the frame index advances modulo the stream's frame count and a tile upload is queued. A stream's period in updates is `256 * frame_count / gcd(rate, 256 * frame_count)`, and a course's combined period is the least common multiple of its stream periods. The longest is 2,560 updates, about 42.86 seconds. All recovered streams write to disjoint tile ranges; the exporter rejects overlapping streams, which would need ordered replay.

The initializers are MRA `1e:4045` and MSUSA `10:404b`; they set the accumulator phases. MSUSA's initializer resets only nine frame-index bytes, but Yellowstone has twelve streams, so three indices inherit leftover boot/menu RAM (observed as `ee`). The exports clear the workspace first and then apply the ROM's accumulator phases, so every loop starts from frame zero.

Timing assumes one update per 70,224-cycle frame at 4,194,304 Hz (about 59.73 Hz). This is uninterrupted gameplay. Real play can run slower: a live MSUSA Los Angeles run showed 172 updates in 180 frames. Those skips depend on workload and are not baked in. MRA's scanline-gate skips are not modeled either.

`tools/export_animations.py` rasterizes straight to palette indices: the 32 original background colors plus one transparent index. It redraws only changed tiles and writes delta rectangles with Pillow's GIF encoder, without quantization or resizing. Identical adjacent frames are merged. Each frame delay is the difference between rounded absolute centisecond timestamps, so the total loop error stays under 5 ms. Viewers may enforce their own minimum delay on very short frames. Every frame uses disposal 1 and the shared palette; the first frame is a full canvas, so the loop restarts cleanly.

Outputs are `images/animated/MRA/` (20 GIFs), and `MSUSA/` (13). Each manifest lists the static courses as well as per-file hashes, frame counts, sizes, durations and timing error.

### Terrain

`tools/terrain.py` translates each game's point-terrain lookup: MSUSA `00:1f08` and MRA `00:2308`. The lookup uses the two map planes, the row table, and the terrain far pointer from the graphics descriptor (staged at `c60a..c60c` in MSUSA and `c62a..c62c` in MRA).

For combined map value `N = L + 256*H`, the cell's terrain record starts at resource offset `2*(N + floor(N/2))`. The record is two three-byte halves, one for each 16-pixel-wide half of the 32×32 cell. In each half, the first byte is a shape byte and the next two are terrain bytes. The shape byte, the first terrain byte's flip flags (bit 6 mirrors the half horizontally; bit 7 flips the comparison vertically), and a fixed-ROM table of 16-entry height profiles (starting at MSUSA `3980` and MRA `3380`) decide which terrain byte applies at each pixel. Shape family `70` is a vertical split at a column; the other families draw a height curve. This allows diagonal and curved boundaries inside a cell; it is not an 8×8 tile occupancy test. The record must stay within one ROM bank, because the CPU adds the offset without switching banks.

In MSUSA, the caller at `00:1ff9` masks the selected byte to six bits and dispatches through bank 1's table at `6ee2`, with code 0 and 1 handlers at `01:6eec` and `01:6eef`. The MRA caller and handler table have not been traced. What each code does in play is still unknown, so codes stay numeric.

| Codes used | Courses |
| --- | --- |
| 0, 1 | All 21 MSUSA courses; 17 MRA courses |
| 0, 1, 2 | MRA Moat Madness, Drawbridge Derby, Really Rapid Rapids, Fairground Follies |
| 0, 1, 2, 3 | MRA Pete's Hunting Hideout |

`tools/export_terrain.py` writes four images per course under `images/terrain/MRA/` and `MSUSA/`:

- `_codes.png`: grayscale, where each pixel value is the terrain code. Meant for scripts: the values are small, so it looks black in an image viewer.
- `_regions.png`: code 0 blue, 1 orange, 2 purple, 3 yellow.
- `_boundaries.png`: one-pixel pink lines at every code change, drawn over the native background.
- `_preview.png`: thicker lines for browsing, with a legend.

Each course also gets a JSON file with dimensions, resource offset and per-code pixel counts.

`tools/verify_terrain.py --game all` runs the original ROM lookup at every cell definition's corners, at seeded random points, and next to every transition, then compares against the translation. All 43 courses pass: 246,604 samples over 12,473 unique cell definitions. `--exports` additionally checks the saved PNGs at 132 points per course. This is sampled equivalence, not exhaustive per-pixel emulation. Reports are `data/terrain_verification_*.json`.

**Limits:** these are static point classifications. They do not show kart clearance (a kart is larger than a point), moving objects, camera limits, runtime map edits or which areas are reachable.

### Unmapped margins

Pete's Dungeon has 144 subtile lookups that land outside the switchable ROM window. All of them are the bottom-right 8×8 subtile of metatile 1024, the filler cell in the map's far-right margin: its lookup resolves to CPU address `$8000`, the start of VRAM, so the tile it shows depends on VRAM contents at the time. In gameplay footage these subtiles appear black, so they are drawn in the course's black (`OBSERVED_FILL` in `tools/maps.py`); the manifest still records the count. No other named course has such lookups.

### Four extra MSUSA slots

`tools/export_maps.py --extras` exports engine slots 21–24 to `images/reconstructed/MSUSA_extras/`, separate from the named courses. `data/msusa_extras.json` gives descriptive labels and per-slot limits.

| Slot | Descriptor | Graphics descriptor | Bytes | Rendering |
| --- | --- | --- | --- | --- |
| 21 | `0800c5` | `08027b` | 7 | Walled garden, 1248×704 |
| 22 | `0800cc` | `080282` | 7 | Log arena, 1024×864 |
| 23 | `0800d3` | `080289` | 7 | Scrambled graphics, 1216×864; conjectural reconstruction as an unfinished arena |
| 24 | `0800da` | `080290` | 10 | City arena, 1376×928; 145 transparent non-ROM subtiles |

The graphics descriptors for slots 21–23 end after the bank-0 graphics pointer; their length follows from the next pointer in the table. The regular loader `00:1921` ignores this and reads a bank-1 far pointer from the first three bytes of the next descriptor, giving fixed-ROM CPU addresses `2371`, `2375` and `2271`. These are not real bank-1 resources. No mapped subtile in slots 21–23 uses VRAM bank 1, so this does not affect the exports, and the exporter treats bank 1 as absent.

`tools/verify_msusa_extras.py` runs the original loader with the LCD on (its graphics transfer waits for VBlank). It compares both loaded map planes and the staged graphics bytes, then checks six renderer samples and three raster windows per slot. Every mapped subtile uses graphics inside its declared resource.

Slot 23 renders exactly what the loader stages, and it is still scrambled, so the source data itself is wrong or incomplete for it. Simple fixes (uniform tile-number offsets, a 128-tile rotation, each named course's tileset) found nothing coherent. `23_Unresolved_Graphics.png` stays as the diagnostic source rendering.

Slot 23's cell grid and terrain codes do read as an early City Arena with a different layout: an oceanside track with 90° turns, buildings along the top and planters inside. `tools/reconstruct_slot23.py` redraws it as `23_Unfinished_Arena.png` in three steps. First it maps each slot 23 cell ID to a City Arena ID with the same terrain template, choosing by how well neighbours join. Then it quilts the grid from those IDs and from City Arena cells copied at a few fixed offsets; road-coded cells keep their mapped ID. Finally it applies 181 hand patches, each taken from City Arena cells, which fix seams such as the shore steps, kerbs, planters and the bottom tip. Slot 23 road-codes the shoreline steps and a short alley in the top building, which the City Arena does not. The result is conjectural, not recovered from ROM, and `data/msusa_extras.json` labels it that way.

Slot 24's non-ROM reads depend on other memory and stay transparent. No route to these slots in normal play, in-game names, or alternate loader has been found, and no animation uploads are assumed for them.

## MRA exploration areas

The exploration engine is separate from the race engine and copies its routines from ROM into WRAM before running them. Six 17-byte map descriptors start at file offset `194997` (`65:4997`). Their pointers are stored as **bank, low, high**, unlike the race format. The graphics selector picks a 16-byte resource descriptor at `194500`.

A map resource starts with a mode byte (zero for all six), width and height in 8-pixel tiles, an attribute dictionary pointer and a token-stream pointer. The tile-ID dictionary follows the seven-byte header; each entry is four consecutive tiles. The token stream expands as follows:

| Token | Meaning |
| --- | --- |
| `00..fc` | Four-tile dictionary entry |
| `fe xx` | Entry `253 + xx` |
| `fd ll hh` | Entry `hhll` |
| `ff token count` | Repeat the following entry `count` times (zero means 256) |

The original decompressor is at file offset `1902d5` and runs from WRAM `c4d5`. It writes attributes to WRAM banks 2–4 and tile IDs to banks 5–7, and that plane order matters.

The graphics resource has three 16-bit pointers: the primary dictionary, the secondary stream and the secondary dictionary. The primary stream starts at byte 6. Graphics tokens emit byte pairs: `00` two zero bytes, `01` two `ff` bytes, `02` four zero bytes, `03` four `ff` bytes, `fe` two literal bytes, `04..fd` a dictionary pair, and `ff` ends the stream. The secondary stream loads VRAM bank 1 first; the primary stream then loads bank 0 and may run on into bank 1. `tools/hubs.py` keeps that order, including streams that cross the bank boundary in the middle of a token.

The palette pointer is part of the graphics descriptor and uses the same RGB555 conversion as the race maps. The game shows no title for these maps; they use the area names players know them by.

### Pluto holes

The source layouts include open and filled Pluto holes. In a fresh town state, runtime edits replace five 4×4-tile hole patches with grass (80 tiles), and those account for every difference between the source town layout and live RAM. The exports keep the source layout, so they show all holes at once, which never happens in play.

### Pluto digging stages

The dig engine is ROM bank `f0`; `tools/export_dig.py` documents the layout in its header. The stage index `ff fe` is world×4+stage. `f0:568a` holds one pointer per world (7) to a block: a pointer to the world header, then four 5-byte stage entries whose first three bytes are a far pointer (bank, low, high) to the stage data. The builder (RAM `c9e0`, copied from `f0:484e`) reads a 12-byte stage header, 16 two-byte object entries, the width and height in 32×32 metatiles, then one metatile id per cell. Metatile `e` has 16 (tile, attribute) pairs at `base + e*2 + k*0x200`, and the builder clears attribute bit 4. Row `r` of each metatile goes to WRAM bank `r+1` at `d000`, 8 bytes per cell, and `f0:42a8` copies the visible window from there into the tile map.

The world header gives the metatile bank and base, the graphics block (BG tiles in signed addressing, all in VRAM bank 0), five palette pointers (the second is the level palette) and five VRAM addresses of animated 2×2 tile groups. The fade-in at `f0:7cb5` steps by 10 and exits before its last step, so the screen keeps every channel at `(v*245+128)>>8`, which is what the exports use. Slot 0 is the bone (5 frames at `f7:6000`, played back and forth) and slot 3 a second collectible (4 frames at `f7:6440`); the graphics block holds placeholders for both, and the PNGs use frame 0.

## Full-screen backgrounds

The MRA world maps and the MSUSA course cards and US map are stored raw, with no compression. Each screen has a tile-ID plane and an attribute plane of the same size, one byte per 8-pixel tile, row by row, and two 256-tile graphics blocks. A plain banked copy (`00:1f82` in MRA, `00:1baa` in MSUSA) moves each block to WRAM bank 1 or 2, continuing into the next ROM bank when it crosses `8000`. A second copy then moves both blocks to VRAM banks 0 and 1 at `8800`–`97ff`. The screens use signed tile addressing, so tile ID `n` is always byte `n × 16` of its block. `tools/export_screens.py` writes them to `images/screens/`.

Neither game's loader writes palette RAM. Both unpack the RGB555 palette into a fade buffer at `cc40` (MRA `00:3147` stores 5-bit components; MSUSA `00:2b84` stores them multiplied by 8), and the VBlank fade uploads it.

### MRA world maps

Each of the five world maps has its own hard-coded loader in bank `0a`. The exporter reads each loader's operands rather than keeping a table:

| Map | Loader | Size (tiles) | Graphics (bank 0, bank 1) | Palette |
| --- | --- | --- | --- | --- |
| Mickey's Medieval Adventure | `0a:56f3` | 28×28 | `276e90`, `277e90` | `0a:6af4` |
| Donald's Pirate Adventure | `0a:5207` | 28×32 | `279840`, `27a840` | `0a:6bfc` |
| Minnie's Frontier Adventure | `0a:4fea` | 32×32 | `27a890` | `0a:6c3c` |
| Daisy's Wonderland Adventure | `0a:53f7` | 28×32 | `2785f0`, `2795f0` | `0a:6b9c` |
| Goofy's Fairground Adventure | `0a:4dbe` | 32×32 | `292620`, `293620` | `0a:6c7c` |

The planes are copied by `LD B,height / LD HL,ids / LD DE,d000 / LD A,width` (attributes to `d400`), with the plane bank in `ff96` when it is not `0a`. The palette is the `DE` operand of `LD B,8 / LD DE,palette / CALL 3147`. Wild West loads only a bank 0 block, and none of its cells use VRAM bank 1. The solid top band on Wild West and Fairground is in the plane data.

### MSUSA course cards

The card loader is `12:52b7`. Card order is the course index `ce5e`, which follows the US map from west to east, not the race order. If the language byte `ce38` is `81`, cards 12 and 13 (Gulf Coast, Louisiana) become 20 and 21 (Golfe du Mexique, Louisiane); if it is `82`, card 12 becomes 22 (Golfküste). There is no Secret Track! card. The exports include only the 20 English cards. The variants reuse their English card's tilemap except the name rows 15-17 and have their own graphics blocks, with the name painted into the art tiles, so there is no text-free version of any card in the ROM.

Two tables of six-byte entries hold two big-endian far pointers (**bank, high, low**) each: graphics blocks at `4a923` (`12:6923`) and planes at `4a9ad` (`12:69ad`), both indexed by the card number after language substitution. The planes are 20×18 tiles. The palette pointer table at `4aa37` (`12:6a37`) is indexed by `ce5e` itself, so the language variants keep their English card's palette.

### MSUSA US map

The US map is loaded by `09:6252`. It is 40×28 tiles (320×224 pixels), wider than the screen, and is scrolled from WRAM bank 2. Its tile IDs are at `27016`, its attributes at `27476`, its graphics blocks at `281730` and `282730` (`a0:5730`, `a0:6730`), and its palette at `26ce6` (`09:6ce6`, loaded by the screen setup at `09:6786`).

The raw planes contain plain placeholder squares where the state markers go. For each of the 20 states, `09:63b0` draws a 2×2 marker over them:

1. The state's slot is `byte(09:64f1 + state) >> 2`.
2. A source offset comes from the word table at `09:6479` if the state is reached (`state ≤ ce5e`), otherwise `09:64a1`. The target map cell comes from `09:64c9`. Sub-tiles step by 1 across and by 20 (source) or 40 (map) down.
3. The marker tile's graphics, `a0:5200 + byte(09:78d6 + source) × 16`, overwrite the graphics of the placeholder tile already at that cell, in the VRAM bank its attribute selects.
4. The cell's flip and palette bits (`67`) are replaced by `byte(09:7aa2 + source)`. Priority, VRAM bank and bit 4 (`98`) are kept.

State 0 always counts as reached, so the exports show progress 0 (only Los Angeles reached) and 19 (every state reached).

## Verification

| Script | Method | Result |
| --- | --- | --- |
| `verify_maps.py` | Calls the original horizontal renderer at six points per course and compares the tile IDs and attributes it emits. | 43/43; `data/verification.json` |
| `verify_pixels.py` | Loads the decoded tiles and palettes into the emulator with sprites off and compares three raster windows per course with the exported PNG. | 43/43, about 2.97 million pixels; `data/pixel_verification.json` |
| `verify_hubs.py` | Runs the original decompressors and compares both full map planes and 8,192 graphics bytes. | 6/6 exact; `data/hub_verification.json` |
| `verify_msusa_extras.py` | Original loader, renderer and rasterizer checks (see above). | 4/4 source-exact; `data/msusa_extras_verification.json` |
| `verify_animations.py` | Compares every accumulator, frame index and upload request with the original code over each course's full cycle. | 10,762 updates; `data/animation_verification.json` |
| `verify_animation_exports.py` | Checks every GIF frame header, duration and hash, three full-map raster phases, and the first three decoded frames at native size. Later frames are checked structurally. | 33 GIFs; `data/animation_export_verification.json` |
| `verify_terrain.py` | Sampled comparison against the original point lookup (see [Terrain](#terrain)). | 43/43; `data/terrain_verification_*.json` |
| `verify_screens.py` | Runs each original full-screen loader and compares the tile map (VRAM `9800`, or WRAM bank 2 for the US map, markers included), every tile the screen uses, and the palette in the `cc40` fade buffer. The US map palette is checked statically against the code at `09:6786`. | 30/30 exact; `data/screen_verification.json` |
| `verify_dig.py` | Replays a Pluto hole entry from a local save state, forces each stage index and compares the WRAM metatile grid, the faded palette buffer and hardware palettes 4-7, and every BG tile in VRAM (animated groups against their `f7` frames). | 28/28; `data/dig_verification.json` |

These checks confirm that the source data is decoded correctly. They do not show that every pixel can be reached by the gameplay camera, and they cover background layers only: sprites, pickups, opponents, some start/finish markers, state-dependent scenery and runtime map edits are outside their scope.

The emulator interface is [PyBoy](https://docs.pyboy.dk/api/pyboy.html). `tools/gbdis.py` takes file offsets and disassembles a range using PyBoy's opcode tables. Generated listings and save states stay in the ignored `local/` folder.
