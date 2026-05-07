"""
Stand-alone parser smoke test (no Blender required).

Loads the dcs_edm_importer.edm sub-package directly (without triggering
the top-level __init__.py that imports `bpy`) and parses every .edm file
in the workspace, printing a one-line summary per file.

Run with::

    python tests/test_parser.py
"""

from __future__ import annotations

import importlib.util
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EDM_PKG = os.path.join(ROOT, "dcs_edm_importer", "edm")


def _load(module_name: str, file_name: str):
    """Load an `edm.<module>` file as `dcs_edm_importer.edm.<module>`."""
    full = f"dcs_edm_importer.edm.{module_name}"
    path = os.path.join(EDM_PKG, file_name)
    spec = importlib.util.spec_from_file_location(full, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod


def setup_pkg():
    """Make the package skeleton importable without running its __init__."""
    pkg_root = "dcs_edm_importer"
    edm_pkg = "dcs_edm_importer.edm"
    sys.modules[pkg_root] = type(sys)(pkg_root)
    sys.modules[pkg_root].__path__ = [os.path.join(ROOT, "dcs_edm_importer")]
    sys.modules[edm_pkg] = type(sys)(edm_pkg)
    sys.modules[edm_pkg].__path__ = [EDM_PKG]
    _load("reader", "reader.py")
    types_mod = _load("types", "types.py")
    sys.modules[edm_pkg].types = types_mod
    parser_mod = _load("parser", "parser.py")
    return parser_mod


def main() -> int:
    parser = setup_pkg()
    edm_files = [f for f in os.listdir(ROOT) if f.lower().endswith(".edm")]
    if not edm_files:
        print("No .edm files in workspace root.")
        return 0

    overall_ok = True
    for filename in edm_files:
        path = os.path.join(ROOT, filename)
        size_mb = os.path.getsize(path) / 1024 / 1024
        t0 = time.time()
        try:
            data = parser.parse_edm(path)
        except Exception as exc:
            print(f"[FAIL] {filename:50s} ({size_mb:6.1f} MB)  {type(exc).__name__}: {exc}")
            overall_ok = False
            continue
        dt = time.time() - t0
        print(
            f"[ OK ] {filename:50s} ({size_mb:6.1f} MB) v{data.version}"
            f"  mats={len(data.materials):3d}"
            f"  scn_nodes={len(data.nodes):4d}"
            f"  render={len(data.render_nodes):4d}"
            f"  shells={len(data.shell_nodes):3d}"
            f"  lights={len(data.light_nodes):3d}"
            f"  conn={len(data.connectors):3d}"
            f"  in {dt:5.2f}s"
        )

        # Quick sanity checks
        if data.materials:
            sample_mat = data.materials[0]
            assert sample_mat.material_name or sample_mat.name, \
                "Material is missing both name and material_name"

    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main())
