#!/usr/bin/env python3
"""HOLLY G1 checksum - patch a Dreamcast / System SP BIOS image so HOLLY accepts it.

HOLLY G1 check (validated against 68,245 tests on real hardware):
  - a checksum is computed over the first (size - 2) bytes of the BIOS image
    (spread + addition + sticky XOR + fold pattern toggled 0 <-> 0x1104 on overflow);
  - the result is compared with the STORED value: the last 2 bytes of the image,
    little-endian. G1 opens if they are equal AND the fold is 0 AFTER the 2 stored
    bytes have been summed too. This fits all 67,802 Develop hardware tests and both
    dc_boot_mod patches (the one ending with fold 0x1104 failed on real hardware).
    The script therefore targets that by default, with the shortest patch (3-8 bytes)
    that reaches it; --any-fold restores the old behaviour (stored value only).
  A BIOS whose last 2 bytes are 00 00 therefore needs a checksum of 0x0000.

MiniHolly-style rule (--verify only, UNCONFIRMED on full-size BIOSes):
  g1min.bin (MiniHolly, 22 bytes) opened G1 on NAOMI 2 although it fails the stored-value
  rule: its WHOLE checked area, stored bytes included, ends on (0x0000, fold 0x1104).
  No Develop hardware test ever ended on that state. --verify reports such images with
  exit code 3 (not 0). The patcher never targets this rule.

Checked size ('auto'):
  Every HOLLY/CLX2 BIOS writes the last address of the checked area to SB_SECUR_EADR
  (0x005F74E4). With SIZE = auto, the script finds that write in the boot code (including
  the hidden loader at 0xE0, stored with its halfwords or longwords reversed) and
  uses value + 1. It also follows loaders the boot code builds in RAM (Develop BIOS).
  Found in all 53 BIOSes tested: Dreamcast / NAOMI / NAOMI 2 / System SP 0x1FFFFF,
  Develop 0x3FF, Atomiswave 0xA677 (bios0/bios1) and 0xA673 (fpr-24363, BIOS at 0x60000).

System SP:
  The three System SP BIOSes tested (epr-24236a, epr-24328, epr-24328a) follow the
  Dreamcast stored-value rule: checksum of 0x0-0x1FFFFD = 0x0000 = stored value. They use
  the same hidden loader at 0xE0 as NAOMI, and Sega tunes 6 bytes at 0x1FFDFA-0x1FFDFF so
  the checksum reaches (0x0000, fold 0) before the zero tail. Use the default mode
  (size 0x200000 or auto). Patched System SP BIOSes have not been tested on hardware.

BIOS image location inside the file:
  --base  start of the BIOS image in the file (default 0x0)
  size    size of the BIOS image (positional), base + size <= file size
  e.g. a 0x200000 file holding a 0x400 Develop BIOS at offset 0 -> size = 0x400.
  Bytes outside [base, base + size) are copied unchanged to the output.
  All offsets (--write, --file, --offset, messages) are RELATIVE TO THE BIOS IMAGE.

How it works:
  - optional changes at any offset (--write / --file); without them, the input is
    treated as an already modified BIOS;
  - the target is the stored value (last 2 bytes). It can be changed with --set-stored;
  - the checksum is corrected by a few bytes placed in the FREE AREA of
    'free_area' bytes located just before the last 2 bytes:
        [size - 2 - free_area, size - 2)
    Default free_area = 8 bytes (64 bits); the 3-byte patch always fits in it.
    e.g. size = 0x400, free_area = 8 -> free area 0x3F6 to 0x3FD inclusive.
  - by default the patch (3 bytes) is placed at the very end of the free area
    (size - 5 .. size - 3): nothing follows it, so the target can be reached
    (exhaustive check for 0x0000 over all 131072 states; sampled for other targets).
  - among all valid patches, the one that changes the FEWEST bytes is chosen
    (ties: the one closest to the padding byte, 0x00 or 0xFF, of the free area).

Safety:
  - BIOS sizes above 0x200000 (2 MiB) are refused unless --force is given;
  - the patch refuses to overwrite non-padding bytes (other than 0x00 / 0xFF)
    unless --force is given;
  - the output must differ from the input; it is written to a temporary file,
    verified, then renamed (a crash never leaves a half-written output).

NAOMI / NAOMI 2 BIOS (--reference REF) - EXPERIMENTAL:
  NAOMI BIOSes do NOT store the expected value in their last 2 bytes. Sega adjusts the last
  6 bytes of each region variant, so those bytes feed the check, but the official BIOSes end
  on many different final values (16 distinct values over 33 NAOMI / NAOMI 2 files), and
  region variants of one build do not always share a value. The exact NAOMI rule is unknown.
  --reference assumes that acceptance depends only on the final state over 'size' bytes,
  and makes the modified BIOS end on a final state (checksum and fold) already used by an
  official BIOS that boots, by patching its last 6 bytes.
  Matching the fold as well needs 6 bytes: 4 bytes only reach 87,381 of the 131,072
  possible states, 6 bytes reach 131,071, which is also what Sega reserves. The one state
  6 bytes cannot reach (start - 1, same fold: it needs two overflows) needs 7, so the
  script falls back to 7 or 8 bytes in that case only. On retail NAOMI those extra bytes
  are in the fixed tail block, so --force is then required.
  REF can be a directory of unmodified BIOSes: the one closest to the input (fewest
  differing bytes) is picked automatically.
  Whether HOLLY accepts the result has not been tested on hardware.

Patch styles (--style):
  minimal  (default) fewest changed bytes, ending just before the stored value (or at the
           end of the image in NAOMI mode).
  develop  the Develop BIOS scheme: an even split (3 bytes, more if needed) that reaches the
           stored value with fold 0x1104, then the fixed reset 53 AD AD AD, which adds exactly
           0x10000 and leaves fold 0. Reproduces the Develop BIOS's own CF CE CE 53 AD AD AD.
  naomi    the official NAOMI scheme, in the last 6 bytes: bit 7 on the first bytes provides
           the extra wrap, the rest is split evenly over the low 7 bits. Same construction as
           Sega's, but not Sega's exact bytes (the exact choice could not be derived).

NAOMI without a reference file (--naomi, --naomi-target):
  Patching keeps the INPUT's own final state when changes are given with --write/--file on
  an unmodified official BIOS - the same way Sega's region variants keep their build's
  value. For an input that is already modified, give the original value with
  --naomi-target (e.g. 0x4A73, or 0xF853:0x1104). --verify --naomi checks the final state
  against the 17 known official NAOMI / NAOMI 2 values. Experimental, like --reference.

Optional patch file (--patch-file): IPS (.ips) or BPS (.bps) patch from the input
to the output, so changes can be shared without distributing the BIOS.

Exit codes: 0 = OK, 1 = failure / refused, 2 = invalid arguments.

Examples:
  holly_g1_checksum.py bios.bin out.bin 0x200000
  holly_g1_checksum.py bios.bin out.bin 0x400 --write 0x10=DEADBEEF
  holly_g1_checksum.py bios.bin out.bin 0x200000 --file 0x8000=logo.bin --patch-file out.bps
  holly_g1_checksum.py dump.bin out.bin 0x400 --base 0x10000 --json
  holly_g1_checksum.py bios.bin 0x400 --verify
  holly_g1_checksum.py bios.bin auto --verify          (size read from SB_SECUR_EADR)
  holly_g1_checksum.py naomi.bin 0x200000 --verify --reference naomi_bioses/
  holly_g1_checksum.py modified.bin out.bin 0x200000 --reference naomi_bioses/
  holly_g1_checksum.py epr-21576a.ic27 out.bin auto --naomi --write 0x4BF68=03 --style naomi
  holly_g1_checksum.py bios.bin out.bin 0x400 --write 0x10=DEADBEEF --style develop
"""
import argparse
import struct
import json
import os
import sys
import tempfile
import zlib

