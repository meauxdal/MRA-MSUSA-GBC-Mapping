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

The animation selector is at `ce7b` in MRA and `ce8c` in MSUSA. MSUSA's animation counters are in WRAM bank 5 at `dca0..dcb7`, including Yellowstone's 12 separate streams. The default capture uses `ce60=0`. A separate capture, `msusa_animations_special.json`, records the `ce60=1` branch, which changes Nebraska's animation uploads. What sets that branch during play is unknown, so it is not applied to the default maps.

### Animated course loops

`tools/animations.py` hooks the games' stream helpers to recover each stream's destination tile range, frame source pointers, rate and starting phase. The helpers are MRA `1e:453e` / `1f:6578` and MSUSA `10:4407` / `11:7f95` / `17:48f9`. Results go to `data/animation_sequences.json`, or `animation_sequences_special.json` with `--special`.

Each update adds an 8-bit rate to an 8-bit accumulator. On overflow, the frame index advances modulo the stream's frame count and a tile upload is queued. A stream's period in updates is `256 * frame_count / gcd(rate, 256 * frame_count)`, and a course's combined period is the least common multiple of its stream periods. The longest is 2,560 updates, about 42.86 seconds. All recovered streams write to disjoint tile ranges; the exporter rejects overlapping streams, which would need ordered replay.

The initializers are MRA `1e:4045` and MSUSA `10:404b`; they set the accumulator phases. MSUSA's initializer resets only nine frame-index bytes, but Yellowstone has twelve streams, so three indices inherit leftover boot/menu RAM (observed as `ee`). The exports clear the workspace first and then apply the ROM's accumulator phases, so every loop starts from frame zero.

Timing assumes one update per 70,224-cycle frame at 4,194,304 Hz (about 59.73 Hz). This is uninterrupted gameplay. Real play can run slower: a live MSUSA Los Angeles run showed 172 updates in 180 frames. Those skips depend on workload and are not baked in. MRA's scanline-gate skips are not modeled either.

`tools/export_animations.py` rasterizes straight to palette indices: the 32 original background colors plus one transparent index. It redraws only changed tiles and writes delta rectangles with Pillow's GIF encoder, without quantization or resizing. Identical adjacent frames are merged. Each frame delay is the difference between rounded absolute centisecond timestamps, so the total loop error stays under 5 ms. Viewers may enforce their own minimum delay on very short frames. Every frame uses disposal 1 and the shared palette; the first frame is a full canvas, so the loop restarts cleanly.

Outputs are `images/animated/MRA/` (20 GIFs), `MSUSA/` (12) and `MSUSA_special/` (Nebraska only). Each manifest lists the static courses as well as per-file hashes, frame counts, sizes, durations and timing error.

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

- `_codes.png`: grayscale, where each pixel value is the terrain code.
- `_regions.png`: code 0 blue, 1 orange, 2 purple, 3 yellow.
- `_boundaries.png`: one-pixel pink lines at every code change, drawn over the native background.
- `_preview.png`: thicker lines for browsing, with a legend.

Each course also gets a JSON file with dimensions, resource offset and per-code pixel counts.

`tools/verify_terrain.py --game all` runs the original ROM lookup at every cell definition's corners, at seeded random points, and next to every transition, then compares against the translation. All 43 courses pass: 246,604 samples over 12,473 unique cell definitions. `--exports` additionally checks the saved PNGs at 132 points per course. This is sampled equivalence, not exhaustive per-pixel emulation. Reports are `data/terrain_verification_*.json`.

**Limits:** these are static point classifications. They do not show kart clearance (a kart is larger than a point), moving objects, camera limits, runtime map edits or which areas are reachable.

### Unmapped margins

Pete's Dungeon has 144 subtile lookups in the far-right margin of its map that land outside the switchable ROM window. They read non-ROM memory, so they are exported as transparent rather than guessed, and the manifest records the count. No other course has such lookups. Whether the camera can reach this margin is unverified.

### Four extra MSUSA slots

