"""
Texture file resolution.

DCS stores textures in three increasingly annoying places:

  1. Plain files next to or near the ``.edm`` (most cockpits do this).
  2. Plain files inside the user's DCS install
     (``Bazar/World/textures/...``, ``Mods/aircraft/<X>/Textures``,
     livery overrides, ...).
  3. Inside ``.zip`` bundles that DCS unpacks at runtime (most external
     aircraft skins use this — look at any ``Bazar/World/textures``
     folder and you'll see hundreds of small ``F-16C.zip`` /
     ``M-2000C.zip`` etc. files).

This resolver walks all three. Files referenced by base-name are
matched against:

  * search-paths the user provided explicitly,
  * search-paths derived from the ``.edm``'s own location,
  * a long list of known DCS install paths,
  * recursively, every directory under the above (capped at a sane
    depth so we don't spend minutes spidering 100 GB DCS installs),
  * every ``.zip`` archive found in those directories — texture data
    is extracted to a per-import temp directory so Blender can load
    it like any normal file.

Cache: once a texture has been located it is cached on a per-importer
basis so we don't pay for the disk walk repeatedly.
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import zipfile
from typing import Dict, Iterable, List, Optional, Tuple


# Image extensions DCS uses (in order of preference).
SUPPORTED_TEXTURE_EXTENSIONS = (".dds", ".png", ".tga", ".bmp", ".jpg", ".jpeg")

# Common DCS install paths on Windows. We try each combined with several
# typical relative texture locations.
_DEFAULT_DCS_ROOTS = (
    r"C:\Program Files\Eagle Dynamics\DCS World",
    r"C:\Program Files\Eagle Dynamics\DCS World OpenBeta",
    r"C:\Program Files\Eagle Dynamics\DCS World Server",
    r"C:\Program Files (x86)\Eagle Dynamics\DCS World",
    r"C:\Program Files (x86)\Steam\steamapps\common\DCSWorld",
    r"D:\Program Files\Eagle Dynamics\DCS World",
    r"D:\Eagle Dynamics\DCS World",
    r"D:\DCS World",
    r"D:\Steam\steamapps\common\DCSWorld",
    r"E:\Eagle Dynamics\DCS World",
    r"E:\DCS World",
    r"E:\Steam\steamapps\common\DCSWorld",
)

# Sub-directories under any DCS root where textures might live.
# The empty string and "." mean "the root itself".
_DEFAULT_TEXTURE_SUBDIRS = (
    "",
    ".",
    "..",
    "textures",
    "Textures",
    "tex",
    os.path.join("..", "textures"),
    os.path.join("..", "..", "textures"),
    os.path.join("Bazar", "World", "textures"),
    os.path.join("Bazar", "World", "Textures"),
    os.path.join("Bazar", "Effects", "Textures"),
    os.path.join("Mods", "aircraft"),
    os.path.join("Mods", "tech"),
    os.path.join("Liveries"),
    os.path.join("CoreMods"),
)

# How deep we walk into a search root looking for textures or zips.
# 4 levels is enough for "DCS/Bazar/World/textures/F-16C/Skin01" but
# stops us from indexing every leaf in CoreMods/aircraft/.
_MAX_RECURSE_DEPTH = 4


# A single shared temp directory across all imports in one Blender
# session, cleaned up when Python exits.
_TEMP_DIR: Optional[str] = None


def _get_temp_dir() -> str:
    global _TEMP_DIR
    if _TEMP_DIR is None or not os.path.isdir(_TEMP_DIR):
        _TEMP_DIR = tempfile.mkdtemp(prefix="dcs_edm_textures_")
        atexit.register(_cleanup_temp_dir)
    return _TEMP_DIR


def _cleanup_temp_dir() -> None:
    if _TEMP_DIR and os.path.isdir(_TEMP_DIR):
        shutil.rmtree(_TEMP_DIR, ignore_errors=True)


# ---------------------------------------------------------------------------
#  Resolver
# ---------------------------------------------------------------------------


class TextureResolver:
    """Stateful texture lookup with caching, zip support, and recursion."""

    def __init__(self, edm_path: str, extra_search_paths: Iterable[str] = ()):
        self._edm_dir = os.path.dirname(os.path.abspath(edm_path))
        self._cache: Dict[str, Optional[str]] = {}
        self._search_paths: List[str] = self._build_search_paths(extra_search_paths)

        # Pre-built directory listing (case-insensitive) plus discovered
        # zip archives. Computed lazily on first miss so a quick import
        # of a tiny model in an unusual location pays nothing.
        self._dir_index: Optional[Dict[str, List[Tuple[str, str]]]] = None
        self._zip_archives: Optional[List[str]] = None

    # --------------------------------------------------------------- public
    def resolve(self, name: str) -> Optional[str]:
        """Return an absolute path for texture ``name``, or ``None``."""
        if not name:
            return None
        if name in self._cache:
            return self._cache[name]

        # 1) Direct hit on a known search-path.
        hit = self._lookup_direct(name)
        if hit:
            self._cache[name] = hit
            return hit

        # 2) Case-insensitive scan of the indexed search-paths
        #    (recursively built on first miss).
        if self._dir_index is None:
            self._build_indexes()
        hit = self._lookup_indexed(name)
        if hit:
            self._cache[name] = hit
            return hit

        # 3) Pull from any zip archive on those search paths.
        hit = self._lookup_in_zips(name)
        if hit:
            self._cache[name] = hit
            return hit

        self._cache[name] = None
        print(f"[EDM] Texture not found: {name!r}")
        return None

    @property
    def search_paths(self) -> List[str]:
        return self._search_paths

    # -------------------------------------------------------------- private
    def _build_search_paths(self, extra: Iterable[str]) -> List[str]:
        roots: List[str] = []

        def add(path: str) -> None:
            try:
                norm = os.path.normpath(path)
            except (TypeError, ValueError):
                return
            if not norm or norm in roots:
                return
            if not os.path.isdir(norm):
                return
            roots.append(norm)

        # The EDM's own directory and obvious siblings come first.
        add(self._edm_dir)
        # Walk a few parents up so we still find textures shipped in
        # "Mods/aircraft/<X>/Shapes/file.edm" with textures at
        # "Mods/aircraft/<X>/Textures".
        parent = self._edm_dir
        for _ in range(5):
            new_parent = os.path.dirname(parent)
            if new_parent == parent:
                break
            parent = new_parent
            for sub in _DEFAULT_TEXTURE_SUBDIRS:
                add(os.path.join(parent, sub))

        # Anything the caller explicitly provided.
        for path in extra:
            if path:
                add(path)

        # Standard DCS install locations.
        for dcs_root in _DEFAULT_DCS_ROOTS:
            for sub in _DEFAULT_TEXTURE_SUBDIRS:
                add(os.path.join(dcs_root, sub))

        return roots

    def _lookup_direct(self, name: str) -> Optional[str]:
        for directory in self._search_paths:
            for ext in SUPPORTED_TEXTURE_EXTENSIONS:
                candidate = os.path.join(directory, name + ext)
                if os.path.isfile(candidate):
                    return os.path.abspath(candidate)
        return None

    def _build_indexes(self) -> None:
        """Populate dir-index (lowercase stem -> [(path, ext)]) and zip list."""
        index: Dict[str, List[Tuple[str, str]]] = {}
        zips: List[str] = []
        seen: set = set()

        for root in self._search_paths:
            self._walk_index(root, 0, index, zips, seen)

        self._dir_index = index
        self._zip_archives = zips

    def _walk_index(
        self,
        path: str,
        depth: int,
        index: Dict[str, List[Tuple[str, str]]],
        zips: List[str],
        seen: set,
    ) -> None:
        if path in seen or depth > _MAX_RECURSE_DEPTH:
            return
        seen.add(path)
        try:
            entries = os.scandir(path)
        except (OSError, PermissionError):
            return
        try:
            for entry in entries:
                try:
                    is_dir = entry.is_dir(follow_symlinks=False)
                except OSError:
                    continue
                full = entry.path
                if is_dir:
                    self._walk_index(full, depth + 1, index, zips, seen)
                    continue
                stem, ext = os.path.splitext(entry.name)
                ext_lower = ext.lower()
                if ext_lower == ".zip":
                    zips.append(full)
                elif ext_lower in SUPPORTED_TEXTURE_EXTENSIONS:
                    index.setdefault(stem.lower(), []).append((full, ext_lower))
        finally:
            try:
                entries.close()
            except Exception:
                pass

    def _lookup_indexed(self, name: str) -> Optional[str]:
        if not self._dir_index:
            return None
        candidates = self._dir_index.get(name.lower())
        if not candidates:
            return None
        # Pick the first candidate, preferring DDS if present.
        candidates.sort(
            key=lambda pair: SUPPORTED_TEXTURE_EXTENSIONS.index(pair[1])
            if pair[1] in SUPPORTED_TEXTURE_EXTENSIONS
            else 99
        )
        return candidates[0][0]

    def _lookup_in_zips(self, name: str) -> Optional[str]:
        """Search every indexed .zip for ``name.<ext>`` and extract it."""
        if not self._zip_archives:
            return None
        lowered = name.lower()
        wanted_exts = SUPPORTED_TEXTURE_EXTENSIONS

        for zip_path in self._zip_archives:
            try:
                with zipfile.ZipFile(zip_path, "r") as zf:
                    for member in zf.namelist():
                        # Ignore directory entries and Windows path
                        # separators inside the archive.
                        member_norm = member.replace("\\", "/")
                        if member_norm.endswith("/"):
                            continue
                        member_name = member_norm.rsplit("/", 1)[-1]
                        stem, ext = os.path.splitext(member_name)
                        if ext.lower() not in wanted_exts:
                            continue
                        if stem.lower() != lowered:
                            continue
                        # Match — extract into our temp dir.
                        target = os.path.join(
                            _get_temp_dir(), member_name
                        )
                        if not os.path.isfile(target):
                            try:
                                with zf.open(member) as src, open(target, "wb") as dst:
                                    shutil.copyfileobj(src, dst)
                            except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
                                print(
                                    f"[EDM] Warning: could not extract "
                                    f"{member!r} from {zip_path!r}: {exc}"
                                )
                                continue
                        print(
                            f"[EDM] Resolved {name!r} from "
                            f"{os.path.basename(zip_path)} -> {target}"
                        )
                        return target
            except (zipfile.BadZipFile, OSError):
                continue
        return None