import numpy as np

DEFAULT_FREE_AREA = 8      # bytes (64 bits) just before the last 2 bytes
MAX_BIOS_SIZE = 0x200000   # largest expected BIOS size; above it --force is required
FOLD = 0x1104              # fold pattern = spread(0x52)
PREVIEW = 16               # max bytes shown for user writes
PADDING = (0x00, 0xFF)
MAX_LENGTH = 8             # max patch length. 6 bytes reach every checksum state but one
                           # (start - 1 with the same fold, which needs two overflows); 7 reach all
SEGA_TUNE = 6              # NAOMI: last bytes Sega tunes to keep the checksum per version
NAOMI_LENGTH = 6           # NAOMI: preferred patch length (Sega's 6 bytes); 7-8 only as fallback


class Fail(Exception):
    """Error that stops the script (exit code 1)."""


# --------------------------------------------------------------------------- checksum

def spread(b):
    """8 bits -> 16 bits, bit m moved to position 2m (Morton spread, no loop)."""
    b = (b | b << 4) & 0x0F0F
    b = (b | b << 2) & 0x3333
    b = (b | b << 1) & 0x5555
    return b


SPREAD = [spread(i) for i in range(256)]
SP = np.array(SPREAD, dtype=np.int64)
INV = np.full(0x10000, -1, dtype=np.int64)     # inverse spread: 16-bit value -> byte
INV[SP] = np.arange(256)


def state(data, A=0, fold=0):
    """State (A, fold) after processing 'data' starting from (A, fold)."""
    sp = SPREAD
    for byte in data:
        A += sp[byte] ^ fold
        if A >= 0x10000:
            A &= 0xFFFF
            fold ^= FOLD
    return A, fold


def checksum(data, A=0):
    """16-bit checksum of 'data' (iterable of bytes), initial state A."""
    return state(data, A)[0]


def final_fold_ok(cs_fold, stored, size_bytes):
    """Fold after summing the 2 stored bytes, starting from (stored, cs_fold) - i.e. the
    state at the compare point when the stored-value check passes. Must be 0."""
    return state(size_bytes, stored, cs_fold)[1] == 0


def allowed_folds(stored_bytes):
    """Folds at the compare point (before the stored bytes) that leave fold 0 afterwards."""
    W = stored_bytes[0] | stored_bytes[1] << 8
    return [f for f in (0, FOLD) if state(stored_bytes, W, f)[1] == 0]


def stored_value(image, size):
    """Value HOLLY compares the checksum with: last 2 bytes of the image, little-endian."""
    return image[size - 2] | (image[size - 1] << 8)


def holly_check(image, size, A=0):
    """(ok, computed, stored) for a BIOS image of 'size' bytes starting at image[0]."""
    computed = checksum(image[:size - 2], A)
    stored = stored_value(image, size)
    return computed == stored, computed, stored


# --------------------------------------------------------------------------- patch search
# A state is encoded as key = A | (fold active) << 16.
# Each candidate carries a cost: (MAX_LENGTH + 1) per byte changed from the original
# + 1 per byte different from the padding byte. Lowest cost wins. The weight makes the
# order strict: fewest changed bytes first, then closest to padding.

def byte_cost(old_byte, pad):
    v = np.arange(256, dtype=np.int64)
    return (MAX_LENGTH + 1) * (v != old_byte) + (v != pad)


def _dedup_min(keys, cost):
    """Indices keeping, for each distinct key, the candidate with the lowest cost."""
    comp = keys * 128 + cost                    # cost < 128 (<= (MAX_LENGTH + 2) * MAX_LENGTH = 80)
    comp_u, idx = np.unique(comp, return_index=True)
    k = comp_u >> 7
    first = np.ones(len(k), dtype=bool)
    first[1:] = k[1:] != k[:-1]
    return idx[first]


def _start(A, fold):
    return (np.array([A | ((fold != 0) << 16)], dtype=np.int64),
            np.zeros(1, dtype=np.int64),
            np.zeros((1, 0), dtype=np.uint8))


EXTEND_CHUNK = 8192         # parent states processed at once (8192 x 256 candidates)
NO_COST = np.iinfo(np.int64).max


def _extend(keys, cost, patches, bcost):
    """Append one free byte to every state; keep the cheapest path to each new state.
    Works in chunks over a dense table of the 131072 possible states, so memory stays
    bounded even when every state is reachable (5th and 6th byte of a 6-byte patch)."""
    best_cost = np.full(1 << 17, NO_COST, dtype=np.int64)
    best_parent = np.zeros(1 << 17, dtype=np.int64)
    best_val = np.zeros(1 << 17, dtype=np.uint8)
    for s in range(0, len(keys), EXTEND_CHUNK):
        k = keys[s:s + EXTEND_CHUNK]
        a = k & 0xFFFF
        fl = k >> 16
        n = a[:, None] + (SP[None, :] ^ np.where(fl, FOLD, 0)[:, None])
        nk = ((n & 0xFFFF) | ((fl[:, None] ^ (n >= 0x10000)) << 16)).ravel()
        nc = (cost[s:s + EXTEND_CHUNK, None] + bcost[None, :]).ravel()
        sel = _dedup_min(nk, nc)                # cheapest candidate per state in this chunk
        tk, tc = nk[sel], nc[sel]
        better = tc < best_cost[tk]
        tk, tc, sel = tk[better], tc[better], sel[better]
        best_cost[tk] = tc
        best_parent[tk] = s + sel // 256
        best_val[tk] = sel % 256
    nkeys = np.nonzero(best_cost != NO_COST)[0]
    return (nkeys, best_cost[nkeys],
            np.hstack([patches[best_parent[nkeys]], best_val[nkeys, None]]))


def solve_at_end(A, fold, old, pad, target, target_fold=None):
    """Patch followed by NO bytes: (len-1) bytes searched, last byte computed directly.
    If target_fold is given (0 or FOLD), the final fold must match it too."""
    keys, cost, patches = _start(A, fold)
    for i in range(len(old) - 1):
        keys, cost, patches = _extend(keys, cost, patches, byte_cost(old[i], pad))
    a = keys & 0xFFFF
    f = np.where(keys >> 16, FOLD, 0)
    last = byte_cost(old[-1], pad)
    best = None
    for base in (target, target + 0x10000):    # without / with final overflow
        x = base - a
        ok = (x >= 0) & (x <= 0x5555)
        b = INV[np.where(ok, x, 0) ^ f]
        ok &= b >= 0
        if target_fold is not None:            # fold after the last byte must match
            ok &= (f ^ (FOLD if base > 0xFFFF else 0)) == target_fold
        i = np.nonzero(ok)[0]
        if len(i):
            total = cost[i] + last[b[i]]
            j = i[np.argmin(total)]
            if best is None or total.min() < best[0]:
                best = (int(total.min()), bytes(patches[j].tolist() + [int(b[j])]))
    return best[1] if best else None


def solve_in_middle(A, fold, old, pad, rest, target, target_fold=None):
    """Patch followed by the (kept) bytes 'rest': search + propagation."""
    keys, cost, patches = _start(A, fold)
    for i in range(len(old)):
        keys, cost, patches = _extend(keys, cost, patches, byte_cost(old[i], pad))
    rep = np.arange(len(keys))
    for b in rest:
        a = (keys & 0xFFFF) + (SPREAD[b] ^ np.where(keys >> 16, FOLD, 0))
        keys = (a & 0xFFFF) | (((keys >> 16) ^ (a >= 0x10000)) << 16)
        sel = _dedup_min(keys, cost)
        keys, cost, rep = keys[sel], cost[sel], rep[sel]
    match = (keys & 0xFFFF) == target
    if target_fold is not None:
        match &= (keys >> 16) == (target_fold != 0)
    i = np.nonzero(match)[0]
    if not len(i):
        return None
    return bytes(patches[rep[i[np.argmin(cost[i])]]])


