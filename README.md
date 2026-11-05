# HOLLY G1 Checksum

Patch a Dreamcast or NAOMI BIOS image so it passes HOLLY's **G1 checksum check**. You can
change bytes anywhere in the image; the script then corrects the checksum by writing a few
bytes at the end of the image.

At boot, HOLLY computes a checksum over the BIOS. If it doesn't have the expected value, the
G1 bus (GD-ROM on Dreamcast, cartridge/DIMM on NAOMI) stays locked. The bus is only unlocked
once the check passes. What the checksum is compared with depends on the BIOS:

- **Dreamcast retail and Develop BIOSes:** the **stored value** in the last 2 bytes of the image.
- **NAOMI BIOSes:** no stored value. The checksum of the whole image must reach the same final
  value as an unmodified BIOS of the same version (`--reference`).

- Works on an already modified BIOS, or applies your changes for you (`--write` / `--file`)
- With the default settings, always reaches a stored value of `0x0000` (checked for every possible checksum state)
- Can also set a new stored value (`--set-stored`)
- NAOMI BIOSes: patches to the final value of an official BIOS, picked automatically from a
  folder of unmodified dumps (`--reference`)
- Changes as few bytes as possible
- Refuses to overwrite real data or to write over the input file
- Can also produce an **IPS** or **BPS** patch, so you can share changes without the BIOS
- Checked against **68,245 tests on real hardware** (see [Validation on hardware](#validation-on-hardware))

> **NAOMI:** NAOMI support is based on analysis of the official BIOS files and has **not been
> tested on hardware yet**. It needs at least one unmodified BIOS of the same version as the one
> you modify. See [NAOMI BIOSes](#naomi-bioses).

---

## Part 1 — Usage

### Requirements

- Python 3
- [NumPy](https://numpy.org/)

```sh
pip install numpy
```

### Quick start

```sh
# Fix the checksum of a BIOS you have already modified
python3 holly_g1_checksum.py modified.bin fixed.bin 0x200000

# Check a BIOS without writing anything
python3 holly_g1_checksum.py fixed.bin 0x200000 --verify

# Apply changes and fix the checksum in one step
python3 holly_g1_checksum.py bios.bin out.bin 0x200000 --write 0x1000=DEADBEEF --file 0x8000=logo.bin

# Same, and also produce a BPS patch to share
python3 holly_g1_checksum.py bios.bin out.bin 0x200000 --write 0x1000=DEADBEEF --patch-file out.bps

# NAOMI: verify, then patch, picking the reference from a folder of unmodified BIOSes
python3 holly_g1_checksum.py naomi.bin 0x200000 --verify --reference naomi_bioses/
python3 holly_g1_checksum.py modified.bin out.bin 0x200000 --reference naomi_bioses/
```

The input file is never modified.

### BIOS sizes

`SIZE` must be the size of the area HOLLY checks, not just the file size.

| BIOS | `SIZE` | Compared with | Status |
|---|---|---|---|
| Retail Dreamcast BIOS | `0x200000` | Stored value (last 2 bytes) | Supported |
| NAOMI / Dreamcast **Develop** BIOS | `0x400` | Stored value (last 2 bytes) | Supported, validated on hardware |
| NAOMI BIOS | `0x200000` | Final value of a reference BIOS (`--reference`) | Supported, **not tested on hardware** |

A NAOMI BIOS checked without `--reference` always fails, even when unmodified: the script then
looks for a stored value that NAOMI BIOSes don't have.

### Syntax

```
holly_g1_checksum.py IMAGE [OUTPUT] SIZE [options]
```

| Argument | Description |
|---|---|
| `IMAGE` | Input file. Left unchanged. |
| `OUTPUT` | Output file (patched copy). Must be a different file from `IMAGE`. Not needed with `--verify`. |
| `SIZE` | Size of the BIOS image. Can be smaller than the file. |

Numbers can be written in decimal or hex (`1024`, `0x400`).

### Options

| Option | Default | Description |
|---|---|---|
| `--verify` | | Only check the input: checksum must equal the stored value (or the reference's final value with `--reference`). Writes nothing. |
| `--write OFF=HEX` | | Write hex bytes at offset `OFF`. Repeatable. Spaces are allowed if the argument is quoted. |
| `--file OFF=PATH` | | Write the contents of a file at offset `OFF`. Repeatable. |
| `--set-stored VALUE` | | Write a new stored value (16-bit, little-endian) to the last 2 bytes, and patch the checksum to match it. Not available with `--reference`. |
| `--reference REF` | | NAOMI mode. `REF` is an unmodified BIOS of the same version, or a folder of unmodified BIOSes (the closest one is picked). See [NAOMI BIOSes](#naomi-bioses). |
| `--base OFF` | `0x0` | Where the BIOS image starts inside the file. |
| `--free-area N` | `8` | Size of the free area, in bytes, at the end of the checked area. |
| `--offset OFF` | end of free area | Place the patch at a specific offset inside the free area. |
| `--length N` | `3` (at end), `4` (with `--offset` or `--reference`) | Patch length, 1 to 6 bytes. Fewer than 3 bytes can fail. |
| `--force` | | Allow the patch to overwrite non-padding bytes, and allow a `SIZE` above `0x200000`. A warning is still printed. |
| `--patch-file PATH` | | Also write an IPS (`.ips`) or BPS (`.bps`) patch from input to output. |
| `--init VALUE` | `0x0000` | Initial value of the checksum accumulator. |
| `--quiet` | | Print only warnings and errors. |
| `--json` | | Print a single JSON result object (also on errors). |

`--quiet` and `--json` cannot be used together.

### The stored value

The last 2 bytes of the image hold the value HOLLY expects, in little-endian order
(`00 00` = `0x0000`, `34 12` = `0x1234`). The script always patches the checksum to match
the stored value **after** your changes are applied:

- By default the stored value is left as it is. Most BIOSes end in `00 00`, so the target is `0x0000`.
- `--set-stored 0x1234` writes `34 12` to the last 2 bytes and patches the checksum to `0x1234`.
- A `--write` that changes the last 2 bytes also changes the target.

### Offsets, size and base

All offsets (`--write`, `--file`, `--offset`, and the messages) are **relative to the start of
the BIOS image**, not the file. When `--base` is not 0, messages also show the file offset.

```
file   |-------------------------------- file size --------------------------------|
image          |<------------------------------ SIZE ----------------------------->|
               ^ --base
               |<------------- checked: first SIZE - 2 bytes ------------->|stored |
                                                       |<--- free area --->|
                                                                 |<-patch->|
```

- The checksum covers the first `SIZE - 2` bytes of the image. The free area and the patch
  are **inside** that range.
- The last 2 bytes are the stored value. They are not part of the checksum, and the script
  only changes them if you ask it to (`--set-stored` or `--write`).
- The free area is `[SIZE - 2 - free_area, SIZE - 2)`.
- The default patch is the last 3 bytes of the free area: `SIZE - 5` to `SIZE - 3`.
- Everything outside the image is copied to the output unchanged.

Example: a `0x200000` file containing a `0x400` Develop BIOS at offset `0`:

```sh
python3 holly_g1_checksum.py test.bin out.bin 0x400
```

| Item | Range |
|---|---|
| Checked area | `0x000`–`0x3FD` |
| Free area (8 bytes) | `0x3F6`–`0x3FD` |
| Patch (3 bytes) | `0x3FB`–`0x3FD` |
| Stored value | `0x3FE`–`0x3FF` |
| Copied unchanged | `0x400`–`0x1FFFFF` |

### Example output

```
file             = 0x200000 bytes, BIOS image = 0x0 .. 0x3FF (the rest is copied unchanged)
free area        = 0x3F6 .. 0x3FD (inclusive)
write @ 0x10 : 0A 27 FF C9 -> DE AD BE EF
checksum before  = 0x733A, stored = 0x0000
patch @ 0x3FB : FF FF FF -> 54 2C AD (3 byte(s) changed)
patch file       = out.ips (25 bytes, verified)
checksum after   = 0x0000, stored = 0x0000 -> OK
```

Every change is shown as **old bytes → new bytes**. Long writes are shortened to the first
16 bytes. Running the script on a BIOS that already passes reports the patch as `(unchanged)`.

### Safety checks

| Check | Behaviour | Bypass |
|---|---|---|
| `SIZE` above `0x200000` (also with `--verify`) | Refused, probably a typo | `--force` (warning printed) |
| Patch would change bytes other than `0x00` / `0xFF` (NAOMI: except the last 6 bytes) | Refused, offsets listed | `--force` (warning printed) |
| NAOMI: closest reference in the folder differs by more than `0x1000` bytes | Warning only | — |
| `--set-stored` with `--reference` | Refused | none |
| A `--write` / `--file` overlaps the patch | Refused | none |
| Output or patch file is the same file as the input | Refused | none |
| Patch outside the free area | Refused | none |
| Image does not fit in the file (`base + SIZE`) | Refused | none |

> **Re-patching:** once a BIOS has been patched, its patch bytes are no longer padding. If you
> change it again, the new patch will usually need `--force`. If the BIOS already passes, no
> bytes change and `--force` is not needed.

The output is written to a temporary file, read back and checked, and only then renamed to
`OUTPUT`. If anything fails, no output is written and an existing `OUTPUT` is left untouched.

### Patch files (IPS / BPS)

```sh
python3 holly_g1_checksum.py bios.bin out.bin 0x200000 --write 0x10=DEADBEEF --patch-file out.ips
python3 holly_g1_checksum.py bios.bin out.bin 0x200000 --write 0x10=DEADBEEF --patch-file out.bps
```

The format comes from the file extension. Before saving, the script applies the patch to the
input and checks that the result matches the output byte for byte. The patch contains every
difference between the input and output files: your changes, the checksum patch and any
change to the stored value.

| Format | Notes |
|---|---|
| IPS | Widely supported. Files up to 16 MiB only. |
| BPS | No size limit. Contains CRC32s of the source, target and patch, so it only applies to the right BIOS. |

### Scripting: exit codes and JSON

| Exit code | Meaning |
|---|---|
| `0` | OK: checksum matches the stored value (or the reference's final value) |
| `1` | Failed or refused: checksum mismatch, safety check, I/O error |
| `2` | Invalid command-line arguments |

```sh
python3 holly_g1_checksum.py bios.bin out.bin 0x400 --write 0x5=AA --json
```

Example result (values depend on the input):

```json
{
  "warnings": [],
  "input": "bios.bin",
  "size": "0x400",
  "base": "0x0",
  "mode": "patch",
  "output": "out.bin",
  "free_area": ["0x3F6", "0x3FD"],
  "writes": [{"offset": "0x5", "length": "0x1"}],
  "checksum_before": "0x72F6",
  "stored": "0x0000",
  "patch": {
    "offset": "0x3FB",
    "old": "FF FF FF",
    "new": "42 22 A3",
    "changed_bytes": 3,
    "padding": "0xFF"
  },
  "checksum_after": "0x0000",
  "ok": true
}
```

With `--verify`, the object contains `"mode": "verify"`, `"checksum"` and `"stored"`.
With `--reference`, `"stored"` is replaced by `"reference"`, `"fold"`, `"reference_checksum"` and
`"reference_fold"`; when `REF` is a folder, `"reference_distance"` and `"reference_group"` are
added (see [NAOMI BIOSes](#naomi-bioses)).
On error, it contains `"ok": false` and an `"error"` message.

### Validation on hardware

`validate_g1_tests.py` replays a hardware test log against the script's checksum and prints
how well they agree:

```sh
python3 validate_g1_tests.py g1test.bin tests_physiques_G1.txt --size 0x400
```

- The first argument is the base BIOS, as a `.bin` file or as a C array export (`.c`).
- The test log has one test per line, in the format
  `ADR=Llane OLD->NEW [; ADR=Llane OLD->NEW ...] || G1=OUVERT/FERME`
  (`OUVERT` = open, `FERME` = closed).
- For each test, the changes are applied to the base BIOS and the script predicts whether
  G1 opens. The result is a confusion matrix, followed by the mismatches.

The test logs contain Develop BIOS bytes and are **not** included in this repository.
`validate_g1_tests.py` contains no BIOS data.

### NAOMI BIOSes

NAOMI BIOSes don't store the expected value in their last 2 bytes. HOLLY's checksum runs over
all `0x200000` bytes, and every official BIOS of the same version ends on the **same final
value** (checksum and fold). With `--reference`, the script patches a modified BIOS so it ends on
the same final value as an unmodified one.

```sh
# Verify a NAOMI BIOS
python3 holly_g1_checksum.py mybios.bin 0x200000 --verify --reference naomi_bioses/

# Patch a modified NAOMI BIOS
python3 holly_g1_checksum.py modified.bin out.bin 0x200000 --reference naomi_bioses/

# Use one specific reference file instead of a folder
python3 holly_g1_checksum.py modified.bin out.bin 0x200000 --reference epr-21576a.bin
```

In NAOMI mode:

| | Dreamcast (default) | NAOMI (`--reference`) |
|---|---|---|
| Checked area | first `SIZE - 2` bytes | all `SIZE` bytes |
| Target | stored value (last 2 bytes) | final checksum **and** fold of the reference |
| Free area (default 8 bytes) | `SIZE - 10` to `SIZE - 3` | `SIZE - 8` to `SIZE - 1` |
| Default patch | 3 bytes, `SIZE - 5` to `SIZE - 3` | 4 bytes, `SIZE - 4` to `SIZE - 1` |

The last 6 bytes of a NAOMI BIOS are the bytes Sega adjusts to keep each version's final value
(see [NAOMI: no stored value](#naomi-no-stored-value)). The patch may overwrite them without
`--force`.

#### Choosing the reference

`REF` can be a file or a folder:

- **A file** is used as is. The best choice is the exact unmodified dump you started from.
- **A folder** of unmodified official BIOSes: the script compares your BIOS with every file of
  at least `base + SIZE` bytes, and uses the one with the **fewest differing bytes**.

```
reference        = epr-21576a.bin (closest of 20, 0 byte(s) differ)
same final state = epr-21576a.bin, epr-21579.bin, epr-21576b.bin, epr-21577a.bin, epr-21578a.bin
free area        = 0x1FFFF8 .. 0x1FFFFF (inclusive)
write @ 0x4BF68 : 00 -> 03
checksum before  = 0x4A74, reference = 0x4A73
patch @ 0x1FFFFC : EE CA 3F 38 -> EE CA 3E 38 (1 byte(s) changed)
checksum after   = 0x4A73, reference = 0x4A73 -> OK
```

- `reference` is the file picked and how many bytes differ from it.
- `same final state` lists every BIOS in the folder that ends on the same final value. Any of
  them would give the same result.
- If even the closest file differs by more than `0x1000` bytes, a warning says your BIOS is
  probably a version that isn't in the folder.

Rules for the folder:

- **Only unmodified official dumps.** A patched file in the folder would be the closest match to
  itself, and every check against it would pass.
- **After large changes, check the `same final state` line** to make sure the right version was
  picked.
- **Run identification on an unmodified file** when you just want to know which BIOS you have.

#### Final values of the official BIOSes

Checksum over all `0x200000` bytes of each official BIOS. Any BIOS in a group can be used as the
reference for the others in that group:

| Final checksum (fold) | BIOSes |
|---|---|
| `0x4A73` (0) | 21576a, 21576b, 21577a, 21578a, 21579 |
| `0x4653` (0) | 21576e, 21576g, 21577g, 21578e |
| `0xF853` (`0x1104`) | 21576h, 21577h, 21578h |
| `0x4A53` (0) | 21576d, 21578d |
| `0x5B57` (0) | 21576, 21577d |
| `0x14A2` (0) | 21576c |
| `0x8E53` (`0x1104`) | 21577e |
| `0x4843` (0) | 21578f |
| `0x1253` (0) | 21578g |

The file name is **not** a reliable guide. The number (21576 to 21579) is the region variant
and the letter the revision, but `21577d` ends with `21576` rather than with `21576d`/`21578d`,
and `21577e` doesn't end with `21576e`/`21578e`. Let the script pick from a folder, or use the
exact file you started from.

#### Limits

- **Not tested on hardware.** The method reproduces what Sega did in its own BIOSes (see
  [Part 2](#naomi-no-stored-value)), but no NAOMI BIOS patched this way has been booted yet.
- **A clean BIOS of the same version is required.** How HOLLY knows the expected value on NAOMI
  is still unknown, so the script can't target a version you don't have an unmodified copy of.

### Changing the defaults

Constants at the top of the script:

```python
DEFAULT_FREE_AREA = 8         # bytes (64 bits) at the end of the checked area
MAX_BIOS_SIZE     = 0x200000  # largest expected BIOS size; above it --force is required
SEGA_TUNE         = 6         # NAOMI: last bytes Sega adjusts, may be overwritten without --force
FAR_REFERENCE     = 0x1000    # NAOMI: warn if the closest reference differs by more bytes
```

---

## Part 2 — How it works

### The HOLLY G1 check

HOLLY computes a checksum over the first `SIZE - 2` bytes of the image, with a 16-bit
accumulator `A` and a "sticky" fold value that is either `0` or `0x1104`.

For each byte `b`:

1. **Spread** the byte to 16 bits: bit *m* moves to bit *2m*.
   `0xFF` becomes `0x5555`, the largest possible value.
2. **Add** `spread(b) XOR fold` to `A`.
3. On **overflow** (`A ≥ 0x10000`), keep the low 16 bits and **toggle** `fold` between
   `0` and `0x1104`.

G1 is unlocked if and only if the final `A` equals the **stored value**: the last 2 bytes of
the image, little-endian.

```python
FOLD = 0x1104                      # = spread(0x52)

def spread(b):                     # Morton spread, no loop
    b = (b | b << 4) & 0x0F0F
    b = (b | b << 2) & 0x3333
    b = (b | b << 1) & 0x5555
    return b

def checksum(data, A=0):
    fold = 0
    for b in data:
        A += spread(b) ^ fold
        if A >= 0x10000:
            A &= 0xFFFF
            fold ^= FOLD
    return A

def holly_check(image, size):
    stored = image[size - 2] | image[size - 1] << 8
    return checksum(image[:size - 2]) == stored
```

Unmodified retail Dreamcast BIOSes give `0x0000` over `0x200000` bytes.

NAOMI BIOSes use the same algorithm with a different target: see
[NAOMI: no stored value](#naomi-no-stored-value).

### Validation on hardware

The algorithm was checked against **68,245 unique tests** run on real hardware with a
`0x400` Develop BIOS (see [Contribution](#contribution)):

| | Hardware: G1 open | Hardware: G1 closed |
|---|---|---|
| Predicted open | **10,169** | 208 |
| Predicted closed | **0** | **57,868** |

- **Every opening was predicted:** no test opened when the algorithm said it should not.
- **Excluding byte `0xFC`, the agreement is 100%** (67,802 tests).
- **Comparing with the stored value is required.** Two tests opened with a non-zero stored
  value (`0x0001` and `0xB000`), each with a matching checksum. A fixed target of `0x0000`
  would get 275 tests wrong instead of 208.

**The `0xFC` exceptions.** All 208 mismatches change byte `0xFC` of the Develop BIOS, and in
all of them G1 stayed closed although the checksum matched. These are most likely not checksum
failures: `0xFC`–`0xFF` appears to be code that the test BIOS runs, so changing it stops the
BIOS before it can report. This is an interpretation, not a proven fact. It is based on the
following:

- These tests change `0xFC` to a value `x` and the next byte to its complement, which keeps
  the checksum the same. Some values of `x` open and some don't, so the checksum is not what
  decides.
- Bit 0 of `x` never changes the result. Which values open seems to follow how the 16-bit word
  would decode as an SH-4 instruction.
- The result depends only on the 4 bytes at `0xFC`–`0xFF`: tests with the same values there
  never gave different results.

### NAOMI: no stored value

The same checksum, applied to NAOMI BIOSes with the Dreamcast rule (first `0x1FFFFE` bytes
compared with the last 2), fails for every official file. Other places and encodings for a
stored value were tried, and none matched. What the official files show instead:

- **Same version, same final value.** Run over all `0x200000` bytes, the region variants of a
  version all end on the same checksum **and** fold (table in
  [Final values of the official BIOSes](#final-values-of-the-official-bioses)). Different
  versions end on different values.
- **Sega keeps that value on purpose.** The region variants differ by a region byte
  (`00`/`01`/`02`/`03`). When changing it would alter the final value, Sega also changed some of
  the last bytes of the file to bring it back. For example, `21576h` and `21578h` differ by the
  region byte at `0x586E0` and 6 bytes at `0x1FFFFA`–`0x1FFFFF`.
- **This confirms the algorithm.** Those adjustments only work out with exactly this checksum
  (fold `0x1104`, toggled on overflow, over all `0x200000` bytes). With any other rule, the
  region variants would not match each other.
- **It isn't a different starting value.** All 131,072 possible starting states were tried; no
  single one gives a common result for all files.

So in NAOMI mode, the script targets the final state `(A, fold)` of a reference BIOS instead of
a stored value. Matching the fold as well as `A` keeps the result identical to an official BIOS,
whatever HOLLY actually compares.

Checked against Sega's own files, by applying a region change to one BIOS and letting the script
fix it:

| Input + change | Result |
|---|---|
| `21576a` + region `03` | **Identical** to `21579`, byte for byte |
| `21576b` + region `02` | **Identical** to `21578a` |
| `21576d` + region `02` | **Identical** to `21578d` |
| `21576h` + region `02` | Same final value as `21578h`. Sega changed 6 bytes; the script changes 1 |

Several quite different builds share a final value (for example `21576a` and `21576b` differ by
about 194,000 bytes but both end on `0x4A73`). HOLLY may therefore accept a small set of values
rather than one per version. This is speculation; which values HOLLY accepts on NAOMI is unknown.

### The state space

At any point, the checksum is fully described by:

$$
\text{state} = (A,\ \text{fold}) \in [0, 2^{16}) \times \{0,\ \texttt{0x1104}\}
$$

That is **131,072** possible states. The script stores a state as one integer,
`key = A | (fold != 0) << 16`, so NumPy can process all states at once.

Because `0x1104 = spread(0x52)` only has even bits set, XOR with the fold stays inside the
set of spread values:

$$
\text{spread}(b) \oplus \texttt{0x1104} = \text{spread}(b \oplus \texttt{0x52})
$$

So the value added at each step is always the spread of some byte, and a lookup table can
turn it back into that byte.

### Why the patch goes at the end

The step function is **not reversible**: two different states can be sent to the same next
state by the same byte. Once two states merge, they stay merged, so over many bytes the set of
possible states collapses.

Measured on one random 2 MiB image, starting from **all** 131,072 states:

| Bytes processed after the patch | Distinct states left | Can still reach `0x0000`? |
|---|---|---|
| 16 | 87,224 | yes |
| 64 | 42,221 | yes |
| 128 | 26,850 | no |
| 1,024 | 2,380 | no |
| 65,536 | 64 | no |
| ~2 MiB | 4 | no |

A patch placed far from the end of the checked area therefore **cannot** steer the checksum
to an arbitrary value, whatever its content or length: the bytes after it decide the result.
The exact limit depends on the data, roughly 64 to 128 bytes in this test.

The fix is to put the patch **last**, with nothing after it in the checked area. That is why
the default patch is at `SIZE - 5` to `SIZE - 3`, just before the stored value. Your own
changes can then go anywhere.

### Why 3 bytes

| Patch length at the end | Result |
|---|---|
| 2 bytes | `0x0000` reachable from about 7% of starting states (random sample of 200 states) |
| **3 bytes** | **`0x0000` reachable from all 131,072 / 131,072 states (exhaustive check)** |
| **3 bytes** | **all 65,536 values reachable** from each of 150 sampled starting states |

Each byte adds one of only 256 values between `0` and `0x5555`, so 2 bytes give too few
combinations to hit an exact 16-bit value from most states. With 3 bytes, every one of the
131,072 states was checked and all of them can reach `0x0000`. This is why the default patch
always succeeds for a stored value of `0x0000`, and why an 8-byte (64-bit) free area is more
than enough.

For other stored values, the check was done on a sample of starting states rather than all of
them. Every sampled state could reach every value, so other stored values are expected to work,
but this is not proven for every state.

### Finding the patch

The target `T` is the stored value, read after your changes are applied. With `--reference`,
the target is the reference's final state: `A = T` **and** the fold after the last byte must
match the reference's fold.

**Patch at the end (default).** The first `length - 1` bytes are searched; the last one is
computed directly.

1. Run the checksum up to the patch offset to get the starting state.
2. For each patch byte except the last, extend every current state with all 256 byte values,
   then **merge identical states**. This keeps the search to at most 131,072 states per step,
   whatever the length.
3. For the last byte, solve for it instead of trying all values. To reach `T`:

$$
A + (\text{spread}(b) \oplus \text{fold}) = T \quad\text{or}\quad T + \texttt{0x10000}
$$

   The value added must be between `0` and `0x5555`, and `b` comes from an inverse-spread
   lookup table. If no such `b` exists, that state is dropped.

**Patch with data after it** (`--offset` not at the end). All states reachable after the patch
are run through the remaining bytes together, merging as they go and remembering which patch
led to each one. Any final state with `A = T` gives a valid patch. Because of the collapse
described above, this only works close to the end of the checked area; otherwise the script
reports that no patch exists.

### Choosing the best patch

Several patches usually reach the target. Each candidate gets a cost, and the cheapest wins:

| Per patch byte | Cost |
|---|---|
| Different from the original byte | +7 |
| Different from the padding byte | +1 |

The changed-byte weight (7) is larger than the highest possible padding cost (6 bytes), so the
order is strict: **fewest changed bytes first**, then the patch that looks most like the
padding. The padding byte is whichever of `0x00` or `0xFF` is most common in the free area.

When states merge during the search, the cheapest way to reach each state is kept. Costs add up
byte by byte, so the patch chosen is the best one for that position and length. On a BIOS that
already passes, the cheapest patch is to change nothing, which is why re-running the script
reports `(unchanged)`.

### Writing the output safely

1. Copy the input in memory, apply `--write` / `--file` / `--set-stored`, then apply the patch.
2. Write the result to a temporary file in the output directory and flush it to disk (`fsync`).
3. Read the temporary file back and check its content, and that the checksum equals the
   stored value.
   With `--reference`, it checks that the final state matches the reference instead.
4. If requested, build the IPS/BPS patch, apply it to the input in memory and check it gives
   exactly the output.
5. Rename the temporary file(s) to the final name in one step (`os.replace`).

If any step fails, the temporary files are deleted.

### Patch file formats

- **IPS:** `PATCH` header, then records of *3-byte offset, 2-byte length, data*, then `EOF`.
  Runs longer than `0xFFFE` bytes are split. A record at offset `0x454F46` would read as `EOF`,
  so it starts one byte earlier. The 3-byte offset limits IPS to 16 MiB.
- **BPS:** `BPS1` header with variable-length sizes, then *SourceRead* actions (keep the
  original bytes) and *TargetRead* actions (new bytes), then the CRC32 of the source, the
  target and the patch itself.

---

## Contribution

The checksum algorithm was worked out from close to **70,000 tests on real hardware**
(68,245 unique tests after removing duplicates).

The test setup:

- A **NAOMI** with a socket holding a **custom-made EEPROM emulator**.
- The emulator runs a custom **Develop BIOS** with a defined padding area.
- At boot, the BIOS checks the **G1 state** (open or closed) and reports it.
- For each test, the padding area was changed and the NAOMI was reset/rebooted.

Each test took about **7 seconds**, so 70,000 tests add up to roughly **136 hours** (about
5.7 days) of continuous hardware testing. The results of these tests are what made it possible
to reduce the checksum to the algorithm in [Part 2](#part-2--how-it-works), and they are what
the script is [validated against](#validation-on-hardware-1).

<img width="3840" height="2891" alt="s2ohdlx04cxh1" src="https://github.com/user-attachments/assets/834f86ad-20c7-4aa4-b8d9-6b05ffeed8ec" />

## Contributors

- [Guimli/Nicolas Weill](https://github.com/Guimli)
  - Ran all the tests and designed the custom hardware, worked on the algorithm
- [Mathieulh](https://github.com/Mathieulh)
  - Worked on the algorithm, wrote the script, tested across all 131,072 states over 0x200000 bytes
