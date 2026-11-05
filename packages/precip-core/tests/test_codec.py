import numpy as np
import pytest

from precip_core.codec import (
    NODATA,
    Encoding,
    decode_atlas,
    decode_cube,
    dequantize,
    encode_atlas,
    encode_cube,
    quantize,
)


def test_zero_nodata_and_range():
    v = np.array([0.0, 0.019, 0.02, 1000.0, 5000.0, np.nan], dtype=np.float32)
    q = quantize(v)
    assert q.tolist()[:2] == [0, 0]
    assert q[2] == 1 and q[3] == 254 and q[4] == 254  # clipped at vmax
    assert q[5] == NODATA


def test_roundtrip_error_bounds():
    enc = Encoding()
    rng = np.random.default_rng(0)
    v = np.exp(rng.uniform(np.log(enc.v0), np.log(enc.vmax), 100_000)).astype(np.float32)
    back = dequantize(quantize(v, enc), enc)
    rel = np.abs(back - v) / v
    assert rel.max() < 0.0225  # about 2.2% relative step


def test_below_threshold_absolute_error():
    v = np.linspace(0, 0.0199, 100, dtype=np.float32)
    assert np.abs(dequantize(quantize(v)) - v).max() < 0.02


def test_dequantize_nodata_is_nan():
    assert np.isnan(dequantize(np.array([NODATA], dtype=np.uint8))[0])


def test_atlas_roundtrip_and_padding():
    rng = np.random.default_rng(3)
    frames = [rng.integers(0, 255, (16, 16), dtype=np.uint8) for _ in range(6)]
    png = encode_atlas(frames, cols=4)
    out = decode_atlas(png, 8, 4, tile=16)
    assert np.array_equal(out[:6], np.stack(frames))
    assert (out[6:] == NODATA).all()


def test_cube_roundtrip():
    q = np.random.default_rng(1).integers(0, 255, (5, 7, 3), dtype=np.uint8)
    header, back = decode_cube(encode_cube(q, {"grid": {"ny": 5}}))
    assert np.array_equal(back, q) and header["shape"] == [5, 7, 3]
    assert header["grid"] == {"ny": 5}


def test_cube_rejects_bad_input():
    with pytest.raises(ValueError):
        decode_cube(b"nope....")
    with pytest.raises(ValueError):
        encode_cube(np.zeros((2, 2), np.uint8), {})
