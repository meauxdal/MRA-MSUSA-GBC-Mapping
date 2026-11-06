# Mickey's Racing Adventure and Mickey's Speedway USA: GBC maps

Pixel-exact maps of every course in *Mickey's Racing Adventure* (Game Boy Color, 1999) and *Mickey's Speedway USA* (Game Boy Color, 2001), decoded directly from the original ROMs and checked against the games' own code.

## Maps

| Set | Overview | Per-map files |
| --- | --- | --- |
| MRA courses (22) | [Grid](images/reconstructed/MRA_grid.png) | [Maps](images/reconstructed/MRA/) · [Manifest](images/reconstructed/MRA/manifest.json) |
| MSUSA courses (21) | [Grid](images/reconstructed/MSUSA_grid.png) | [Maps](images/reconstructed/MSUSA/) · [Manifest](images/reconstructed/MSUSA/manifest.json) |
| MRA exploration areas (6) | [Grid](images/reconstructed/MRA_hubs_grid.png) | [Maps](images/reconstructed/MRA_hubs/) · [Manifest](images/reconstructed/MRA_hubs/manifest.json) |
| MSUSA extra slots (4, research) | [Grid](images/reconstructed/MSUSA_extras_grid.png) | [Maps](images/reconstructed/MSUSA_extras/) · [Manifest](images/reconstructed/MSUSA_extras/manifest.json) |
| MRA animated courses (20) | | [GIFs](images/animated/MRA/) · [Manifest](images/animated/MRA/manifest.json) |
| MSUSA animated courses (12 + 1 variant) | | [GIFs](images/animated/MSUSA/) · [Variant](images/animated/MSUSA_special/) · [Manifest](images/animated/MSUSA/manifest.json) |
| MRA terrain (22) | [Regions](images/terrain/MRA_regions_grid.png) · [Boundaries](images/terrain/MRA_boundaries_grid.png) | [Maps](images/terrain/MRA/) · [Manifest](images/terrain/MRA/manifest.json) |
| MSUSA terrain (21) | [Regions](images/terrain/MSUSA_regions_grid.png) · [Boundaries](images/terrain/MSUSA_boundaries_grid.png) | [Maps](images/terrain/MSUSA/) · [Manifest](images/terrain/MSUSA/manifest.json) |

Full-size PNGs and GIFs are at native resolution with the original palettes: no scaling, filtering or color correction. Only the overview grids are resized. Each manifest records the source ROM addresses, dimensions and SHA-256 hashes for its files.

## What each set shows

- **Courses:** the complete background layer: both map planes, metatiles, tile graphics, flips, palettes, and the first frame of animated tiles.
- **Exploration areas:** the six MRA overworld maps, in their source layout. Pluto holes are all shown; in play, which holes are visible depends on game state.
- **Animated courses:** looping GIFs of every course with animated background tiles. Frame order, speed and starting phase come from the ROM, and timing is accurate to within 5 ms per loop at the nominal 59.73 Hz. The other courses have no animated tiles. The MSUSA variant is Nebraska's alternate animation branch (`ce60=1`).
- **Terrain:** the terrain code the game reads at every pixel, exported as a raw code image, a colored region map, a boundary overlay on the background, and a browsing preview. Codes are numbered, not named: what each code does in play (road, wall, slow ground) has not been traced yet.
- **MSUSA extra slots:** four engine slots after the 21 named courses. Two are clean arenas (a walled garden and a log arena), one has scrambled graphics, and one has 145 tiles with no ROM source. Whether any of them is reachable in normal play is unknown.

## Not included

These are background layers, not gameplay screenshots. Sprites, karts, pickups, some start and finish markers, and scenery that changes during play are not drawn. MRA's Pete's Dungeon has 144 tiles in its far-right margin that read from outside ROM; they are left transparent rather than guessed.

## Reproduce

You need Python 3.12 and your own copies of both ROMs. The tools never download ROMs. Put the ROMs in `local/` (ignored by git) under their standard names. The tools check SHA-256 hashes and refuse any other revision.

```powershell
python -m pip install -r requirements.txt

# Static maps (about 11 s)
python tools/trace_animations.py
python tools/export_maps.py
python tools/export_maps.py --extras
python tools/export_hubs.py

# Animated GIFs (about 90 s). Add --special to these two commands and to both animation verify commands to build and check the Nebraska variant.
python tools/animations.py
python tools/export_animations.py

# Terrain
python tools/export_terrain.py

# Verification against the original game code
python tools/verify_maps.py
python tools/verify_pixels.py
python tools/verify_hubs.py
python tools/verify_msusa_extras.py
python tools/verify_animations.py
python tools/verify_animation_exports.py
python tools/verify_terrain.py --game all
```

Verification reports are written to [`data/`](data/). The verify scripts need [PyBoy](https://github.com/Baekalfen/PyBoy) (included in `requirements.txt`).

## Documentation

- [Map formats and evidence](docs/FORMAT.md): how each data format is laid out, how it was decoded, and how the decoding was verified.
- [Engine notes](docs/ENGINE.md): ROM routines, RAM layout, and runtime behavior traced so far, plus open questions.
