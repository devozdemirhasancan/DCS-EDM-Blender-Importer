---
title: Development
layout: default
nav_order: 7
permalink: /development/
---

# Development
{: .no_toc }

Contributing patches, running the test suite, releasing new versions.
{: .fs-5 .fw-300 }

1. TOC
{:toc}

---

## Setting up

```bash
git clone https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer.git
cd DCS-EDM-Blender-Importer
```

You'll need:

- **Python 3.10+** for the parser tests (no third-party libs required).
- **PowerShell 5.1+** to run `build.ps1`.
- **Blender 4.0+** for end-to-end testing.

A useful symlink lets your edits take effect on every Blender "Reload
Scripts" without re-zipping:

```powershell
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\dcs_edm_importer" `
  -Target "$pwd\dcs_edm_importer"
```

## Running the tests

```bash
python tests/test_parser.py            # smoke test: every .edm parses
python tests/test_data_integrity.py    # spot-checks dataclass fields
```

Neither test requires Blender — they exercise only `dcs_edm_importer.edm`.

CI runs the smoke test on every push and PR against Python 3.10 and
3.11 — see
[.github/workflows/ci.yml](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/.github/workflows/ci.yml).

## Adding a new node type

1. Add a dataclass to `dcs_edm_importer/edm/types.py` (alphabetised).
2. Add a private reader method to `EDMFileParser` (in `edm/parser.py`).
3. Register the EDM type-name → method binding in
   `EDMFileParser._build_dispatch`.
4. If the new type is a render item, add its category and known
   sub-types to `_RECOVERY_TYPES_BY_CATEGORY` so the resync heuristic
   knows to look for it.
5. Run `python tests/test_parser.py` against your sample file — it
   should now parse without warnings.
6. Add a Blender-side handler if needed (`MeshBuilder` for geometry,
   `extras.py` for empties / lights).

## Adding a new MATERIAL_NAME preset

Edit `dcs_edm_importer/blender/materials.py`:

1. Add the EDM material name to one of `_SELF_ILLUM_MATERIALS`,
   `_GLASS_MATERIALS`, `_METALLIC_MATERIALS`, or create a new set if
   it's a fundamentally different shader category.
2. Add any specific socket overrides inside
   `MaterialBuilder._configure_shader_for_material`.
3. Document the new preset in `docs/format.md` under "Materials".

## Releasing a new version

1. Update the version tuple in two places:
   - `dcs_edm_importer/__init__.py` (`bl_info["version"]`)
   - `dcs_edm_importer/blender_manifest.toml` (`version = "..."`)
2. Update the [README](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/README.md)
   "Highlights" table if there are user-visible changes.
3. Commit the bumps with a `chore: release vX.Y.Z` message.
4. Tag and push:

   ```bash
   git tag v0.3.0
   git push origin v0.3.0
   ```

5. The `Release` workflow in
   [.github/workflows/release.yml](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/.github/workflows/release.yml)
   takes over: it builds the zip, runs the parser smoke-test, creates
   a GitHub Release, and attaches `dcs_edm_importer-X.Y.Z.zip` as an
   asset.

You can also trigger the workflow manually from the Actions tab via
**Run workflow → tag = v0.3.0** if the tag already exists.

## Updating the docs

The site is plain Jekyll powered by `just-the-docs`. Local preview:

```bash
cd docs
bundle install     # first time only
bundle exec jekyll serve
# → http://127.0.0.1:4000/DCS-EDM-Blender-Importer/
```

Pushing to `main` automatically rebuilds and deploys via
[.github/workflows/pages.yml](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/.github/workflows/pages.yml).

## Updating the wiki

The repository's wiki is mirrored from `wiki/*.md` in the main repo.
Edit those files, push to `main`, and the
[.github/workflows/wiki-sync.yml](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/blob/main/.github/workflows/wiki-sync.yml)
workflow will sync them to the actual GitHub wiki repository.

This way every wiki edit goes through PR review just like code.

## Reload-aware development loop

`__init__.py` walks the package's sub-modules and reloads them when
Blender re-imports the top-level package — so `F3 → Reload Scripts`
in Blender picks up edits without a full restart. If you add a *new*
sub-module while iterating, you do need a full restart so Python
discovers it.

## Code style

- Type hints on public APIs.
- Docstrings on every public function/class.
- Keep parser code free of `bpy` imports (so the test suite stays
  Blender-free).
- Prefer dataclasses over `SimpleNamespace` for new types.
- 4-space indents, no tabs.

There's no automated formatter required, but if you want to run one,
`black` with default settings produces a result close to the existing
style.
