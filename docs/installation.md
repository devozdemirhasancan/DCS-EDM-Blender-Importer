---
title: Installation
layout: default
nav_order: 2
permalink: /installation/
---

# Installation
{: .no_toc }

There are three ways to get the add-on into Blender, ordered from
easiest to most-flexible.
{: .fs-5 .fw-300 }

1. TOC
{:toc}

---

## Option 1 — Pre-built zip (recommended)

The fastest path. Each tagged release attaches a ready-to-install zip.

1. Open the [latest release](https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer/releases/latest).
2. Download `dcs_edm_importer-<version>.zip`.
3. In Blender: **Edit → Preferences → Add-ons → Install…**
4. Pick the downloaded zip.
5. Tick the **DCS World EDM Importer** check-box to enable it.

## Option 2 — Build from source

Useful when you want unreleased fixes or you intend to modify the code.

```powershell
git clone https://github.com/devozdemirhasancan/DCS-EDM-Blender-Importer.git
cd DCS-EDM-Blender-Importer
.\build.ps1
```

`build.ps1` reads the version from `dcs_edm_importer/__init__.py` and
writes `build/dcs_edm_importer-<version>.zip`. Install the result the
same way as in **Option 1**.

The script automatically strips `__pycache__` folders so the zip stays
small (~36 KB) and Blender re-compiles modules cleanly on first load.

## Option 3 — Symlink / copy the source folder

The most flexible option for active development — your edits take
effect immediately on every "Reload Scripts" without re-zipping.

Find Blender's user-scripts directory:

| OS      | Default path                                                                                  |
| ------- | --------------------------------------------------------------------------------------------- |
| Windows | `%APPDATA%\Blender Foundation\Blender\<version>\scripts\addons\`                              |
| macOS   | `~/Library/Application Support/Blender/<version>/scripts/addons/`                             |
| Linux   | `~/.config/blender/<version>/scripts/addons/`                                                 |

Then either copy or symlink:

```powershell
# Windows (PowerShell as admin, for the symlink)
New-Item -ItemType SymbolicLink `
  -Path "$env:APPDATA\Blender Foundation\Blender\4.2\scripts\addons\dcs_edm_importer" `
  -Target "C:\path\to\repo\dcs_edm_importer"
```

```bash
# Linux / macOS
ln -s "$(pwd)/dcs_edm_importer" \
  ~/.config/blender/4.2/scripts/addons/dcs_edm_importer
```

Restart Blender once and enable the add-on.

{: .note }
The package is **reload-aware** — `__init__.py` walks its sub-modules
and re-imports them when the user hits "Reload Scripts" (`F3 → Reload
Scripts`), so iteration is fast.

## Blender 4.2+ Extensions

The package also ships a `blender_manifest.toml`, so it's compatible
with Blender 4.2's new Extension API. To use that:

1. **Edit → Preferences → Get Extensions → Install from Disk…**
2. Pick the same zip as in **Option 1**.

The legacy `bl_info` and the new manifest coexist in the same file, so
both flows work from one zip.

## Verifying the install

Open Blender, go to **File → Import**, and you should see
**DCS World EDM (.edm)** at the bottom of the menu. Picking that
opens the import dialog described in [Usage]({{ site.baseurl }}/usage/).

If the menu entry isn't there:

- Check **Edit → Preferences → Add-ons** and look for
  *DCS World EDM Importer* — make sure the check-box is on.
- Open Blender's system console (Window → Toggle System Console on
  Windows) and look for `[EDM]` lines or any tracebacks at startup.
- See [Troubleshooting]({{ site.baseurl }}/troubleshooting/).