`tools/export_maps.py --extras` exports engine slots 21–24 to `images/reconstructed/MSUSA_extras/`, separate from the named courses. `data/msusa_extras.json` gives descriptive labels and per-slot limits.

| Slot | Descriptor | Graphics descriptor | Bytes | Rendering |
| --- | --- | --- | --- | --- |
| 21 | `0800c5` | `08027b` | 7 | Walled garden, 1248×704 |
| 22 | `0800cc` | `080282` | 7 | Log arena, 1024×864 |
| 23 | `0800d3` | `080289` | 7 | Scrambled graphics, 1216×864 |
| 24 | `0800da` | `080290` | 10 | City arena, 1376×928; 145 transparent non-ROM subtiles |

The graphics descriptors for slots 21–23 end after the bank-0 graphics pointer; their length follows from the next pointer in the table. The regular loader `00:1921` ignores this and reads a bank-1 far pointer from the first three bytes of the next descriptor, giving fixed-ROM CPU addresses `2371`, `2375` and `2271`. These are not real bank-1 resources. No mapped subtile in slots 21–23 uses VRAM bank 1, so this does not affect the exports, and the exporter treats bank 1 as absent.

`tools/verify_msusa_extras.py` runs the original loader with the LCD on (its graphics transfer waits for VBlank). It compares both loaded map planes and the staged graphics bytes, then checks six renderer samples and three raster windows per slot. Every mapped subtile uses graphics inside its declared resource.

Slot 23 renders exactly what the loader stages, and it is still scrambled, so the source data itself is wrong or incomplete for it. A heuristic search over simple fixes (uniform tile-number offsets, a 128-tile rotation, each named course's tileset) found nothing coherent, though it was not exhaustive. The fault could be in tile numbering, the referenced tileset, or the metatile definitions. Slot 24's non-ROM reads depend on other memory and stay transparent. No route to these slots in normal play, in-game names, or alternate loader has been found, and no animation uploads are assumed for them.

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

The palette pointer is part of the graphics descriptor and uses the same RGB555 conversion as the race maps. The six map names are visual descriptions, not in-game titles.

### Pluto holes

The source layouts include open and filled Pluto holes. In a fresh town state, runtime edits replace five 4×4-tile hole patches with grass (80 tiles), and those account for every difference between the source town layout and live RAM. The exports keep the source layout, so they show all holes at once, which never happens in play.

## Verification

| Script | Method | Result |
| --- | --- | --- |
| `verify_maps.py` | Calls the original horizontal renderer at six points per course and compares the tile IDs and attributes it emits. | 43/43; `data/verification.json` |
| `verify_pixels.py` | Loads the decoded tiles and palettes into the emulator with sprites off and compares three raster windows per course with the exported PNG. | 43/43, about 2.97 million pixels; `data/pixel_verification.json` |
| `verify_hubs.py` | Runs the original decompressors and compares both full map planes and 8,192 graphics bytes. | 6/6 exact; `data/hub_verification.json` |
| `verify_msusa_extras.py` | Original loader, renderer and rasterizer checks (see above). | 4/4 source-exact; `data/msusa_extras_verification.json` |
| `verify_animations.py` | Compares every accumulator, frame index and upload request with the original code over each course's full cycle. | 10,635 updates (2,080 for the variant); `data/animation_verification*.json` |
| `verify_animation_exports.py` | Checks every GIF frame header, duration and hash, three full-map raster phases, and the first three decoded frames at native size. Later frames are checked structurally. | 32 GIFs + variant; `data/animation_export_verification*.json` |
| `verify_terrain.py` | Sampled comparison against the original point lookup (see [Terrain](#terrain)). | 43/43; `data/terrain_verification_*.json` |

These checks confirm that the source data is decoded correctly. They do not show that every pixel can be reached by the gameplay camera, and they cover background layers only: sprites, pickups, opponents, some start/finish markers, state-dependent scenery and runtime map edits are outside their scope.

The emulator interface is [PyBoy](https://docs.pyboy.dk/api/pyboy.html). `tools/gbdis.py` takes file offsets and disassembles a range using PyBoy's opcode tables. Generated listings and save states stay in the ignored `local/` folder.
