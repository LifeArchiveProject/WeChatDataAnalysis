from __future__ import annotations

"""ISAAC-64 PRNG (best-effort fallback).

In this repo, Moments (SNS) *video* decryption uses a keystream generator that
matches WeFlow's WxIsaac64 (WASM) behavior and XORs only the first 128KB of the
MP4.

This module provides a pure-Python ISAAC-64 implementation so the backend can
still attempt to generate a keystream when the WASM helper is unavailable.

Notes:
- Moments *image* decryption is handled via `wcdb_api.dll` (`wcdb_decrypt_sns_image`)
  because "ISAAC-64 full-file XOR" is not reliably reproducible for images across
  different versions/samples.
- This ISAAC-64 implementation may not perfectly match WxIsaac64; treat it as
  best-effort.
"""

from typing import Any, Literal

_MASK_64 = 0xFFFFFFFFFFFFFFFF


def _u64(v: int) -> int:
    return int(v) & _MASK_64


class Isaac64:
    def __init__(self, seed: Any):
        seed_text = str(seed).strip()
        if not seed_text:
            seed_val = 0
        else:
            try:
                # WeFlow seeds with BigInt(seed), where seed is usually a decimal string.
                seed_val = int(seed_text, 0)
            except Exception:
                seed_val = 0

        self.mm = [_u64(0) for _ in range(256)]
        self.aa = _u64(0)
        self.bb = _u64(0)
        self.cc = _u64(0)
        self.randrsl = [_u64(0) for _ in range(256)]
        self.randrsl[0] = _u64(seed_val)
        self.randcnt = 0
        self._init(True)

    def _init(self, flag: bool) -> None:
        a = b = c = d = e = f = g = h = _u64(0x9E3779B97F4A7C15)

        def mix() -> tuple[int, int, int, int, int, int, int, int]:
            nonlocal a, b, c, d, e, f, g, h
            a = _u64(a - e)
            f = _u64(f ^ (h >> 9))
            h = _u64(h + a)

            b = _u64(b - f)
            g = _u64(g ^ _u64(a << 9))
            a = _u64(a + b)

            c = _u64(c - g)
            h = _u64(h ^ (b >> 23))
            b = _u64(b + c)

            d = _u64(d - h)
            a = _u64(a ^ _u64(c << 15))
            c = _u64(c + d)

            e = _u64(e - a)
            b = _u64(b ^ (d >> 14))
            d = _u64(d + e)

            f = _u64(f - b)
            c = _u64(c ^ _u64(e << 20))
            e = _u64(e + f)

            g = _u64(g - c)
            d = _u64(d ^ (f >> 17))
            f = _u64(f + g)

            h = _u64(h - d)
            e = _u64(e ^ _u64(g << 14))
            g = _u64(g + h)
            return a, b, c, d, e, f, g, h

        for _ in range(4):
            mix()

        for i in range(0, 256, 8):
            if flag:
                a = _u64(a + self.randrsl[i])
                b = _u64(b + self.randrsl[i + 1])
                c = _u64(c + self.randrsl[i + 2])
                d = _u64(d + self.randrsl[i + 3])
                e = _u64(e + self.randrsl[i + 4])
                f = _u64(f + self.randrsl[i + 5])
                g = _u64(g + self.randrsl[i + 6])
                h = _u64(h + self.randrsl[i + 7])
            mix()
            self.mm[i] = a
            self.mm[i + 1] = b
            self.mm[i + 2] = c
            self.mm[i + 3] = d
            self.mm[i + 4] = e
            self.mm[i + 5] = f
            self.mm[i + 6] = g
            self.mm[i + 7] = h

        if flag:
            for i in range(0, 256, 8):
                a = _u64(a + self.mm[i])
                b = _u64(b + self.mm[i + 1])
                c = _u64(c + self.mm[i + 2])
                d = _u64(d + self.mm[i + 3])
                e = _u64(e + self.mm[i + 4])
                f = _u64(f + self.mm[i + 5])
                g = _u64(g + self.mm[i + 6])
                h = _u64(h + self.mm[i + 7])
                mix()
                self.mm[i] = a
                self.mm[i + 1] = b
                self.mm[i + 2] = c
                self.mm[i + 3] = d
                self.mm[i + 4] = e
                self.mm[i + 5] = f
                self.mm[i + 6] = g
                self.mm[i + 7] = h

        self._isaac64()
        self.randcnt = 256

    def _isaac64(self) -> None:
        self.cc = _u64(self.cc + 1)
        self.bb = _u64(self.bb + self.cc)

        for i in range(256):
            x = self.mm[i]
            if (i & 3) == 0:
                # aa ^= ~(aa << 21)
                self.aa = _u64(self.aa ^ (_u64(self.aa << 21) ^ _MASK_64))
            elif (i & 3) == 1:
                self.aa = _u64(self.aa ^ (self.aa >> 5))
            elif (i & 3) == 2:
                self.aa = _u64(self.aa ^ _u64(self.aa << 12))
            else:
                self.aa = _u64(self.aa ^ (self.aa >> 33))

            self.aa = _u64(self.mm[(i + 128) & 255] + self.aa)
            y = _u64(self.mm[(x >> 3) & 255] + self.aa + self.bb)
            self.mm[i] = y
            self.bb = _u64(self.mm[(y >> 11) & 255] + x)
            self.randrsl[i] = self.bb

    def rand_u64(self) -> int:
        """Return the next ISAAC-64 output as an unsigned 64-bit integer.

        Note: The original reference `rand()` consumes `randrsl[]` in reverse order.
        """
        if self.randcnt == 0:
            self._isaac64()
            self.randcnt = 256
        self.randcnt -= 1
        return _u64(self.randrsl[self.randcnt])

    # Backward-compatible alias (older callers used `get_next()`).
    def get_next(self) -> int:  # pragma: no cover
        return self.rand_u64()

    KeystreamWordFormat = Literal["raw_le", "raw_be", "be_swap32", "le_swap32"]

    @staticmethod
    def _raw_to_bytes(raw: int, word_format: KeystreamWordFormat) -> bytes:
        """Serialize one 64-bit `rand()` output to 8 bytes.

        - raw_le/raw_be: direct endianness of the 64-bit integer.
        - be_swap32: big-endian bytes with 32-bit halves swapped (BE(lo32)||BE(hi32)).
          This matches the byte layout implied by the doc's `htonl(hi32)||htonl(lo32)`
          pattern when the resulting u64 is read as bytes on little-endian hosts.
        - le_swap32: little-endian bytes with 32-bit halves swapped.
        """
        v = _u64(raw)
        if word_format == "raw_le":
            return int(v).to_bytes(8, "little", signed=False)
        if word_format == "raw_be":
            return int(v).to_bytes(8, "big", signed=False)
        if word_format == "be_swap32":
            b = int(v).to_bytes(8, "big", signed=False)
            return b[4:8] + b[0:4]
        if word_format == "le_swap32":
            b = int(v).to_bytes(8, "little", signed=False)
            return b[4:8] + b[0:4]
        raise ValueError(f"Unknown ISAAC64 word_format: {word_format}")

    def generate_keystream(self, size: int, *, word_format: KeystreamWordFormat = "be_swap32") -> bytes:
        """Generate a keystream of `size` bytes.

        This mirrors the decryption loop behavior: produce a new 8-byte keyblock
        for every 8 bytes of input, and slice for tail bytes.
        """
        want = int(size or 0)
        if want <= 0:
            return b""

        blocks = (want + 7) // 8
        out = bytearray()
        for _ in range(blocks):
            out.extend(self._raw_to_bytes(self.rand_u64(), word_format))
        return bytes(out[:want])
