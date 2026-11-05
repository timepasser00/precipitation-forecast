"""Process-wide state: storage handle, manifest cache and an LRU of decoded point cubes."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict

import numpy as np

from precip_core.codec import decode_cube
from precip_core.grid import GridSpec
from precip_core.manifest import Manifest, load_manifest
from precip_core.registry import Registry, load_registry
from precip_core.storage import Storage, storage_from_url

from .settings import Settings


class Cube:
    __slots__ = ("grid", "header", "q")

    def __init__(self, header: dict, q: np.ndarray):
        self.header = header
        self.q = q
        self.grid = GridSpec.from_dict(header["grid"])


class AppState:
    def __init__(self, settings: Settings, storage: Storage | None = None):
        self.settings = settings
        self.storage = storage or storage_from_url(settings.storage_url)
        self._lock = threading.Lock()
        self._manifest: tuple[float, Manifest] | None = None
        self._cubes: OrderedDict[str, Cube] = OrderedDict()
        self._registry: Registry | None = None
        self._registry_tried = False

    def manifest(self) -> Manifest:
        """Cached for a short TTL so a burst of requests costs one storage read."""
        now = time.monotonic()
        with self._lock:
            if self._manifest and now - self._manifest[0] < self.settings.manifest_ttl_s:
                return self._manifest[1]
        m = load_manifest(self.storage)
        with self._lock:
            self._manifest = (now, m)
        return m

    def registry(self) -> Registry | None:
        """Source metadata (names, licences). Optional: the API still works without it."""
        if not self._registry_tried:
            self._registry_tried = True
            try:
                self._registry = load_registry(self.settings.config_path)
            except Exception:
                self._registry = None
        return self._registry

    def cube(self, source: str, run: str, tier: str, cube_path: str) -> Cube:
        key = f"{source}/{run}/{tier}"
        with self._lock:
            if key in self._cubes:
                self._cubes.move_to_end(key)
                return self._cubes[key]
        header, q = decode_cube(self.storage.get(cube_path))
        cube = Cube(header, q)
        with self._lock:
            self._cubes[key] = cube
            while len(self._cubes) > self.settings.cube_cache_size:
                self._cubes.popitem(last=False)
        return cube
