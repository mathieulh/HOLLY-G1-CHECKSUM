#!/usr/bin/env bash
# Build MiniHolly, the minimal NAOMI BIOS that unlocks G1 with a 0x16-byte checked area.
#
# Usage:
#   ./make_miniholly.sh [SOURCE] [OUTPUT]
#     SOURCE  assembler source   (default: MiniHolly.asm)
#     OUTPUT  raw binary image   (default: miniholly.bin)
#
# Environment:
#   CROSS     toolchain prefix, e.g. sh-elf- or sh4-linux-gnu- (auto-detected if unset)
#   PAD_SIZE  pad the image to this size, e.g. 0x200000 for a 2 MB VROM (default: no padding)
#   PAD_BYTE  padding byte in hex (default: FF, erased flash)
#
# Steps: assemble (SH-4, little-endian) -> link at address 0 -> raw binary -> optional padding
# -> check the HOLLY checksum of the checked area (needs python3).

set -euo pipefail

SRC=${1:-MiniHolly.asm}
OUT=${2:-miniholly.bin}
PAD_SIZE=${PAD_SIZE:-}
PAD_BYTE=${PAD_BYTE:-FF}

# Bytes validated on hardware (HOLLY_KEY.c): the build must produce exactly these first.
EXPECTED="5fe0184074cb1840e4cb15e5522000e802a009e84b6b0900"

die() { echo "error: $*" >&2; exit 1; }

[ -f "$SRC" ] || die "source '$SRC' not found"

# --- toolchain ---------------------------------------------------------------
if [ -z "${CROSS:-}" ]; then
    for p in sh-elf- sh4-elf- sh4-linux-gnu- sh-linux-gnu- sh4-unknown-linux-gnu-; do
        if command -v "${p}as" >/dev/null 2>&1; then CROSS=$p; break; fi
    done
fi
[ -n "${CROSS:-}" ] || die "no SH toolchain found (tried sh-elf-, sh4-elf-, sh4-linux-gnu-, sh-linux-gnu-); set CROSS="
for tool in as ld objcopy; do
    command -v "${CROSS}${tool}" >/dev/null 2>&1 || die "${CROSS}${tool} not found"
done
echo "toolchain : ${CROSS}"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# --- assemble, link at 0, extract raw binary ----------------------------------
"${CROSS}as" -little -o "$TMP/miniholly.o" "$SRC"
"${CROSS}ld" -EL -Ttext=0x0 -e _start -o "$TMP/miniholly.elf" "$TMP/miniholly.o"
"${CROSS}objcopy" -O binary -j .text "$TMP/miniholly.elf" "$TMP/miniholly.raw"

SIZE=$(stat -c %s "$TMP/miniholly.raw")
echo "code size : $SIZE bytes"

# --- compare with the image validated on hardware -----------------------------
GOT=$(od -An -tx1 -v "$TMP/miniholly.raw" | tr -d ' \n')
if [ "${GOT:0:${#EXPECTED}}" = "$EXPECTED" ]; then
    echo "bytes     : identical to HOLLY_KEY.c (validated on NAOMI 2)"
else
    echo "warning   : bytes differ from HOLLY_KEY.c (validated on NAOMI 2)" >&2
    echo "  expected: $EXPECTED" >&2
    echo "  got     : ${GOT:0:${#EXPECTED}}" >&2
fi

# --- optional padding ----------------------------------------------------------
cp "$TMP/miniholly.raw" "$OUT"
if [ -n "$PAD_SIZE" ]; then
    PAD=$(( PAD_SIZE ))
    [ "$PAD" -ge "$SIZE" ] || die "PAD_SIZE ($PAD_SIZE) is smaller than the code ($SIZE bytes)"
    head -c $(( PAD - SIZE )) /dev/zero | tr '\0' "\\$(printf '%03o' $(( 16#$PAD_BYTE )))" >> "$OUT"
    printf 'padded    : to 0x%X bytes with 0x%s\n' "$PAD" "$PAD_BYTE"
fi

# --- HOLLY checksum of the checked area ---------------------------------------
if command -v python3 >/dev/null 2>&1; then
    python3 - "$OUT" <<'PY'
import struct, sys
FOLD = 0x1104
def spread(b):
    b = (b | b << 4) & 0x0F0F
    b = (b | b << 2) & 0x3333
    return (b | b << 1) & 0x5555
d = open(sys.argv[1], 'rb').read()
# key = the immediate loaded into r5 just before the SB_SECUR_EADR write (mov #imm,r5 at 0x0A)
op = struct.unpack_from('<H', d, 0x0A)[0]
if op >> 8 != 0xE5:
    sys.exit("checksum  : could not find 'mov #key,r5' at 0x0A, skipped")
key = op & 0xFF
A = f = 0
for x in d[:key + 1]:
    A += spread(x) ^ f
    if A >= 0x10000:
        A &= 0xFFFF
        f ^= FOLD
ok = (A, f) == (0, FOLD)
print(f"checksum  : area 0x000-0x{key:03X} -> A=0x{A:04X} fold=0x{f:04X} "
      f"({'OK' if ok else 'MISMATCH'}: rule observed with MiniHolly is A=0, fold=0x1104)")
sys.exit(0 if ok else 1)
PY
else
    echo "checksum  : python3 not found, skipped"
fi

echo "output    : $OUT"
