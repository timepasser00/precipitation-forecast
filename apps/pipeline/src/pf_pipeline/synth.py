"""Synthetic precipitation fields: sparse, spatially correlated, heavy-tailed, monsoon-aware.

This is test and demo data. It is *not* a weather model. It exists so the whole pipeline
(including GRIB decoding) can be exercised without network access, and so two "sources" can
disagree in believable ways. The large-scale pattern is shared by all sources, and each source
adds its own timing offset, bias, texture and lead-time-dependent run-to-run drift.
"""

from __future__ import annotations

import math
import zlib
from collections.abc import Iterator
from datetime import UTC, datetime

import numpy as np

from precip_core.grid import GridSpec, global_grid
from precip_core.tiling import BilinearSampler

EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
LATENT = global_grid(2.0)  # 91 x 180 latent grid
DRIFT_DEG_PER_H = 0.3  # eastward drift of the weather pattern
# Calibration: tuned so global mean is about 2.5-3 mm/day and the Indian monsoon region about
# 6-10 mm/day, with rare daily maxima of a few hundred mm (see tests/test_synth.py).
WET_Z, WET_OFFSET, RATE_K, RATE_P = 0.8, -0.75, 0.9, 1.75
PERIOD_H = 96.0  # temporal decorrelation of the pattern
_STYLE = {
    "ecmwf-ifs": {"phase_h": 0.0, "amp": 1.00, "texture": 0.40, "salt": 11},
    "ecmwf-aifs": {"phase_h": 3.0, "amp": 0.92, "texture": 0.22, "salt": 23},
}


def _climatology(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Rough 'how rainy is this place' weight in [0, ~2.5]: monsoon, ITCZ, storm tracks, deserts."""

    def blob(lat0, lon0, slat, slon, a):
        dlon = (lon - lon0 + 180.0) % 360.0 - 180.0
        return a * np.exp(-0.5 * (((lat - lat0) / slat) ** 2 + (dlon / slon) ** 2))

    w = 0.55 * np.exp(-0.5 * ((lat - 8.0) / 9.0) ** 2)
    w = w + blob(15, 88, 8, 12, 0.55) + blob(14, 73, 8, 5, 0.6) + blob(23, 92, 5, 6, 0.45)
    w = w + blob(-5, 115, 10, 25, 0.45) + blob(45, -30, 8, 40, 0.45) + blob(-50, 100, 8, 120, 0.4)
    w = w - blob(25, 15, 10, 25, 0.8) - blob(24, 45, 8, 12, 0.6)
    return np.clip(w, 0.0, None).astype(np.float32)


def _spectral_noise(rng: np.random.Generator, shape: tuple[int, int], corr_cells: float):
    f = np.fft.rfft2(rng.standard_normal(shape))
    ky = np.fft.fftfreq(shape[0])[:, None]
    kx = np.fft.rfftfreq(shape[1])[None, :]
    return f * np.exp(-0.5 * (kx**2 + ky**2) * (2 * np.pi * corr_cells) ** 2)


class SyntheticModel:
    def __init__(self, source_id: str, *, seed: int = 7):
        style = _STYLE.get(source_id)
        if style is None:
            style = {
                "phase_h": float(zlib.crc32(source_id.encode()) % 6),
                "amp": 0.95,
                "texture": 0.3,
                "salt": zlib.crc32(source_id.encode()) % 997,
            }
        self.source_id, self.style, self.seed = source_id, style, seed
        shared = np.random.default_rng(seed)
        self._a = _spectral_noise(shared, LATENT.shape, 3.0)
        self._b = _spectral_noise(shared, LATENT.shape, 3.0)
        self._norm = float(np.fft.irfft2(self._a, s=LATENT.shape).std()) or 1.0
        self._clim = _climatology(LATENT.lats[:, None], LATENT.lons[None, :])
        self._kx = np.fft.rfftfreq(LATENT.nx)[None, :]

    def _pattern(self, t_abs_h: float, fourier_extra=None, extra_w: float = 0.0) -> np.ndarray:
        w = 2 * np.pi * t_abs_h / PERIOD_H
        f = math.cos(w) * self._a + math.sin(w) * self._b
        if fourier_extra is not None:
            f = f + extra_w * fourier_extra
        shift_cells = DRIFT_DEG_PER_H * t_abs_h / LATENT.dlon
        f = f * np.exp(-2j * np.pi * self._kx * shift_cells)
        return np.fft.irfft2(f, s=LATENT.shape) / self._norm

    def accumulations(
        self, run_time: datetime, grid: GridSpec, steps: list[int]
    ) -> Iterator[tuple[int, np.ndarray]]:
        """Yield (step, accumulated precipitation in metres from forecast start)."""
        t_run = (run_time - EPOCH).total_seconds() / 3600.0 + self.style["phase_h"]
        run_rng = np.random.default_rng([self.seed, self.style["salt"], int(t_run)])
        drift = _spectral_noise(run_rng, LATENT.shape, 3.0)  # run-specific disagreement
        sampler = BilinearSampler(LATENT, grid.lons, grid.lats)
        acc = np.zeros(grid.shape, dtype=np.float32)
        prev = 0
        for step in sorted(steps):
            h = prev
            while h < step:
                nxt = min(step, h + 6)
                lead_mid = (h + nxt) / 2.0
                eps = min(0.6, 0.25 * math.sqrt(max(lead_mid, 1.0) / 72.0))
                z = self._pattern(t_run + lead_mid, drift, eps)
                wet = WET_Z * z + self._clim + WET_OFFSET
                rate = RATE_K * np.clip(wet, 0.0, None) ** RATE_P * self.style["amp"]  # mm per hour
                rate_g = sampler.apply(rate.astype(np.float32))
                tex_rng = np.random.default_rng([self.seed, self.style["salt"], step, int(h)])
                tex = np.exp(
                    self.style["texture"] * tex_rng.standard_normal(grid.shape, dtype=np.float32)
                    - self.style["texture"] ** 2 / 2
                )
                acc += (rate_g * tex * (nxt - h) / 1000.0).astype(np.float32)
                h = nxt
            prev = step
            yield step, acc.copy()
