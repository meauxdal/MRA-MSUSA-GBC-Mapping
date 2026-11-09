# Building the maps

You need Python 3.12 and your own copies of both ROMs. The tools never download ROMs. Put the ROMs in `local/` (ignored by git) under their standard names. The tools check SHA-256 hashes and refuse any other revision.

```powershell
python -m pip install -r requirements.txt

# Static maps (about 11 s)
python tools/trace_animations.py
python tools/export_maps.py
python tools/export_maps.py --extras
python tools/reconstruct_slot23.py
python tools/export_hubs.py
python tools/export_screens.py

# Animated GIFs (about 90 s)
python tools/animations.py
python tools/export_animations.py

# Terrain
python tools/export_terrain.py

# README showcase GIFs, thumbnails and map tables
python tools/export_showcase.py
python tools/export_readme.py

# Verification against the original game code
python tools/verify_maps.py
python tools/verify_pixels.py
python tools/verify_hubs.py
python tools/verify_msusa_extras.py
python tools/verify_animations.py
python tools/verify_animation_exports.py
python tools/verify_terrain.py --game all
python tools/verify_screens.py
```

Verification reports are written to [`data/`](../data/). The verify scripts need [PyBoy](https://github.com/Baekalfen/PyBoy) (included in `requirements.txt`).

`export_readme.py` rewrites only the tables between `<!-- table:NAME -->` and `<!-- /table -->` markers in the README; the text around them is edited by hand. `reconstruct_slot23.py --city-grid FILE` also writes a labelled City Arena grid, for picking the source cells of new slot 23 patches.

Each output folder has a `manifest.json` recording the source ROM addresses, dimensions and SHA-256 hash of every file; [FORMAT.md](FORMAT.md) describes them.
