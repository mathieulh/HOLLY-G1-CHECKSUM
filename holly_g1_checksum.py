#!/usr/bin/env python3
"""HOLLY G1 checksum - patch a Dreamcast BIOS image so HOLLY accepts it.

HOLLY G1 check (validated against 68,245 tests on real hardware):
  - a checksum is computed over the first (size - 2) bytes of the BIOS image
    (spread + addition + sticky XOR + fold pattern toggled 0 <-> 0x1104 on overflow);
  - the result is compared with the STORED value: the last 2 bytes of the image,
    little-endian. G1 opens if and only if they are equal.
  A BIOS whose last 2 bytes are 00 00 therefore needs a checksum of 0x0000.

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

NAOMI BIOS (--reference REF):
  NAOMI BIOSes do NOT store the expected value in their last 2 bytes. The checksum runs
  over all 'size' bytes (0x200000), and every official BIOS of the same version ends in the
  same final state; Sega tunes the last 6 bytes of each region variant to keep it. With
  --reference, the script makes the modified BIOS reach the same final state (checksum
  and fold) as REF, an unmodified BIOS of the same version, by patching its last 4 bytes.
  REF can be a directory of unmodified BIOSes: the one closest to the input (fewest
  differing bytes) is picked automatically.
  Whether HOLLY accepts the result has not been tested on hardware.

Optional patch file (--patch-file): IPS (.ips) or BPS (.bps) patch from the input
to the output, so changes can be shared without distributing the BIOS.

Exit codes: 0 = OK, 1 = failure / refused, 2 = invalid arguments.

Examples:
  holly_g1_checksum.py bios.bin out.bin 0x200000
  holly_g1_checksum.py bios.bin out.bin 0x400 --write 0x10=DEADBEEF
  holly_g1_checksum.py bios.bin out.bin 0x200000 --file 0x8000=logo.bin --patch-file out.bps
  holly_g1_checksum.py dump.bin out.bin 0x400 --base 0x10000 --json
  holly_g1_checksum.py bios.bin 0x400 --verify
  holly_g1_checksum.py naomi.bin 0x200000 --verify --reference naomi_bioses/
"""
import argparse
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
MAX_LENGTH = 6             # max patch length (search cost grows quickly)
SEGA_TUNE = 6              # NAOMI: last bytes Sega tunes to keep the checksum per version


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
    comp = keys * 64 + cost                     # cost < 64 (<= (MAX_LENGTH + 2) * MAX_LENGTH = 48)
    comp_u, idx = np.unique(comp, return_index=True)
    k = comp_u >> 6
    first = np.ones(len(k), dtype=bool)
    first[1:] = k[1:] != k[:-1]
    return idx[first]


def _start(A, fold):
    return (np.array([A | ((fold != 0) << 16)], dtype=np.int64),
            np.zeros(1, dtype=np.int64),
            np.zeros((1, 0), dtype=np.uint8))


