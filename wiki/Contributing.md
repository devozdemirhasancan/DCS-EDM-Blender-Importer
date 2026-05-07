# Contributing

Bug reports, fixes and new features are very welcome. The full
developer guide lives at
[devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/development/](https://devozdemirhasancan.github.io/DCS-EDM-Blender-Importer/development/);
this wiki page is a quick orientation.

## What's easy to contribute

- **New `MATERIAL_NAME` presets** — the mapping in
  `dcs_edm_importer/blender/materials.py` is small. If a particular
  material category looks wrong, drop a comment on its source data.
- **Sample `.edm` regression files** — anything weird, broken, or
  exotic helps us extend the resync heuristic and edge-case coverage.
  Tiny files are fine.
- **Documentation** — if anything in this wiki or the Pages site is
  unclear, just edit the markdown and open a PR.
- **Module-specific notes** — drop any DCS module's argument list,
  texture conventions, or quirks into the wiki under a new page.

## What needs more thought

- **EDM export** — would require correctly synthesising the
  `indexA` / `indexB` cross-checks and reconstructing the v10 string
  lookup. Big project, ideally a separate `dcs_edm_importer.writer`
  sibling package.
- **Animation transform chain completeness** — `Quat2` and the matrix
  translation component aren't applied yet. Tested by importing
  modules with non-default `Quat2` values (rare).
- **NumberNode body layout** — currently we skip past it via the
  resync heuristic. Reverse-engineering the actual layout would let
  us extract whatever data is in there (probably render-control hints
  related to `model::RNControlNode`).

## Workflow

1. Fork, branch, edit.
2. Run `python tests/test_parser.py` against any `.edm` files you have
   handy.
3. If it touches `bpy`, sanity-test in Blender too.
4. Commit with a conventional-commit style message
   (e.g. `feat: add chrome material preset`).
5. Open a PR. CI will run the smoke tests automatically.

## Code style

- 4-space indents, no tabs.
- Type hints on public APIs.
- Docstrings on public functions/classes.
- Don't import `bpy` from anything in `dcs_edm_importer/edm/` — that
  package needs to remain Blender-free for testing.

## License

The project is MIT. By contributing you agree that your changes can
be relicensed under the same terms.
