"""
Texture file resolution.

EDM files reference textures by base-name without extension. We have to
guess where the user's textures live; the heuristic walks a list of
candidate roots (the .edm's own directory, common DCS install paths, ...)
and tries each known image extension.

Cache: once a texture has been located it is cached on a per-importer
basis so we don't pay for the disk walk repeatedly.
"""

from __future__ import annotations

import os
from typing import Dict, Iterable, List, Optional


# Image extensions DCS uses (in order of preference).
SUPPORTED_TEXTURE_EXTENSIONS = (".dds", ".png", ".tga", ".bmp", ".jpg", ".jpeg")

# Common DCS install paths on Windows. We try each combined with several
# typical relative texture locations. None of these are mandatory — a
# missing path simply means we don't find the texture at that location.
_DEFAULT_DCS_ROOTS = (
    r"C:\Program Files\Eagle Dynamics\DCS World",
    r"C:\Program Files\Eagle Dynamics\DCS World OpenBeta",
    r"C:\Program Files\Eagle Dynamics\DCS World Server",
    r"C:\Program Files (x86)\Steam\steamapps\common\DCSWorld",
    r"D:\Program Files\Eagle Dynamics\DCS World",
    r"D:\Eagle Dynamics\DCS World",
    r"E:\Eagle Dynamics\DCS World",
)

_DEFAULT_TEXTURE_SUBDIRS = (
    "",                           # the EDM's own directory
    "..",
    "textures",
    os.path.join("..", "textures"),
    os.path.join("..", "..", "textures"),
    os.path.join("Bazar", "World", "textures"),
    os.path.join("Bazar", "World", "Textures"),
)


class TextureResolver:
    """Stateful texture lookup with caching and configurable search paths."""

    def __init__(self, edm_path: str, extra_search_paths: Iterable[str] = ()):
        self._edm_dir = os.path.dirname(os.path.abspath(edm_path))
        self._cache: Dict[str, Optional[str]] = {}
        self._search_paths: List[str] = self._build_search_paths(extra_search_paths)

    # --------------------------------------------------------------- public
    def resolve(self, name: str) -> Optional[str]:
        """Return an absolute path for texture ``name``, or ``None``."""
        if not name:
            return None
        if name in self._cache:
            return self._cache[name]

        # Try direct, case-sensitive match first (common case).
        for directory in self._search_paths:
            for ext in SUPPORTED_TEXTURE_EXTENSIONS:
                candidate = os.path.join(directory, name + ext)
                if os.path.isfile(candidate):
                    self._cache[name] = os.path.abspath(candidate)
                    return self._cache[name]

        # Fall back to a case-insensitive directory scan (slow path).
        lowered = name.lower()
        for directory in self._search_paths:
            try:
                entries = os.listdir(directory)
            except OSError:
                continue
            for entry in entries:
                stem, ext = os.path.splitext(entry)
                if stem.lower() == lowered and ext.lower() in SUPPORTED_TEXTURE_EXTENSIONS:
                    self._cache[name] = os.path.abspath(os.path.join(directory, entry))
                    return self._cache[name]

        self._cache[name] = None
        return None

    @property
    def search_paths(self) -> List[str]:
        return self._search_paths

    # -------------------------------------------------------------- private
    def _build_search_paths(self, extra: Iterable[str]) -> List[str]:
        roots: List[str] = []

        def add(path: str) -> None:
            norm = os.path.normpath(path)
            if norm and norm not in roots and os.path.isdir(norm):
                roots.append(norm)

        # The EDM's own directory and obvious siblings come first.
        add(self._edm_dir)
        for sub in _DEFAULT_TEXTURE_SUBDIRS:
            add(os.path.join(self._edm_dir, sub))

        # Anything the caller explicitly provided.
        for path in extra:
            add(path)

        # Standard DCS install locations.
        for dcs_root in _DEFAULT_DCS_ROOTS:
            for sub in _DEFAULT_TEXTURE_SUBDIRS:
                add(os.path.join(dcs_root, sub))

        return roots
