"""Minimal dependency-free PNG writer (8/16-bit gray, 8-bit RGB) for labels/depth."""

import struct
import zlib

import numpy as np


def _chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def write_png(path, arr):
    """``arr``: HxW (uint8/uint16 gray) or HxWx3 (uint8 RGB), top row first."""
    arr = np.ascontiguousarray(arr)
    if arr.ndim == 2:
        color_type = 0
        ch = 1
    elif arr.ndim == 3 and arr.shape[2] == 3:
        color_type = 2
        ch = 3
    else:
        raise ValueError("unsupported shape %s" % (arr.shape,))
    if arr.dtype == np.uint16:
        depth = 16
        raw = arr.astype(">u2")
    elif arr.dtype == np.uint8:
        depth = 8
        raw = arr
    else:
        raise ValueError("dtype must be uint8 or uint16")
    h, w = arr.shape[:2]
    rows = raw.reshape(h, w * ch * (depth // 8)) if depth == 8 else raw.reshape(h, -1).view(np.uint8)
    data = b"".join(b"\x00" + rows[i].tobytes() for i in range(h))
    ihdr = struct.pack(">IIBBBBB", w, h, depth, color_type, 0, 0, 0)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(_chunk(b"IHDR", ihdr))
        f.write(_chunk(b"IDAT", zlib.compress(data, 6)))
        f.write(_chunk(b"IEND", b""))


def read_png(path):
    """Read PNGs written by :func:`write_png` (8/16-bit gray or RGB, filter 0)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: %s" % path)
    pos, idat, hdr = 8, b"", None
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + n]
        if tag == b"IHDR":
            hdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + n
    w, h, depth, ctype = hdr[:4]
    ch = 3 if ctype == 2 else 1
    raw = zlib.decompress(idat)
    stride = w * ch * depth // 8 + 1
    rows = b"".join(raw[i * stride + 1:(i + 1) * stride] for i in range(h))
    if any(raw[i * stride] != 0 for i in range(h)):
        raise ValueError("only filter type 0 supported")
    arr = np.frombuffer(rows, dtype=">u2" if depth == 16 else np.uint8)
    arr = arr.astype(np.uint16 if depth == 16 else np.uint8)
    return arr.reshape(h, w, ch) if ch == 3 else arr.reshape(h, w)
