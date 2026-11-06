# Mickey's Racing Adventure and Mickey's Speedway USA GBC Mapping
Mapping *Mickey's Racing Adventure* (Game Boy Color, 1999) and *Mickey's Speedway USA* (Game Boy Color, 2001).

## Reconstructed backgrounds

Native-resolution backgrounds now export from the supplied ROMs: **22 MRA
courses, 21 MSUSA courses, and 6 MRA exploration maps**. The
[historical previews](docs/HISTORICAL_PREVIEWS.md) are preserved separately.
The new maps combine both map planes, metatile definitions, graphics
banks, tile flips, original palettes, and frame-zero animation uploads.

These are **background layers**, not finished gameplay composites. Sprites,
state-dependent objects and some markers remain to be mapped. Pluto holes are
preserved in the source exploration layouts; the game can hide them at runtime.
Pete's Dungeon has 144 unmapped 8-pixel tiles in its far-right margin, shown
transparent. [Format, evidence, and limitations](docs/FORMAT.md) describe the
validation precisely.

| Outputs | Overview | Per-map files and provenance |
| --- | --- | --- |
| MRA courses | [Grid](images/reconstructed/MRA_grid.png) | [Maps](images/reconstructed/MRA/) · [Manifest](images/reconstructed/MRA/manifest.json) |
| MSUSA courses | [Grid](images/reconstructed/MSUSA_grid.png) | [Maps](images/reconstructed/MSUSA/) · [Manifest](images/reconstructed/MSUSA/manifest.json) |
| MSUSA extra slots (research) | [Grid](images/reconstructed/MSUSA_extras_grid.png) | [Maps](images/reconstructed/MSUSA_extras/) · [Manifest](images/reconstructed/MSUSA_extras/manifest.json) |
| MRA exploration | [Grid](images/reconstructed/MRA_hubs_grid.png) | [Maps](images/reconstructed/MRA_hubs/) · [Manifest](images/reconstructed/MRA_hubs/manifest.json) |

The four additional MSUSA slots are exported separately from the 21 named
courses. Slots 21 (walled garden) and 22 (log arena) are coherent source
backgrounds. Slot 23 remains a **scrambled diagnostic rendering**; slot 24 (city
arena) has **145 non-ROM subtile reads**, shown transparent. These labels describe
their appearance; in-game names and gameplay reachability are unverified.
Original-loader, terrain-renderer and pixel checks pass for the decoded source
data, which does not resolve the incomplete graphics or establish playability.

### Terrain boundary prototype

Nebraska now has [native terrain boundaries](images/terrain/MSUSA/11_Nebraska_boundaries.png),
a [colored region mask](images/terrain/MSUSA/11_Nebraska_regions.png) (code 0 blue,
code 1 orange), and a [browsing preview](images/terrain/MSUSA/11_Nebraska_preview.png).
The decoder matches 7,600 original-ROM point lookups across all 380 distinct
Nebraska cell definitions. These are source terrain-code regions; behavior
labels, vehicle clearance and reachable bounds remain unverified. See
[format and reproduction instructions](docs/FORMAT.md#source-terrain-boundaries-msusa-prototype).

### Animated backgrounds

Native-size looping GIFs now include **20 MRA courses and 12 MSUSA courses**
with tile-animation streams. The other courses have no tile-animation streams
in their selected dispatch and retain their static PNGs. A separate Nebraska
GIF preserves the MSUSA `CE60=1` branch without applying it to the default map.

- [MRA GIFs and manifest](images/animated/MRA/)
- [MSUSA GIFs and manifest](images/animated/MSUSA/)
- [Nebraska variant](images/animated/MSUSA_special/)
- [Yellowstone detail preview](images/animated/Yellowstone_detail.gif)

GIFs preserve the original map dimensions and colors. Each independent stream
uses its ROM frame order, accumulator rate and initializer phase, over a complete
combined loop. Timing uses nominal gameplay updates at ~59.73 Hz, rounded to
GIF's 10 ms units with less than 5 ms total error per loop. Gameplay stalls,
pauses, sprites, hub animations and runtime map edits are not included.

```powershell
python tools/animations.py
python tools/verify_animations.py
python tools/export_animations.py
python tools/verify_animation_exports.py
python tools/animations.py --special
python tools/verify_animations.py --special
python tools/export_animations.py --special
python tools/verify_animation_exports.py --special
```

Full GIF export takes roughly 90 seconds on the development machine and retains
only a few indexed canvases at once. The longest combined loops last ~42.86 s.

### Reproduce static maps

Use Python 3.12 and install `requirements.txt`. Place both supported ROMs in
ignored `local/`, retaining the supplied game names. SHA-256 checks reject other
revisions before decoding; ROMs are never downloaded by these tools.

```powershell
python -m pip install -r requirements.txt
python tools/trace_animations.py
python tools/export_maps.py
python tools/export_hubs.py
python tools/verify_maps.py
python tools/verify_pixels.py
python tools/verify_hubs.py
python tools/export_maps.py --extras
python tools/verify_msusa_extras.py
```

The complete export takes about 11 seconds on the development machine; the
bounded verification scripts take a few seconds each. `tools/gbdis.py` provides
targeted range disassembly after PyBoy is installed locally under
`local/tools/python`. Research states and raw dumps remain private in `local/`.
