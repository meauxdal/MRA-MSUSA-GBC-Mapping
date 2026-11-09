# Engine notes

This page lists the code and RAM traced in both games. Data formats are described in [FORMAT.md](FORMAT.md). Addresses are hexadecimal: `bb:aaaa` is a banked CPU address (file offset `bb * 4000 + aaaa - 4000`), `00:aaaa` is fixed ROM, and bare four-digit addresses in `c000..dfff` are WRAM. Everything here was confirmed by running or hooking the original code in PyBoy unless it is marked as a hypothesis.

## Routine index

### Race maps (both games)

| Purpose | MRA | MSUSA |
| --- | --- | --- |
| Main race-map loader | `00:1d23` | `00:1921` |
| Horizontal terrain renderer | `00:1a40` | `00:1622` |
| Map row lookup | `00:1c43` | `00:1825` |
| Point-terrain lookup | `00:2308` | `00:1f08` |
| Terrain lookup core | `00:2348..23da` | `00:1f48..1fda` |
| Terrain height profiles (16 bytes each) | from `00:3380` | from `00:3980` |
| Terrain code dispatch | not traced | caller `00:1ff9`, table `01:6ee2` |
| Animation dispatch | `1e:421f` (LY gate at `4215`) | `10:41e2` |
| Animation initializer | `1e:4045` | `10:404b` |
| Animation stream helpers | `1e:453e`, `1f:6578` | `10:4407`, `11:7f95`, `17:48f9` |
| Tile upload queue | `00:1477` | `00:10e5` |

### MRA exploration engine

| Purpose | Address |
| --- | --- |
| Map descriptors (6 × 17 bytes) | `65:4997` (file `194997`) |
| Graphics resource descriptors (16 bytes) | file `194500` |
| Map decompressor | file `1902d5`, runs at WRAM `c4d5` |

The decompressor writes attributes to WRAM banks 2–4 and tile IDs to banks 5–7.

### Full-screen backgrounds

| Purpose | Address |
| --- | --- |
| Banked tile copy to WRAM (A bank, B WRAM bank, C tiles, 0 = 256) | MRA `00:1f82`, MSUSA `00:1baa` |
| Palette to `cc40` fade buffer (B palettes from DE) | MRA `00:3147`, MSUSA `00:2b84` |
| WRAM banks 1/2 → VRAM banks 0/1 at `8800` | MRA `04:5b4a` |
| MRA world map loaders | `0a:56f3`, `0a:5207`, `0a:4fea`, `0a:53f7`, `0a:4dbe` |
| MSUSA course card loader | `12:52b7` |
| MSUSA US map loader / palette setup | `09:6252` / `09:6786` |
| MSUSA US map state markers | `09:63b0` (called for 20 states × 4 sub-tiles) |