# --------------------------------------------------------------------------- Sega-style patches
# Both styles work on EFFECTIVE bytes e: the value a byte adds is spread(e) whatever the fold,
# because spread(raw) ^ 0x1104 == spread(raw ^ 0x52). The raw byte written is e ^ 0x52 while
# the fold is 0x1104, e otherwise.

DEVELOP_RESET = bytes([0x53, 0xAD, 0xAD, 0xAD])   # with fold 0x1104: adds 1 + 3 * 0x5555 = 0x10000
OFFICIAL_NAOMI = {                                # final (checksum, fold) of official NAOMI BIOSes
    (0x5B57, 0): "epr-21576, 21577d", (0x4A73, 0): "epr-21576a/b, 21577a, 21578a, 21579",
    (0x14A2, 0): "epr-21576c", (0x4A53, 0): "epr-21576d, 21578d",
    (0x4653, 0): "epr-21576e/g, 21577g, 21578e", (0xF853, FOLD): "epr-21576h, 21577h, 21578h",
    (0x8E53, FOLD): "epr-21577e", (0x4843, 0): "epr-21578f", (0x1253, 0): "epr-21578g",
    (0x1043, 0): "epr-21579d, 23608", (0x2349, 0): "epr-21336a (Develop)",
    (0x1233, 0): "epr-23605", (0x483B, 0): "epr-23605a, 23608a",
    (0x4853, 0): "epr-23605b, 23607b, 23608b, 23609b", (0x485B, 0): "epr-23605c, 23608c",
    (0x5F47, 0): "epr-23607", (0x484B, 0): "epr-23607c, 23610b",
}
_SPREADS = sorted((SPREAD[e], e) for e in range(256))


def _plan_total(A0, f0, target, target_fold, cap):
    """Total amount to add (smallest) taking (A0, f0) to (target, target_fold), with the
    right number of wraps for the fold. None if more than 'cap' would be needed."""
    D = (target - A0) & 0xFFFF
    for w in range(4):
        total = D + 0x10000 * w
        wraps = (A0 + total) >> 16
        if total <= cap and (wraps & 1) == ((f0 != 0) != (target_fold != 0)):
            return total
    return None


_REACH = {}


def _reachable(allowed, k):
    """Bitmask (Python int) of every total reachable as the sum of the spreads of k bytes
    taken from 'allowed' (cached)."""
    key = (allowed, k)
    if key not in _REACH:
        if k == 0:
            _REACH[key] = 1
        else:
            prev, acc = _reachable(allowed, k - 1), 0
            for v in {SPREAD[e] for e in allowed}:
                acc |= prev << v
            _REACH[key] = acc
    return _REACH[key]


