# Compatibility Matrix

Known-good module / Blender combinations. If your aircraft isn't
listed and works (or doesn't), please open a PR adding it!

## Blender versions

| Blender | Add-on version | Status |
| ------- | -------------- | ------ |
| 4.4 LTS | 0.2.0          | ✅ Tested |
| 4.3     | 0.2.0          | ✅ Tested |
| 4.2 LTS | 0.2.0          | ✅ Tested (uses Extension manifest) |
| 4.1     | 0.2.0          | ✅ Tested (legacy add-on) |
| 4.0     | 0.2.0          | ✅ Tested (legacy add-on) |
| 3.6 LTS | 0.1.0          | ⚠️ Partial — Principled BSDF socket names changed in 4.0; some materials may import flat |

## Tested DCS modules

| Module                       | File(s)                          | Result                                                                  |
| ---------------------------- | -------------------------------- | ----------------------------------------------------------------------- |
| F-16C Viper (BlinkD/standard)| `f-16c_bl50.edm`                 | ✅ Full import — 296 render nodes, 16 lights, 20 connectors, 297 mats   |
| F-16C Viper (ED-modified)    | `f-16c_bl50_ED.edm`              | ✅ Full import via NumberNode resync — 319 render nodes recovered       |
| F-16C cockpit                | `Cockpit_F-16C.edm`              | ✅ Full import (per legacy 0.1 testing)                                 |

## Reporting compatibility

Please open an issue or a PR with a row added to this table when you
test a module. Useful info to include:

- Module name and exact file path.
- File size.
- Blender version.
- Add-on version (`bl_info["version"]` or zip filename).
- Outcome (Full import / partial / failed).
- If partial, the line from the system console showing how many items were recovered.

## Files we know break

| File                       | Symptom                                                               |
| -------------------------- | --------------------------------------------------------------------- |
| Very old EDM v6 / v7 files | Unsupported version. Only v8 and v10 are recognised.                  |
| In-development EDM v11+    | Unsupported version. Open an issue with a sample file.                 |

## DCS install variants

The importer's default texture search includes:

- `C:\Program Files\Eagle Dynamics\DCS World`
- `C:\Program Files\Eagle Dynamics\DCS World OpenBeta`
- `C:\Program Files\Eagle Dynamics\DCS World Server`
- `C:\Program Files (x86)\Steam\steamapps\common\DCSWorld`
- D:/E:-drive variants of the above

Custom installs (network drives, OneDrive folders, …) need the
**Extra Texture Folder** option on the import dialog.