See [Full-screen backgrounds](FORMAT.md#full-screen-backgrounds) for the data layout.

### MSUSA gameplay

| Purpose | Address |
| --- | --- |
| Main loop | `00:033f..04d6` |
| Idle wait (HALT until `c63b` is set) | `00:04de..04e4` |
| Player update call | `00:0362..036a` → bank `[c618]`, trampoline `c619` → `01:44de` |
| Player update entry | `01:44de` |
| Per-kart physics | `01:55dd` |
| Multi-kart update loops (karts `c0`, `c1`, `c2`) | `01:4500`, `01:452c` |
| Kart state jump table | `01:56b5` |
| State countdown handlers | `01:573f..5878` |
| Course script table (42-byte records) | `01:7774` |
| Course script installer | `01:749d` (copies to trampoline `c626..c629`) |
| Course script call site | `00:0378..0380` |
| Terrain code 0 / 1 handlers | `01:6eec` / `01:6eef` |

## RAM

| Address | Game | Meaning |
| --- | --- | --- |
| `c60a..c60c` | MSUSA | Staged terrain resource far pointer |
| `c62a..c62c` | MRA | Staged terrain resource far pointer |
| `c618`, `c619` | MSUSA | Bank byte and trampoline for the player update |
| `c626..c629` | MSUSA | Course script trampoline |
| `c63b` | MSUSA | Flag the idle loop waits on |
| `cc40` | both | Palette fade buffer, 3 bytes per color (MRA 5-bit, MSUSA ×8) |
| `ce38` | MSUSA | Language for the course cards: `81` French, `82` German |
| `ce5e` | MSUSA | Course index in US-map order; also the US map progress (states up to it are drawn reached) |
| `ce7b` | MRA | Animation selector |
| `ce8c` | MSUSA | Animation selector |
| `ce60` | MSUSA | Mode flag, set to 1 by a menu routine at `09:5918` and cleared by others (such as `09:58b0`). Read in many banks. With 0, Nebraska's windmills don't animate; normal play has them spinning, so captures use 1 |
| `dca0..dcb7` (WRAM bank 5) | MSUSA | Animation stream counters |
| `c000..c3ff` | MSUSA | Four kart records (below) |
| `ff9d` | MSUSA | High byte of the current kart record (`c0..c3`) |

## MSUSA kart records

Each kart has a 256-byte record at `c000`, `c100`, `c200` or `c300`. Code sets `H` from `[ff9d]` and uses `L` as the field offset, which is why direct `c0xx` references are rare in the ROM. `01:44de` sets `ff9d = c0` and then calls `01:55dd`, `01:53aa` and `01:5117` for the player.

| Offset | Meaning |
| --- | --- |
| `00..05` | Position |
| `0d` | Sprite / heading; flag bits at `33` and `34` add 8 |
| `28..29` | Probably vertical velocity |
| `33`, `34` | Flags |
| `7e`, `80` | Per-frame position deltas |
| `88` | Track segment index |
| `ae` | State countdown, dispatched through `01:56b5` |
| `b0..b3` | Sprite animation cycler, copied to `c5d6` |

`01:55dd` updates position, speed, heading and the deltas. Wall contact does not go through the `ae` state machine: `ae` stayed 0 throughout a 300-frame fence scrape. Writing large jumps directly to the position bytes hangs the game.

Example segment indices on Los Angeles: the lower boardwalk goes from `15` to `16`, and the U-turn after it from `16` to `17` to `18`.

## MSUSA course scripts and jumps

The course script table at `01:7774` has one 42-byte record per course in engine order (index 0 is Los Angeles). Its script pointer is stored big-endian as bank, high, low, and is installed into the trampoline at `c626..c629` by `01:749d` and called from `00:0378..0380`.

Scripted jumps live in bank `13`. A launch script sets `ae = 25`, speed `380`, aims the heading at a fixed point and sets `28..29 = fda0`. `13:5031` is a bare `RET`, used by courses without a script.

| Course | Script |
| --- | --- |
| Los Angeles | `13:4ff0` (only sets flag bit `33.0` at segments `30` and `34`) |
| San Francisco | `13:4906` |
| Milwaukee | `13:47eb` |
| Gulf Coast | `13:4c0d` |
| Louisiana | `13:43e5` |
| Indianapolis | `13:43b4` |
| Boston | `13:4211` |
| Florida Everglades | `13:4252` |
| Washington D.C. | `13:4000` (segments `15`, `16`, `2d`, `2e`) |

## Timing

The games run at one main-loop pass per 70,224-cycle frame at 4,194,304 Hz (about 59.73 Hz). The main loop finishes early and HALTs in the idle wait, so sampling the PC at VBlank always lands on `04df`. Under load, MSUSA skips updates: a live Los Angeles run showed 172 updates in 180 frames. MRA's animation dispatch also skips updates through an LY gate at `1e:4215`.

## Open questions

- **Terrain behavior:** what each terrain code does in play, how kart clearance is tested against it, and where MRA dispatches its codes.
- **MSUSA "phantom hit":** a rare unexplained knockback in Time Trial, best known at the end of the fence at the Los Angeles lower-boardwalk U-turn (around map pixel 515,400). Scripted jumps and visible AI karts have been ruled out. The two remaining hypotheses are a wall push-out error when a contact probe lands inside a thin wall or on a 256-pixel seam, and stale records in `c100..c3ff` that are still collision-tested in Time Trial.
- **MSUSA extra slots 21–24:** whether any normal mode loads them, and where slot 23's correct graphics come from.
- **`ce60`:** which menu choice the setting routine at `09:5918` belongs to, and what else the flag changes.
- **Runtime layers:** sprites, pickups, markers, Pluto-hole state, and runtime map edits are not yet traced.

## Research tools

`tools/session.py` and `tools/emulator.py` boot the ROMs in PyBoy for bounded experiments. `tools/gbdis.py` disassembles a file-offset range. ROMs, save states and research dumps belong in the ignored `local/` folder.
