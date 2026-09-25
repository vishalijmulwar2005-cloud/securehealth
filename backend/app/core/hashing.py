"""Port of the verified console's util.js (preserved behavior, TRD §16/§17).

sha256Hex, mulberry32 PRNG and Box-Muller gauss are bit-faithful ports of the
audited source (server/util.js) — the FL/ledger regression-parity test proves
identical outputs against the original JavaScript implementation.
"""
import hashlib
import math

M32 = 0xFFFFFFFF


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def mulberry32(seed: int):
    """Deterministic PRNG — exact port of util.js mulberry32.

    JS arithmetic is 32-bit; XOR/ADD/IMUL low-32 are all ring operations mod
    2^32, and the final `>>> 0` reinterprets unsigned — so pure mod-2^32 math
    reproduces the sequence exactly.
    """
    a = seed & M32

    def rng() -> float:
        nonlocal a
        a = (a + 0x6D2B79F5) & M32
        t = ((a ^ (a >> 15)) * ((a | 1) & M32)) & M32          # Math.imul(a ^ a>>>15, 1|a)
        inner = (((t ^ (t >> 7)) * ((61 | t) & M32)) & M32)    # Math.imul(t ^ t>>>7, 61|t)
        t = ((t + inner) & M32) ^ t                            # (t + imul) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296            # (t ^ t>>>14) >>> 0

    return rng


def gauss(rng) -> float:
    """Standard normal via Box-Muller — port of seed.js/util.js gauss."""
    u = 0.0
    v = 0.0
    while u == 0.0:
        u = rng()
    while v == 0.0:
        v = rng()
    return math.sqrt(-2.0 * math.log(u)) * math.cos(2.0 * math.pi * v)


# seed.js exports randn === gauss (identical function body in util.js)
randn = gauss
