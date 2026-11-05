# Mickey's Racing Adventure and Mickey's Speedway USA GBC Mapping
Mapping *Mickey's Racing Adventure* (Game Boy Color, 1999) and *Mickey's Speedway USA* (Game Boy Color, 2001).

## Reconstructed backgrounds

Native-resolution backgrounds now export from the supplied ROMs: **22 MRA
courses, 21 MSUSA courses, and 6 MRA exploration maps**. Originals below are
preserved. The new maps combine both map planes, metatile definitions, graphics
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

### Reproduce

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

## Historical previews

MRA progress:
![mra-grid](/images/MRA_grid.png)

MSUSA progress:
![msusa-grid](/images/MSUSA_grid.png)
