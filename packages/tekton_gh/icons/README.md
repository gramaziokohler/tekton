# Icon sources

The editable originals live here: `<bundle>.svg` (scalable) and
`<bundle>_96.png` (for judging the result). What Grasshopper actually shows is
the 24px `icon.png` **inside the respective bundle** under
`../components/<bundle>/`.

Two places, because the componentizer expects the 24px PNG next to `code.py`
and `metadata.json` — so the file in the bundle is not redundant, it is the
build artefact.

## Changing an icon

1. Edit the SVG here.
2. Rasterise to 24px and save as `../components/<bundle>/icon.png`
   (update the 96px version here at the same time).
3. Rebuild and install — see [../README.md](../README.md).

`build_metadata.py` does **not** overwrite an existing `icon.png`; it only
creates what is missing. The real icons are therefore safe.

## Style

Taken from `lorin-gh-tools/gh-icons`: stroke `#26272A` at 1.8pt,
`stroke-linecap`/`linejoin` round, transparent background, one accent per
group. The colour assignment and the motifs are in
[../ICONS.md](../ICONS.md).

| Group | Accent |
|---|---|
| 0 \| Setup | `#a5a9ae` grey |
| 1 \| Author | `#50a9d3` light blue |
| 2 \| Translate | `#50d3c6` turquoise |
| 3 \| Run | `#d3a850` orange |
| 4 \| Results | `#8f50d3` violet |
| 5 \| IO | `#7a8288` dark grey |

Exception: `tekton_visualize` carries the result gradient green→yellow→red,
because that is exactly its function.