def _even_split(total, n, allowed):
    """n effective bytes (each from 'allowed') whose spreads add up to 'total' exactly, each
    as close as possible to an equal share of what is left (share rounded up, larger value on
    ties). Exact: a value is only taken if the remainder is still reachable. List or None."""
    allowed = tuple(allowed)
    vals = sorted((SPREAD[e], e) for e in allowed)
    if not (_reachable(allowed, n) >> total) & 1:
        return None
    out, R = [], total
    for left in range(n, 0, -1):
        share = -(-R // left)
        for v, e in sorted(vals, key=lambda t: (abs(t[0] - share), -t[0])):
            rest = R - v
            if rest >= 0 and (_reachable(allowed, left - 1) >> rest) & 1:
                out.append(e)
                R = rest
                break
    return out


def _to_raw(A0, f0, effective):
    """Raw bytes for a list of effective bytes, simulating the fold."""
    A, f, out = A0, f0, bytearray()
    for e in effective:
        out.append(e ^ (0x52 if f else 0))
        A += SPREAD[e]
        if A >= 0x10000:
            A &= 0xFFFF
            f ^= FOLD
    return bytes(out), (A, f)


def develop_style(state_at, zone, target, fold_options, room=None):
    """Develop BIOS scheme: an even split that reaches (target, fold 0x1104), followed by the
    fixed reset 53 AD AD AD, which adds exactly 0x10000 and leaves (target, fold 0).
    If that doesn't fit in 'room' bytes (or the reset can't be used: stored value above
    0x5554, or only fold 0x1104 allowed), a plain even split to the required fold is used.
    state_at(offset) gives the checksum state before 'offset'. Returns (offset, bytes, note)."""
    reset_ok = 0 in fold_options and target <= 0x5554   # the reset must wrap on its last byte
    plain_fold = 0 if 0 in fold_options else FOLD
    plans = ([(True, n) for n in (3, 4, 5)] if reset_ok else []) + \
            [(False, n) for n in (3, 4, 5)]
    for use_reset, n in plans:
        length = n + (len(DEVELOP_RESET) if use_reset else 0)
        if room is not None and length > room:
            continue
        end_fold = FOLD if use_reset else plain_fold
        A0, f0 = state_at(zone - length)
        total = _plan_total(A0, f0, target, end_fold, n * 0x5555)
        if total is None:
            continue
        eff = _even_split(total, n, range(256))
        if eff is None:
            continue
        raw, st = _to_raw(A0, f0, eff)
        if st != (target, end_fold):
            continue
        if use_reset:
            return zone - length, raw + DEVELOP_RESET, f"{n}-byte even split + reset 53 AD AD AD"
        why = ("the reset needs fold 0 allowed and a stored value up to 0x5554" if not reset_ok
               else "split + reset would not fit in the free area")
        return zone - length, raw, f"{n}-byte even split, no reset ({why})"
    return None


def naomi_style(A0, f0, target, target_fold):
    """NAOMI scheme (6 bytes): bit 7 set on the first k effective bytes (k = 4 for one extra
    wrap, as in most official BIOSes; 6 or 0 when needed), and the rest of the amount split
    evenly over the low 7 bits of all six bytes. Returns raw bytes or None."""
    total = _plan_total(A0, f0, target, target_fold, 6 * 0x5555)
    if total is None:
        return None
    for k in (4, 6, 0, 2, 5, 3, 1):
        r = total - 0x4000 * k
        if 0 <= r <= 6 * 0x1555:
            low = _even_split(r, 6, range(0x80))
            if low is None:
                continue
            eff = [(0x80 if i < k else 0) | x for i, x in enumerate(low)]
            raw, st = _to_raw(A0, f0, eff)
            if st == (target, target_fold):
                return raw
    return None


def parse_naomi_target(x):
    """'0x4A73' or '0x4A73:0x1104' -> (checksum, fold)."""
    a, _, f = x.partition(':')
    fold = int(f, 0) if f else 0
    if fold not in (0, FOLD):
        raise argparse.ArgumentTypeError("fold must be 0 or 0x1104")
    return int(a, 0) & 0xFFFF, fold


# --------------------------------------------------------------------------- IPS / BPS

def _diff_runs(src, dst, max_run=None):
    """(start, end) runs of differing bytes between two equal-size buffers."""
    d = np.nonzero(np.frombuffer(src, np.uint8) != np.frombuffer(dst, np.uint8))[0]
    runs = []
    if len(d):
        breaks = np.nonzero(np.diff(d) != 1)[0]
        starts = np.concatenate([[d[0]], d[breaks + 1]])
        ends = np.concatenate([d[breaks] + 1, [d[-1] + 1]])
        for s, e in zip(starts.tolist(), ends.tolist()):
            while max_run and e - s > max_run:
                runs.append((s, s + max_run))
                s += max_run
            runs.append((s, e))
    return runs


def make_ips(src, dst):
    if len(dst) > 0x1000000:
        raise Fail("IPS only supports files up to 16 MiB; use a .bps patch file")
    out = bytearray(b'PATCH')
    for s, e in _diff_runs(src, dst, 0xFFFE):
        if s == 0x454F46:                       # offset would read as 'EOF'
            s -= 1
        out += s.to_bytes(3, 'big') + (e - s).to_bytes(2, 'big') + dst[s:e]
    return bytes(out + b'EOF')


def apply_ips(src, p):
    if p[:5] != b'PATCH':
        raise Fail("invalid IPS header")
    out, i = bytearray(src), 5
    while p[i:i + 3] != b'EOF':
        off = int.from_bytes(p[i:i + 3], 'big')
        n = int.from_bytes(p[i + 3:i + 5], 'big')
        i += 5
        if n == 0:                              # RLE record
            n = int.from_bytes(p[i:i + 2], 'big')
            out[off:off + n] = p[i + 2:i + 3] * n
            i += 3
        else:
            out[off:off + n] = p[i:i + n]
            i += n
    return bytes(out)


def _vlq(n):
    out = bytearray()
    while True:
        x = n & 0x7F
        n >>= 7
        if n == 0:
            out.append(0x80 | x)
            return bytes(out)
        out.append(x)
        n -= 1


def _read_vlq(p, i):
    data, shift = 0, 1
    while True:
        x = p[i]
        i += 1
        data += (x & 0x7F) * shift
        if x & 0x80:
            return data, i
        shift <<= 7
        data += shift


def make_bps(src, dst):
    out = bytearray(b'BPS1') + _vlq(len(src)) + _vlq(len(dst)) + _vlq(0)
    pos = 0
    for s, e in _diff_runs(src, dst):
        if s > pos:
            out += _vlq(((s - pos - 1) << 2) | 0)       # SourceRead
        out += _vlq(((e - s - 1) << 2) | 1) + dst[s:e]  # TargetRead
        pos = e
    if pos < len(dst):
        out += _vlq(((len(dst) - pos - 1) << 2) | 0)
    out += zlib.crc32(src).to_bytes(4, 'little') + zlib.crc32(dst).to_bytes(4, 'little')
    out += zlib.crc32(out).to_bytes(4, 'little')
    return bytes(out)


def apply_bps(src, p):
    if p[:4] != b'BPS1' or zlib.crc32(p[:-4]) != int.from_bytes(p[-4:], 'little'):
        raise Fail("invalid BPS header or checksum")
    if zlib.crc32(src) != int.from_bytes(p[-12:-8], 'little'):
        raise Fail("BPS source CRC mismatch")
    i = 4
    _, i = _read_vlq(p, i)
    tsize, i = _read_vlq(p, i)
    msize, i = _read_vlq(p, i)
    i += msize
    out = bytearray()
    while i < len(p) - 12:
        d, i = _read_vlq(p, i)
        action, n = d & 3, (d >> 2) + 1
        if action == 0:
            out += src[len(out):len(out) + n]
        elif action == 1:
            out += p[i:i + n]
            i += n
        else:
            raise Fail("unsupported BPS action")
    if len(out) != tsize or zlib.crc32(out) != int.from_bytes(p[-8:-4], 'little'):
        raise Fail("BPS target CRC mismatch")
    return bytes(out)


PATCH_FORMATS = {'.ips': (make_ips, apply_ips), '.bps': (make_bps, apply_bps)}


# --------------------------------------------------------------------------- output

class Reporter:
    """Human-readable lines, --quiet (errors/warnings only) or --json (one object)."""

    def __init__(self, quiet, as_json):
        self.quiet, self.as_json = quiet, as_json
        self.data = {"warnings": []}

    def info(self, msg):
        if not (self.quiet or self.as_json):
            print(msg)

    def warn(self, msg):
        self.data["warnings"].append(msg)
        if not self.as_json:
            print(f"warning: {msg}", file=sys.stderr)

    def set(self, **kw):
        self.data.update(kw)

    def finish(self, ok, error=None):
        self.data["ok"] = ok
        if error:
            self.data["error"] = error
            if not self.as_json:
                print(f"error: {error}", file=sys.stderr)
        if self.as_json:
            print(json.dumps(self.data, indent=2))


def h(n):
    return f"0x{n:X}"


def h4(n):
    return f"0x{n:04X}"


def hexstr(d, limit=None):
    """Hex representation, truncated to 'limit' bytes if requested."""
    if limit is not None and len(d) > limit:
        return d[:limit].hex(' ').upper() + f" ... (0x{len(d):X} bytes)"
    return d.hex(' ').upper()


def same_file(a, b):
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.abspath(a) == os.path.abspath(b)


def write_temp(path, data):
    """Write 'data' to a temporary file next to 'path'; return the temp path."""
    d = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix='.' + os.path.basename(path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        os.unlink(tmp)
        raise
    return tmp


# --------------------------------------------------------------------------- SB_SECUR_EADR
# Every HOLLY/CLX2 BIOS writes the LAST address of the checked area to SB_SECUR_EADR
# (0x005F74E4) before reading it (see MAME dccons_m.cpp). SIZE = value + 1.
EADR_PHYS = 0x005F74E4
M32 = 0xFFFFFFFF


def _s8(i8):
    return i8 - 256 if i8 > 127 else i8


def _decode_eadr_writes(code, base_addr, lo, hi):
    """Linear scan of SH-4 code tracking register constants (literals, immediates, shifts,
    logic, GBR) and reporting every 32-bit store to SB_SECUR_EADR: (address, value)."""
    regs = [None] * 16
    gbr = None
    out = []
    mem = {}                                                  # RAM built by the code itself

    def store(addr, val, pc):
        if addr is not None and val is not None and addr & 0x1FFFFFFF == EADR_PHYS:
            out.append((base_addr + pc, val & M32))

    for pc in range(lo, min(hi, len(code) - 1), 2):
        op = struct.unpack_from('<H', code, pc)[0]
        n, m, i8, top = (op >> 8) & 15, (op >> 4) & 15, op & 0xFF, op >> 12
        rn, rm = regs[n], regs[m]
        r = regs
        if top == 0xD:                                        # mov.l @(disp,PC),Rn
            a = (pc & ~3) + 4 + i8 * 4
            r[n] = struct.unpack_from('<I', code, a)[0] if a + 4 <= len(code) else None
        elif top == 0x9:                                      # mov.w @(disp,PC),Rn
            a = pc + 4 + i8 * 2
            r[n] = (_s8(0) + struct.unpack_from('<h', code, a)[0]) & M32 if a + 2 <= len(code) else None
        elif top == 0xE:                                      # mov #imm,Rn
            r[n] = _s8(i8) & M32
        elif top == 0x7:                                      # add #imm,Rn
            r[n] = (rn + _s8(i8)) & M32 if rn is not None else None
        elif op >> 8 == 0xCB:                                 # or #imm,R0
            r[0] = r[0] | i8 if r[0] is not None else None
        elif op >> 8 == 0xC9:                                 # and #imm,R0
            r[0] = r[0] & i8 if r[0] is not None else None
        elif op >> 8 == 0xCA:                                 # xor #imm,R0
            r[0] = r[0] ^ i8 if r[0] is not None else None
        elif op >> 8 == 0xC2:                                 # mov.l R0,@(disp,GBR)
            store((gbr + i8 * 4) if gbr is not None else None, r[0], pc)
        elif op >> 8 in (0xC6, 0xC4, 0xC5):                   # mov.x @(disp,GBR),R0
            r[0] = None
        elif top == 0x1:                                      # mov.l Rm,@(disp,Rn)
            store((rn + (op & 15) * 4) if rn is not None else None, rm, pc)
        elif op & 0xF00F == 0x2002:                           # mov.l Rm,@Rn
            store(rn, rm, pc)
            if rn is not None and rm is not None:
                mem[rn & 0x1FFFFFFF] = rm
        elif op & 0xF00F == 0x2006:                           # mov.l Rm,@-Rn (push)
            if rn is not None:
                r[n] = (rn - 4) & M32
                store(r[n], rm, pc)
                if rm is not None:
                    mem[r[n] & 0x1FFFFFFF] = rm
        elif op & 0xF00F == 0x6003:                           # mov Rm,Rn
            r[n] = rm
        elif op & 0xF00F == 0x300C:                           # add Rm,Rn
            r[n] = (rn + rm) & M32 if None not in (rn, rm) else None
        elif op & 0xF00F == 0x3008:                           # sub Rm,Rn
            r[n] = (rn - rm) & M32 if None not in (rn, rm) else None
        elif op & 0xF00F == 0x200B:                           # or
            r[n] = rn | rm if None not in (rn, rm) else None
        elif op & 0xF00F == 0x2009:                           # and
            r[n] = rn & rm if None not in (rn, rm) else None
        elif op & 0xF00F == 0x200A:                           # xor
            r[n] = rn ^ rm if None not in (rn, rm) else None
        elif op & 0xF00F == 0x6009:                           # swap.w
            r[n] = ((rm >> 16) | (rm << 16)) & M32 if rm is not None else None
        elif op & 0xF00F == 0x6008:                           # swap.b
            r[n] = (rm & 0xFFFF0000) | ((rm & 0xFF) << 8) | ((rm >> 8) & 0xFF) if rm is not None else None
        elif op & 0xF00F == 0x600C:                           # extu.b
            r[n] = rm & 0xFF if rm is not None else None
        elif op & 0xF00F == 0x600D:                           # extu.w
            r[n] = rm & 0xFFFF if rm is not None else None
        elif op & 0xF00F == 0x6007:                           # not
            r[n] = ~rm & M32 if rm is not None else None
        elif op & 0xF0FF in (0x4000, 0x4008, 0x4018, 0x4028, 0x4020):   # shll, 2, 8, 16, shal
            k = {0x4000: 1, 0x4008: 2, 0x4018: 8, 0x4028: 16, 0x4020: 1}[op & 0xF0FF]
            r[n] = (rn << k) & M32 if rn is not None else None
        elif op & 0xF0FF in (0x4001, 0x4009, 0x4019, 0x4029):           # shlr, 2, 8, 16
            k = {0x4001: 1, 0x4009: 2, 0x4019: 8, 0x4029: 16}[op & 0xF0FF]
            r[n] = rn >> k if rn is not None else None
        elif op & 0xF0FF == 0x401E:                           # ldc Rn,GBR
            gbr = rn
        elif op & 0xF0FF == 0x0012:                           # stc GBR,Rn
            r[n] = gbr
        elif op & 0xF0FF == 0x4010:                           # dt
            r[n] = (rn - 1) & M32 if rn is not None else None
        elif op in (0x000B, 0x002B) or top in (0xA, 0xB) or op & 0xF0FF in (0x402B, 0x400B):
            regs = [None] * 16                                # rts / bra / jmp / jsr
            r = regs
        elif top in (0x6, 0x0, 0x3, 0x4, 0x5, 0x2, 0x8, 0xC, 0xF):
            # anything else that may write Rn (loads, mul, movt, etc.): forget Rn conservatively
            if top in (0x6, 0x5) or (top == 0 and op & 0xF in (0x9, 0xA, 0xC, 0xD, 0xE)):
                r[n] = None
            elif top == 0x8 and n in (0x4, 0x5):              # mov.b/w @(disp,Rm),R0
                r[0] = None
            elif top == 0x3 and op & 0xF in (0x4, 0x5, 0x7, 0xA, 0xB, 0xD, 0xE, 0xF):
                r[n] = None
            elif top == 0x4 and op & 0xFF in (0x05, 0x04, 0x24, 0x25, 0x21, 0x0C, 0x1C, 0x2C, 0x2A,
                                                0x0A, 0x1A, 0x06, 0x16, 0x26):
                if op & 0xFF in (0x05, 0x04, 0x24, 0x25, 0x21, 0x0C, 0x1C, 0x2C):
                    r[n] = None
    _decode_eadr_writes.mem = mem
    return out


def _ram_blocks(mem):
    """Contiguous longword blocks written to RAM by the scanned code: [(addr, bytes)]."""
    blocks, cur, start = [], None, None
    for a in sorted(mem):
        if cur is not None and a == start + len(cur):
            cur += struct.pack('<I', mem[a])
        else:
            if cur:
                blocks.append((start, cur))
            start, cur = a, bytearray(struct.pack('<I', mem[a]))
    if cur:
        blocks.append((start, cur))
    return [(a, bytes(b)) for a, b in blocks if len(b) >= 8]


def find_eadr(bios, scan=0x1000):
    """Return [(where, value, kind)] for SB_SECUR_EADR writes in the boot code.
    Also decodes the hidden loader at 0xE0 (NAOMI / early Dreamcast), stored with its
    halfwords or longwords in reverse order."""
    hits = [(pc, v, 'boot code') for pc, v in _decode_eadr_writes(bios, 0, 0, scan)]
    for addr, blob in _ram_blocks(_decode_eadr_writes.mem):  # loader built in RAM (Develop)
        hits += [(pc | 0xA0000000, v, f'RAM loader built by the boot code at {addr | 0xA0000000:08X}')
                 for pc, v in _decode_eadr_writes(blob + bytes(64), addr, 0, len(blob))]
    if len(bios) >= 0x100:
        h = struct.unpack_from('<16H', bios, 0xE0)
        w = struct.unpack_from('<8I', bios, 0xE0)
        for kind, loader in (('halfwords reversed', struct.pack('<16H', *h[::-1])),
                             ('longwords reversed', struct.pack('<8I', *w[::-1]))):
            hits += [(0xE0, v, f'hidden loader at 0xE0 ({kind})')
                     for _, v in _decode_eadr_writes(loader + bytes(64), 0xE0, 0, 32)]
    return hits


def detect_size(bios, rep):
    """SIZE from the SB_SECUR_EADR write(s) in the boot code."""
    hits = [(a, v, k) for a, v, k in find_eadr(bios) if v not in (0, 0x42FE)]
    if not hits:
        raise Fail("size 'auto': no SB_SECUR_EADR write found in the boot code; give SIZE")
    values = sorted({v for _, v, _ in hits})
    for a, v, k in hits:
        rep.info(f"SB_SECUR_EADR    = {h(v)} written at {h(a)} ({k})")
    if len(values) > 1:
        raise Fail("size 'auto': several different SB_SECUR_EADR values found ("
                   + ", ".join(h(v) for v in values) + "); give SIZE")
    size = (values[0] & 0x1FFFFF) + 1
    rep.set(eadr=h(values[0]), eadr_sites=[{"at": h(a), "kind": k} for a, _, k in hits])
    rep.info(f"size (auto)      = {h(size)}")
    if size not in (0x400, 0x200000):
        rep.warn(f"checked size {h(size)} is not a Dreamcast/NAOMI size (0x400 / 0x200000); "
                 "Atomiswave (0xA678 / 0xA674) is not supported, and small custom images such "
                 "as MiniHolly may follow a different rule (see --verify exit code 3)")
    return size


# --------------------------------------------------------------------------- NAOMI reference

FAR_REFERENCE = 0x1000     # warn if the closest reference differs by more bytes than this


def find_reference(path, bios, base, size, init, rep):
    """Resolve --reference. A file is used as is. For a directory, every file large enough
    is compared with 'bios' (the input, before any change) and the one with the fewest
    differing bytes in [base, base + size) is used. Returns (path, A, fold)."""
    if not os.path.isdir(path):
        ref = open(path, 'rb').read()
        if base + size > len(ref):
            raise Fail(f"reference image [{h(base)}, {h(base + size)}) does not fit in "
                       f"{path} ({h(len(ref))} bytes)")
        A, fold = state(ref[base:base + size], init)
        rep.set(reference=path)
        return path, A, fold

    mine = np.frombuffer(bytes(bios), np.uint8)
    candidates = []                             # (differing bytes, path, region)
    for name in sorted(os.listdir(path)):
        f = os.path.join(path, name)
        if not os.path.isfile(f) or os.path.getsize(f) < base + size:
            continue
        region = open(f, 'rb').read()[base:base + size]
        dist = int(np.count_nonzero(np.frombuffer(region, np.uint8) != mine))
        candidates.append((dist, f, region))
    if not candidates:
        raise Fail(f"no file of at least {h(base + size)} bytes in {path}")
    candidates.sort(key=lambda c: (c[0], c[1]))
    dist, best, region = candidates[0]
    A, fold = state(region, init)

    # every reference ending on the same state (same group) - informative only
    group = [os.path.basename(f) for d, f, r in candidates if state(r, init) == (A, fold)]
    rep.set(reference=best, reference_distance=dist, reference_group=group)
    rep.info(f"reference        = {os.path.basename(best)} (closest of {len(candidates)}, "
             f"{dist} byte(s) differ)")
    rep.info(f"same final state = {', '.join(group)}")
    if dist > FAR_REFERENCE:
        rep.warn(f"the closest reference differs by {dist} bytes: the input may not be a "
                 f"version present in {path}")
    return best, A, fold


# --------------------------------------------------------------------------- main

def integer(x):
    return int(x, 0)


def pair(x):
    off, _, val = x.partition('=')
    if not val:
        raise argparse.ArgumentTypeError("expected format OFFSET=VALUE")
    return int(off, 0), val


def parse_args():
    p = argparse.ArgumentParser(description="Patch a BIOS so its HOLLY G1 checksum matches "
                                            "the stored value (last 2 bytes).")
    p.add_argument("image", help="input file (left unchanged)")
    p.add_argument("output", nargs="?",
                   help="output file (patched copy, must differ from the input); "
                        "not needed with --verify")
    p.add_argument("size", type=lambda x: 'auto' if x.lower() == 'auto' else int(x, 0),
                   help="checked BIOS size (decimal or 0x..), or 'auto' to read it from the "
                        "SB_SECUR_EADR write in the boot code")
    p.add_argument("--base", type=integer, default=0,
                   help="start of the BIOS image in the file (default 0x0)")
    p.add_argument("--verify", action="store_true",
                   help="only check the input (checksum == stored value), write nothing "
                        "(exit code 0 = OK, 1 = FAIL, 3 = MiniHolly-style: only the alternate, "
                        "unconfirmed rule passes - whole area ends on 0x0000 / fold 0x1104)")
    p.add_argument("--set-stored", type=integer, metavar="VALUE",
                   help="write a new stored value (16-bit, little-endian) to the last 2 bytes "
                        "and patch the checksum to match it")
    p.add_argument("--free-area", type=integer, default=DEFAULT_FREE_AREA,
                   help="free area size, just before the last 2 bytes: "
                        f"[size - 2 - free_area, size - 2) (default {DEFAULT_FREE_AREA})")
    p.add_argument("--offset", type=integer,
                   help="patch offset inside the free area (default: end of free area)")
    p.add_argument("--length", type=int,
                   help=f"patch length in bytes, 1..{MAX_LENGTH} (default 3 at end of area, "
                        "4 with --offset; with --reference up to 6, or 7-8 when 6 cannot "
                        "reach the target)")
    p.add_argument("--write", type=pair, action="append", default=[], metavar="OFF=HEX",
                   help="write hex bytes at any offset (repeatable)")
    p.add_argument("--file", type=pair, action="append", default=[], metavar="OFF=PATH",
                   help="write a file's contents at any offset (repeatable)")
    p.add_argument("--force", action="store_true",
                   help="allow the patch to overwrite non-padding bytes and allow a BIOS size "
                        "above 0x200000")
    p.add_argument("--patch-file", metavar="PATH",
                   help="also write an IPS (.ips) or BPS (.bps) patch from input to output")
    p.add_argument("--reference", metavar="REF",
                   help="EXPERIMENTAL NAOMI mode: checksum ALL 'size' bytes (no stored value) "
                        "and match the final checksum state of REF, an unmodified official BIOS. "
                        "REF can be a file, or a DIRECTORY of unmodified BIOSes: the closest "
                        "one (fewest differing bytes) is then picked automatically")
    p.add_argument("--naomi", action="store_true",
                   help="EXPERIMENTAL NAOMI mode without a reference file: the whole image is "
                        "checked. Patching keeps the input's own final state (use --write/--file "
                        "on an UNMODIFIED official BIOS), or the one given with --naomi-target. "
                        "--verify checks the final state against the known official values")
    p.add_argument("--naomi-target", type=parse_naomi_target, metavar="CHECKSUM[:FOLD]",
                   help="NAOMI mode: final state to reach, e.g. 0x4A73 or 0xF853:0x1104")
    p.add_argument("--style", choices=["minimal", "develop", "naomi"], default="minimal",
                   help="patch bytes: 'minimal' (default, fewest changed bytes), 'develop' (the "
                        "Develop BIOS scheme: even split + reset 53 AD AD AD before the stored "
                        "value), 'naomi' (the official NAOMI scheme in the last 6 bytes; NAOMI "
                        "mode only)")
    p.add_argument("--any-fold", action="store_true",
                   help="stored-value mode: only require checksum == stored value. By default the "
                        "fold must also be 0 after the 2 stored bytes (fits every hardware test; "
                        "an image that only matched the stored value failed on real hardware)")
    p.add_argument("--init", type=integer, default=0, help="initial state A (default 0)")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--quiet", action="store_true", help="print only warnings and errors")
    out.add_argument("--json", action="store_true", help="print a single JSON result object")
    return p.parse_args()


def run(args, rep):
    src = open(args.image, 'rb').read()
    image = bytearray(src)
    base, size = args.base, args.size
    if size == 'auto':
        if not 0 <= base < len(image):
            raise Fail(f"--base {h(base)} is outside the file")
        size = detect_size(image[base:], rep)
    if base < 0 or not 2 < size or base + size > len(image):
        raise Fail(f"BIOS image [{h(base)}, {h(base + size)}) does not fit in the file "
                   f"({h(len(image))} bytes)")
    if size > MAX_BIOS_SIZE:
        msg = f"BIOS size {h(size)} exceeds the maximum of {h(MAX_BIOS_SIZE)}"
        if not args.force:
            raise Fail(msg + ". Check the size argument, or use --force to bypass the limit.")
        rep.warn(msg + " (--force)")
    naomi = args.reference is not None or args.naomi or args.naomi_target is not None
    if naomi and args.set_stored is not None:
        raise Fail("--set-stored cannot be used in NAOMI mode (no stored value)")
    if args.style == "naomi" and not naomi:
        raise Fail("--style naomi needs NAOMI mode (--naomi, --naomi-target or --reference)")
    if args.style == "develop" and naomi:
        raise Fail("--style develop is for stored-value BIOSes, not NAOMI mode")
    if args.style != "minimal" and (args.offset is not None or args.length):
        raise Fail("--style sets the patch position and length itself: drop --offset/--length")
    if args.reference is not None and args.naomi_target is not None:
        raise Fail("use either --reference or --naomi-target, not both")
    # checked area: [0, zone) relative to base. Retail/Develop: size - 2 (stored value
    # follows). NAOMI (--reference): the whole image, compared with the reference state.
    zone = size if naomi else size - 2
    free_start = zone - args.free_area
    if naomi and args.reference is not None:
        ref_path, ref_A, ref_fold = find_reference(args.reference, image[base:base + size],
                                                   base, size, args.init, rep)
    elif naomi:
        ref_path = None
        if args.naomi_target is not None:
            ref_A, ref_fold = args.naomi_target
            ref_path = "--naomi-target"
        else:                                   # input's own final state (before any change)
            ref_A, ref_fold = state(image[base:base + size], args.init)
            ref_path = "input (before changes)"
            if not args.verify and not (args.write or args.file):
                if (ref_A, ref_fold) in OFFICIAL_NAOMI:
                    rep.warn("no --write/--file given and the input already ends on an official "
                             "final state: nothing to fix")
                else:
                    raise Fail("--naomi without --write/--file keeps the input's own final state, "
                               f"{h4(ref_A)}/{h4(ref_fold)}, which is not an official value: the "
                               "input looks modified already. Give the original target with "
                               "--naomi-target (or --reference ORIGINAL)")
        if (ref_A, ref_fold) not in OFFICIAL_NAOMI and not args.verify:
            rep.warn(f"target {h4(ref_A)}/{h4(ref_fold)} is not a known official NAOMI final state")
    if naomi:
        rep.warn("NAOMI mode is experimental: the NAOMI check is not fully understood and "
                 "this result has not been validated on hardware")
    if free_start < 0:
        raise Fail("free area larger than the checked area")

    def fo(o):                                  # offset text, with file offset if base != 0
        return h(o) + (f" (file {h(base + o)})" if base else "")

    def bios():
        return image[base:base + size]

    rep.set(input=args.image, size=h(size), base=h(base))
    if base or base + size < len(image):
        rep.info(f"file             = {h(len(image))} bytes, BIOS image = "
                 f"{h(base)} .. {h(base + size - 1)} (the rest is copied unchanged)")

    # Verify mode: input as is, nothing written
    if args.verify:
        if args.write or args.file or args.output or args.patch_file or \
                args.set_stored is not None:
            rep.warn("--verify ignores the output, --write, --file, --set-stored "
                     "and --patch-file")
        if naomi and args.reference is None and args.naomi_target is None:
            c, f = state(bios(), args.init)
            ok = (c, f) in OFFICIAL_NAOMI
            rep.set(mode="verify", checksum=h4(c), fold=h4(f),
                    official=OFFICIAL_NAOMI.get((c, f)))
            rep.info(f"checksum         = {h4(c)} (fold {h4(f)}) -> "
                     + (f"OK: official final state of {OFFICIAL_NAOMI[(c, f)]}" if ok
                        else "FAIL: not a known official NAOMI final state"))
            return ok
        if naomi:
            c, f = state(bios(), args.init)
            ok = (c, f) == (ref_A, ref_fold)
            rep.set(mode="verify", checksum=h4(c), fold=h4(f), reference=ref_path,
                    reference_checksum=h4(ref_A), reference_fold=h4(ref_fold))
            rep.info(f"checksum         = {h4(c)} (fold {h4(f)}), reference = {h4(ref_A)} "
                     f"(fold {h4(ref_fold)}) -> {'OK' if ok else 'FAIL'}")
            return ok
        ok, c, s = holly_check(bios(), size, args.init)
        f = state(bios()[:size - 2], args.init)[1]
        ff = state(bios()[size - 2:size], c, f)[1]          # fold after the stored bytes
        rep.set(mode="verify", checksum=h4(c), stored=h4(s), fold=h4(f), final_fold=h4(ff))
        if ok and ff and not args.any_fold:
            ok = False
            rep.warn(f"checksum matches the stored value but the fold is {h4(ff)} after the "
                     "stored bytes; it must be 0 (fits all hardware tests; an image like this "
                     "failed on real hardware). Use --any-fold to accept it")
        rep.info(f"checksum         = {h4(c)} (fold {h4(f)}), stored = {h4(s)}, fold after "
                 f"stored = {h4(ff)} -> {'OK' if ok else 'FAIL'}")
        rep.set(rule="stored-value" if ok else None)
        if not ok:
            # MiniHolly-style rule: the WHOLE checked area (stored bytes included) ends on
            # (0x0000, fold 0x1104). Seen on real NAOMI 2 hardware with g1min.bin (22 bytes),
            # never reached by any Develop hardware test: reported separately, not as OK.
            fa, ffa = state(bios(), args.init)
            rep.set(full_area_checksum=h4(fa), full_area_fold=h4(ffa))
            if (fa, ffa) == (0, FOLD):
                rep.set(rule="miniholly")
                rep.warn("the stored-value rule fails, but the whole checked area (stored bytes "
                         "included) ends on 0x0000 with fold 0x1104, like MiniHolly (g1min), "
                         "which opened G1 on NAOMI 2. This alternate rule is NOT confirmed on "
                         f"full-size BIOSes (exit code {EXIT_MINIHOLLY})")
                rep.info(f"full area        = {h4(fa)} (fold {h4(ffa)}) -> MINIHOLLY-STYLE "
                         "(alternate rule, unconfirmed)")
                return MINIHOLLY
        return ok

    # Output path checks
    if args.output is None:
        raise Fail("output file required (or --verify)")
    if same_file(args.output, args.image):
        raise Fail("output must differ from the input file")
    fmt = None
    if args.patch_file:
        fmt = PATCH_FORMATS.get(os.path.splitext(args.patch_file)[1].lower())
        if fmt is None:
            raise Fail("--patch-file must end with .ips or .bps")
        if same_file(args.patch_file, args.image) or same_file(args.patch_file, args.output):
            raise Fail("patch file must differ from the input and output files")
    rep.set(mode="patch", output=args.output, free_area=[h(free_start), h(zone - 1)])
    rep.info(f"free area        = {h(free_start)} .. {h(zone - 1)} (inclusive)")

    # 1. User changes (any offset, relative to the BIOS image)
    writes = [(o, bytes.fromhex(x.replace(' ', ''))) for o, x in args.write]
    writes += [(o, open(path, 'rb').read()) for o, path in args.file]
    if args.set_stored is not None:
        if not 0 <= args.set_stored <= 0xFFFF:
            raise Fail("--set-stored must be a 16-bit value (0x0000 .. 0xFFFF)")
        writes.append((zone, args.set_stored.to_bytes(2, 'little')))
    for o, d in writes:
        if base + o < 0 or base + o + len(d) > len(image):
            raise Fail(f"write at {h(o)} ({h(len(d))} bytes) is outside the file")
        old = bytes(image[base + o:base + o + len(d)])
        image[base + o:base + o + len(d)] = d
        rep.info(f"write @ {fo(o)} : {hexstr(old, PREVIEW)} -> {hexstr(d, PREVIEW)}")
    rep.set(writes=[{"offset": h(o), "length": h(len(d))} for o, d in writes])

    # 2. Target: stored value (last 2 bytes, after the user changes), or with
    #    --reference the final state (checksum and fold) of the reference BIOS
    if naomi:
        target, target_fold = ref_A, ref_fold
    else:
        target = stored_value(bios(), size)
        if args.any_fold:
            target_fold = None
        else:
            folds = allowed_folds(bytes(bios()[size - 2:size]))
            if not folds:
                raise Fail(f"stored value {h4(target)}: no fold makes the fold 0 after the stored "
                           "bytes; choose another --set-stored value (or use --any-fold)")
            target_fold = folds[0] if len(folds) == 1 else None
            rep.info(f"target           = checksum {h4(target)}, fold "
                     + (h4(target_fold) if target_fold is not None else "any")
                     + " at 0x{:X} (fold 0 after the stored bytes)".format(zone))

    # 3-4 (styles). Sega-style patches: position, length and bytes set by the scheme
    style_patch = None
    if args.style == "develop":
        fold_options = [target_fold] if target_fold is not None else [0, FOLD]
        res = develop_style(lambda o: state(image[base:base + o], args.init), zone, target,
                            fold_options, room=args.free_area)
        if res is None:
            raise Fail("no Develop-style patch found")
        offset, style_patch, style_note = res
    elif args.style == "naomi":
        offset = size - NAOMI_LENGTH
        A0, f0 = state(image[base:base + offset], args.init)
        style_patch = naomi_style(A0, f0, target, target_fold)
        if style_patch is None:
            raise Fail("no 6-byte NAOMI-style patch exists for this target (it is the checksum "
                       "before the patch minus 1, same fold: needs 7 bytes); use the default style")
        style_note = "NAOMI scheme: bit 7 on the first bytes for the wrap, rest split evenly"
    if style_patch is not None:
        length = len(style_patch)
        if offset < free_start:
            raise Fail(f"the {args.style}-style patch needs {length} bytes from {h(offset)}, "
                       f"outside the free area [{h(free_start)}, {h(zone - 1)}]: raise "
                       "--free-area")
        for o, d in writes:
            if o < offset + length and offset < o + len(d):
                raise Fail(f"the write at {h(o)} overlaps the patch at {h(offset)}")
        rep.info(f"style            = {args.style} ({style_note})")

    if style_patch is None:
        # 3. Patch position
        at_end = args.offset is None
        if args.length:
            length = args.length
        elif naomi or (at_end and target_fold is not None):
            length = min(MAX_LENGTH, args.free_area)   # shortest that works, up to 8 (see below)
        else:
            length = 3 if at_end else 4
        if not 1 <= length <= MAX_LENGTH:
            raise Fail(f"--length must be between 1 and {MAX_LENGTH}")
        offset = zone - length if at_end else args.offset
        if offset < free_start or offset + length > zone:
            raise Fail(f"patch [{h(offset)}, {h(offset + length - 1)}] is outside the free area "
                       f"[{h(free_start)}, {h(zone - 1)}]")
        for o, d in writes:
            if o < offset + length and offset < o + len(d):
                raise Fail(f"the write at {h(o)} overlaps the patch at {h(offset)}")

        before = checksum(image[base:base + zone], args.init)
        label = "reference" if naomi else "stored"
        rep.set(checksum_before=h4(before), **{label: h4(target)})
        rep.info(f"checksum before  = {h4(before)}, {label} = {h4(target)}")

        # 4. Compute the patch (fewest changed bytes, then closest to padding)
        free = image[base + free_start:base + zone]
        pad = 0x00 if free.count(0x00) > free.count(0xFF) else 0xFF
        old = bytes(image[base + offset:base + offset + length])
        A, fold = state(image[base:base + offset], args.init)
        rest = bytes(image[base + offset + length:base + zone])
        if rest:
            patch = solve_in_middle(A, fold, old, pad, rest, target, target_fold)
        elif (naomi or target_fold is not None) and not args.length:
            # Try every length from 1 to 6, all ending at the last byte. Keep the one that
            # changes the fewest bytes; on a tie, the shortest (closest to the end), which
            # leaves the earlier bytes alone and matches how Sega adjusts its own variants.
            # Only if no 1-6 byte patch exists (target = start - 1, same fold) try 7, then 8.
            patch, best = None, None
            for k in range(1, length + 1):
                if k > NAOMI_LENGTH and patch is not None:
                    break
                Ak, fk = state(image[base + offset:base + zone - k], A, fold)
                p_k = solve_at_end(Ak, fk, old[length - k:], pad, target, target_fold)
                if p_k is None:
                    continue
                cand = old[:length - k] + p_k
                n = sum(x != y for x, y in zip(old, cand))
                if best is None or n < best:
                    patch, best = cand, n
                if best <= 1:                       # 0 or 1 changed byte cannot be beaten
                    break
        else:
            patch = solve_at_end(A, fold, old, pad, target, target_fold)
        if patch is None:
            raise Fail(f"no patch of up to {length} bytes found at {h(offset)}. Omit --offset "
                       "to place the patch at the end of the free area, or raise --length "
                       f"(up to {MAX_LENGTH}).")
    else:
        before = checksum(image[base:base + zone], args.init)
        label = "reference" if naomi else "stored"
        rep.set(checksum_before=h4(before), **{label: h4(target)})
        rep.info(f"checksum before  = {h4(before)}, {label} = {h4(target)}")
        free = image[base + free_start:base + zone]
        pad = 0x00 if free.count(0x00) > free.count(0xFF) else 0xFF
        old = bytes(image[base + offset:base + offset + length])
        patch = style_patch
    changed = sum(a != b for a, b in zip(old, patch))

    # 5. Overwrite protection: changed bytes must be padding unless --force
    # (NAOMI: the last SEGA_TUNE bytes are Sega's own compensation bytes, not data)
    data = [i for i in range(length) if patch[i] != old[i] and old[i] not in PADDING
            and not (naomi and offset + i >= size - SEGA_TUNE)]
    if data:
        msg = (f"the patch overwrites non-padding bytes at "
               f"{', '.join(h(offset + i) for i in data)} ({hexstr(old)})")
        if not args.force:
            raise Fail(msg + ". If this area is free (e.g. a previous patch), use --force.")
        rep.warn(msg + " (--force)")

    image[base + offset:base + offset + length] = patch
    note = " (unchanged)" if changed == 0 else f" ({changed} byte(s) changed)"
    rep.set(patch={"offset": h(offset), "old": hexstr(old), "new": hexstr(patch),
                   "changed_bytes": changed, "padding": f"0x{pad:02X}"})
    rep.info(f"patch @ {fo(offset)} : {hexstr(old)} -> {hexstr(patch)}{note}")

    # 6. Write to a temp file, verify it, then rename (never a half-written output)
    tmp = write_temp(args.output, image)
    try:
        written = open(tmp, 'rb').read()
        if naomi:
            after, f = state(written[base:base + size], args.init)
            ok, stored = (after, f) == (ref_A, ref_fold), ref_A
        else:
            ok, after, stored = holly_check(written[base:base + size], size, args.init)
            if not args.any_fold:
                ok = ok and state(written[base:base + size], args.init)[1] == 0
        if written != image or not ok:
            raise Fail(f"verification of the written file failed "
                       f"(checksum {h4(after)}, {label} {h4(stored)})")
        tmp_patch = None
        if fmt:
            make, apply = fmt
            pdata = make(src, written)
            if apply(src, pdata) != written:
                raise Fail("patch file verification failed")
            tmp_patch = write_temp(args.patch_file, pdata)
        os.replace(tmp, args.output)
        tmp = None
        if tmp_patch:
            os.replace(tmp_patch, args.patch_file)
            rep.set(patch_file={"path": args.patch_file, "size": len(pdata)})
            rep.info(f"patch file       = {args.patch_file} ({len(pdata)} bytes, verified)")
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)

    rep.set(checksum_after=h4(after))
    rep.info(f"checksum after   = {h4(after)}, {label} = {h4(stored)} -> OK")
    return True


# --verify result for an image that only passes the MiniHolly-style rule
MINIHOLLY = "miniholly"
EXIT_MINIHOLLY = 3          # 2 is used by argparse for usage errors


def main():
    args = parse_args()
    rep = Reporter(args.quiet, args.json)
    try:
        ok = run(args, rep)
    except (Fail, OSError, ValueError) as e:
        rep.finish(False, str(e))
        sys.exit(1)
    if ok == MINIHOLLY:
        rep.finish(False)
        sys.exit(EXIT_MINIHOLLY)
    rep.finish(ok)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