def _extend(keys, cost, patches, bcost):
    """Append one free byte to every state; keep the cheapest path to each new state."""
    a = keys & 0xFFFF
    fl = keys >> 16
    n = a[:, None] + (SP[None, :] ^ np.where(fl, FOLD, 0)[:, None])
    nk = ((n & 0xFFFF) | ((fl[:, None] ^ (n >= 0x10000)) << 16)).ravel()
    nc = (cost[:, None] + bcost[None, :]).ravel()
    sel = _dedup_min(nk, nc)
    parent = sel // 256
    val = (sel % 256).astype(np.uint8)
    return nk[sel], nc[sel], np.hstack([patches[parent], val[:, None]])


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
    p.add_argument("size", type=integer, help="BIOS image size (decimal or 0x..)")
    p.add_argument("--base", type=integer, default=0,
                   help="start of the BIOS image in the file (default 0x0)")
    p.add_argument("--verify", action="store_true",
                   help="only check the input (checksum == stored value), write nothing "
                        "(exit code 0 = OK, 1 = FAIL)")
    p.add_argument("--set-stored", type=integer, metavar="VALUE",
                   help="write a new stored value (16-bit, little-endian) to the last 2 bytes "
                        "and patch the checksum to match it")
    p.add_argument("--free-area", type=integer, default=DEFAULT_FREE_AREA,
                   help="free area size, just before the last 2 bytes: "
                        f"[size - 2 - free_area, size - 2) (default {DEFAULT_FREE_AREA})")
    p.add_argument("--offset", type=integer,
                   help="patch offset inside the free area (default: end of free area)")
    p.add_argument("--length", type=int,
                   help=f"patch length in bytes, 1..{MAX_LENGTH} "
                        "(default 3 at end of area, 4 otherwise)")
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
                   help="NAOMI mode: checksum ALL 'size' bytes (no stored value) and match the "
                        "final checksum state of REF, an unmodified BIOS of the same version. "
                        "REF can be a file, or a DIRECTORY of unmodified BIOSes: the closest "
                        "one (fewest differing bytes) is then picked automatically")
    p.add_argument("--init", type=integer, default=0, help="initial state A (default 0)")
    out = p.add_mutually_exclusive_group()
    out.add_argument("--quiet", action="store_true", help="print only warnings and errors")
    out.add_argument("--json", action="store_true", help="print a single JSON result object")
    return p.parse_args()


def run(args, rep):
    src = open(args.image, 'rb').read()
    image = bytearray(src)
    base, size = args.base, args.size
    if base < 0 or not 2 < size or base + size > len(image):
        raise Fail(f"BIOS image [{h(base)}, {h(base + size)}) does not fit in the file "
                   f"({h(len(image))} bytes)")
    if size > MAX_BIOS_SIZE:
        msg = f"BIOS size {h(size)} exceeds the maximum of {h(MAX_BIOS_SIZE)}"
        if not args.force:
            raise Fail(msg + ". Check the size argument, or use --force to bypass the limit.")
        rep.warn(msg + " (--force)")
    naomi = args.reference is not None
    if naomi and args.set_stored is not None:
        raise Fail("--set-stored cannot be used with --reference (no stored value)")
    # checked area: [0, zone) relative to base. Retail/Develop: size - 2 (stored value
    # follows). NAOMI (--reference): the whole image, compared with the reference state.
    zone = size if naomi else size - 2
    free_start = zone - args.free_area
    if naomi:
        ref_path, ref_A, ref_fold = find_reference(args.reference, image[base:base + size],
                                                   base, size, args.init, rep)
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
        if naomi:
            c, f = state(bios(), args.init)
            ok = (c, f) == (ref_A, ref_fold)
            rep.set(mode="verify", checksum=h4(c), fold=h4(f), reference=ref_path,
                    reference_checksum=h4(ref_A), reference_fold=h4(ref_fold))
            rep.info(f"checksum         = {h4(c)} (fold {h4(f)}), reference = {h4(ref_A)} "
                     f"(fold {h4(ref_fold)}) -> {'OK' if ok else 'FAIL'}")
            return ok
        ok, c, s = holly_check(bios(), size, args.init)
        rep.set(mode="verify", checksum=h4(c), stored=h4(s))
        rep.info(f"checksum         = {h4(c)}, stored = {h4(s)} -> {'OK' if ok else 'FAIL'}")
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
        target, target_fold = stored_value(bios(), size), None

    # 3. Patch position
    at_end = args.offset is None
    length = args.length or (4 if naomi or not at_end else 3)
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
    else:
        patch = solve_at_end(A, fold, old, pad, target, target_fold)
    if patch is None:
        raise Fail(f"no patch found at {h(offset)}. Omit --offset to place the patch "
                   "at the end of the free area.")
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


def main():
    args = parse_args()
    rep = Reporter(args.quiet, args.json)
    try:
        ok = run(args, rep)
    except (Fail, OSError, ValueError) as e:
        rep.finish(False, str(e))
        sys.exit(1)
    rep.finish(ok)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
