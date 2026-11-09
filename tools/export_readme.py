"""Write README thumbnails and the per-set map tables.

Reads the exported maps and their manifests, writes small thumbnails to
images/thumbs/, and replaces each generated table in README.md. A table sits
between "<!-- table:NAME -->" and "<!-- /table -->"; the prose around it is
hand-written. Run after all the export tools.
"""
import html
import json
from pathlib import Path
from urllib.parse import quote
from PIL import Image
from maps import ROOT

IMG = ROOT/"images"
THUMBS = IMG/"thumbs"
BOX = (180, 180)    # thumbnail bounds; four per row fits GitHub's page width
PER_ROW = 4


def link(path, text):
    return f'<a href="{quote(path.relative_to(ROOT).as_posix())}">{text}</a>'


def thumb(src, set_name):
    """Write a thumbnail of src and return its path."""
    dst = THUMBS/set_name/(src.stem+".png")
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    im.thumbnail(BOX, Image.LANCZOS)
    im.save(dst, optimize=True)
    return dst


def cell(name, src, set_name, links):
    """One table cell: linked thumbnail, name, then the file links."""
    t = thumb(src, set_name)
    w, h = Image.open(t).size
    img = (f'<img src="{quote(t.relative_to(ROOT).as_posix())}" '
           f'width="{w}" height="{h}" alt="{html.escape(name)}">')
    files = " · ".join(link(p, text) for text, p in links)
    return (f'<td align="center" valign="top">{link(src, img)}<br>'
            f"{html.escape(name)}<br><sub>{files}</sub></td>")


def table(cells):
    rows = [cells[i:i+PER_ROW] for i in range(0, len(cells), PER_ROW)]
    body = "\n".join("<tr>\n" + "\n".join(r) + "\n</tr>" for r in rows)
    return f"<table>\n{body}\n</table>"


def manifest(folder):
    entries = json.loads((folder/"manifest.json").read_text())
    return sorted(entries, key=lambda e: e["file"])


def courses(game):
    static = IMG/"reconstructed"/game
    animated = IMG/"animated"/game
    cells = []
    for e in manifest(static):
        src = static/e["file"]
        links = [("PNG", src)]
        gif = animated/(src.stem+".gif")
        if gif.exists():
            links.append(("GIF", gif))
        cells.append(cell(e["name"], src, f"{game}_courses", links))
    return cells


def terrain(game):
    folder = IMG/"terrain"/game
    cells = []
    for e in manifest_terrain(folder):
        files = {k: folder/v["file"] for k, v in e["files"].items()}
        links = [(k.capitalize(), files[k])
                 for k in ("regions", "boundaries") if k in files]
        cells.append(cell(e["name"], files["regions"], f"{game}_terrain",
                          links))
    return cells


def manifest_terrain(folder):
    entries = json.loads((folder/"manifest.json").read_text())
    return sorted(entries, key=lambda e: e["files"]["regions"]["file"])


def hubs():
    folder = IMG/"reconstructed/MRA_hubs"
    return [cell(e["name"], folder/e["file"], "MRA_overworld",
                 [("PNG", folder/e["file"])]) for e in manifest(folder)]


def arenas():
    folder = IMG/"reconstructed/MSUSA_extras"
    cells = []
    for e in manifest(folder):
        name = e["name"].split(": ", 1)[1].capitalize()
        raw = folder/e["file"]
        rec = e.get("reconstruction")
        if rec:
            src = folder/rec["filename"]
            links = [("Reconstruction", src), ("Raw", raw)]
            name += " (conjectural)"
        else:
            src, links = raw, [("PNG", raw)]
        cells.append(cell(f"{e['index']}: {name}", src, "MSUSA_arenas",
                          links))
    return cells


def screens(group):
    folder = IMG/"screens"/group
    return [cell(e["name"], folder/e["file"], group,
                 [("PNG", folder/e["file"])]) for e in manifest(folder)]


TABLES = {
    "msusa-courses": lambda: courses("MSUSA"),
    "msusa-arenas": arenas,
    "msusa-us-map": lambda: screens("MSUSA_us_map"),
    "msusa-cards": lambda: screens("MSUSA_cards"),
    "msusa-terrain": lambda: terrain("MSUSA"),
    "mra-courses": lambda: courses("MRA"),
    "mra-overworld": hubs,
    "mra-worlds": lambda: screens("MRA_worlds"),
    "mra-dig": lambda: screens("MRA_dig"),
    "mra-terrain": lambda: terrain("MRA"),
}


def main():
    readme = ROOT/"README.md"
    text = readme.read_text(encoding="utf-8")
    for name, build in TABLES.items():
        start = f"<!-- table:{name} -->"
        end = "<!-- /table -->"
        i = text.index(start) + len(start)
        j = text.index(end, i)
        cells = build()
        text = text[:i] + "\n" + table(cells) + "\n" + text[j:]
        print(f"{name}: {len(cells)} maps")
    readme.write_bytes(text.encode("utf-8"))


if __name__ == "__main__":
    main()
