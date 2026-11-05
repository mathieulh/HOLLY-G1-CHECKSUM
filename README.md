# HOLLY G1 Checksum

Patch a Dreamcast BIOS image so it passes HOLLY's **G1 checksum check**. You can change bytes
anywhere in the image; the script then corrects the checksum by writing **3 bytes** at the end
of a small free area just before the last 2 bytes of the image.

At boot, the BIOS writes the last address of the area to check to the `SB_SECUR_EADR`
register, and HOLLY sums every byte read from the BIOS up to that address. On Dreamcast BIOSes
the result is compared with the **stored value** in the last 2 bytes of the image. If they
don't match, the G1 bus (GD-ROM on Dreamcast, cartridge/DIMM on NAOMI and Atomiswave) stays
locked. The bus is only unlocked once the check passes.

- Works on an already modified BIOS, or applies your changes for you (`--write` / `--file`)
- With the default settings, always reaches a stored value of `0x0000` (checked for every possible checksum state)
- Can also set a new stored value (`--set-stored`)
- Changes as few bytes as possible
- Refuses to overwrite real data or to write over the input file
- Can also produce an **IPS** or **BPS** patch, so you can share changes without the BIOS
- Checked against **68,245 tests on real hardware** (see [Validation on hardware](#validation-on-hardware))
- Reads the checked size from the BIOS's own boot code (`SIZE` = `auto`)

> [!WARNING]
> **Only Dreamcast BIOSes (retail and Develop) are fully supported.**
> - **NAOMI / NAOMI 2:** experimental (`--reference`). The checked size is known (`0x200000`),
>   but official NAOMI BIOSes do **not** follow the stored-value rule, and the exact rule is
>   unknown. Patched files have **not** been tested on hardware.
> - **Atomiswave:** not supported. The checked size is known, but the rule is unknown;
>   a patched file is unlikely to pass.
>
> See [Platform support](#platform-support).

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

# Let the script read the checked size from the boot code
python3 holly_g1_checksum.py bios.bin auto --verify

# NAOMI (experimental): verify against a folder of unmodified official BIOSes
python3 holly_g1_checksum.py naomi.bin auto --verify --reference naomi_bioses/
```

The input file is never modified.

### BIOS sizes

`SIZE` must be the size of the area HOLLY checks, not just the file size. Use `auto` to read it
from the BIOS itself (see [Automatic size detection](#automatic-size-detection)).

| BIOS | `SIZE` (`auto` finds) | Status |
|---|---|---|
| Retail Dreamcast BIOS (`mpr-*`, `dc_boot`, `set5*`) | `0x200000` | **Supported** |
| NAOMI / Dreamcast **Develop** BIOS | `0x400` | **Supported**, validated on NAOMI hardware, also works on Dreamcast |
| NAOMI / NAOMI 2 BIOS (`epr-215xx`, `epr-236xx`, `epr-21336a`) | `0x200000` | **Experimental**, with `--reference` only |
| Atomiswave BIOS (`bios0`, `bios1`) | `0xA678` | **Not supported**: rule unknown |
| Atomiswave `fpr-24363` (BIOS at `0x60000`) | `0xA674` (with `--base 0x60000`) | **Not supported**: rule unknown |

### Platform support

| Platform | Size known | Rule known | What the script does |
|---|---|---|---|
| Dreamcast retail | Yes | **Yes**: checksum of the first `SIZE - 2` bytes = stored value | Verify and patch |
| Dreamcast / NAOMI Develop | Yes | **Yes**, validated by 68,245 hardware tests | Verify and patch |
| NAOMI / NAOMI 2 | Yes | **No** | `--reference` mode, experimental, warning printed |
| Atomiswave | Yes | **No** | `auto` finds the size; a warning says the rule doesn't hold |

What "rule unknown" means: on official NAOMI, NAOMI 2 and Atomiswave BIOSes, the checksum
computed by this script does **not** equal the stored value, and no starting value, byte order
or fold constant makes it do so (see [NAOMI and Atomiswave: open questions](#naomi-and-atomiswave-open-questions)).
These BIOSes boot, so HOLLY checks them some other way.

### Syntax

```
holly_g1_checksum.py IMAGE [OUTPUT] SIZE [options]
```

| Argument | Description |
|---|---|
| `IMAGE` | Input file. Left unchanged. |
| `OUTPUT` | Output file (patched copy). Must be a different file from `IMAGE`. Not needed with `--verify`. |
| `SIZE` | Checked size of the BIOS image, or `auto` to read it from the boot code. Can be smaller than the file. |

Numbers can be written in decimal or hex (`1024`, `0x400`).

### Options

| Option | Default | Description |
|---|---|---|
| `--verify` | | Only check the input: checksum must equal the stored value. Writes nothing. |
| `--write OFF=HEX` | | Write hex bytes at offset `OFF`. Repeatable. Spaces are allowed if the argument is quoted. |
| `--file OFF=PATH` | | Write the contents of a file at offset `OFF`. Repeatable. |
| `--set-stored VALUE` | | Write a new stored value (16-bit, little-endian) to the last 2 bytes, and patch the checksum to match it. Not available with `--reference`. |
| `--reference REF` | | **Experimental** NAOMI mode. `REF` is an unmodified official BIOS, or a folder of them (the closest one is picked). See [NAOMI and NAOMI 2 (experimental)](#naomi-and-naomi-2-experimental). |
| `--base OFF` | `0x0` | Where the BIOS image starts inside the file. |
| `--free-area N` | `8` | Size of the free area, in bytes, just before the last 2 bytes of the image. |
| `--offset OFF` | end of free area | Place the patch at a specific offset inside the free area. |
| `--length N` | `3` (at end), `4` (with `--offset`), `6` (with `--reference`) | Patch length, 1 to 6 bytes. Fewer than 3 bytes can fail. |
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

### Automatic size detection

Every HOLLY/CLX2 BIOS writes the last address of the area to check to the `SB_SECUR_EADR`
register (`0x005F74E4`) before reading it. With `SIZE` = `auto`, the script finds that write in
the boot code and uses **value + 1** as the size.

```sh
python3 holly_g1_checksum.py bios.bin auto --verify
python3 holly_g1_checksum.py fpr-24363.ic48 auto --base 0x60000 --verify
```

```
SB_SECUR_EADR    = 0x3FF written at 0xAC0000E8 (RAM loader built by the boot code at AC0000E4)
size (auto)      = 0x400
checksum         = 0x0000, stored = 0x0000 -> OK
```

The script decodes the SH-4 boot code (constants, shifts, `GBR`-relative stores) and also
follows the three ways BIOSes hide the write:

| BIOS | Where the write is | `SB_SECUR_EADR` |
|---|---|---|
| Dreamcast retail, set5 v0.972 and later | Boot code (around `0x34E`) and hidden loader at `0xE0` | `0x1FFFFF` |
| set5 v0.41 / v0.71 | Hidden loader at `0xE0`, stored with its **longwords** reversed | `0x1FFFFF` |
| NAOMI, NAOMI 2, NAOMI Develop `21336a` | Hidden loader at `0xE0`, stored with its **halfwords** reversed | `0x1FFFFF` |
| Dreamcast / NAOMI Develop (`0x400`) | Loader the boot code builds in RAM at `0xAC0000E4` | `0x3FF` |
| Atomiswave `bios0` / `bios1` | Boot code at `0x26` | `0xA677` |
| Atomiswave `fpr-24363` | Boot code at `0x26` (relative to `--base 0x60000`) | `0xA673` |

All 50 BIOSes tested give a single, consistent value. If no write is found, or two writes give
different values, the script stops and asks for `SIZE`. Writes of `0` and `0x42FE` (used to
re-arm the check, e.g. before Mil-CD) are ignored. For a size other than `0x400` or
`0x200000`, a warning is printed, because the stored-value rule is not known to hold there.

`--json` adds `"eadr"` (the value) and `"eadr_sites"` (where each write was found).

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
| Patch would change bytes other than `0x00` / `0xFF` | Refused, offsets listed | `--force` (warning printed) |
| A `--write` / `--file` overlaps the patch | Refused | none |
| Output or patch file is the same file as the input | Refused | none |
| Patch outside the free area | Refused | none |
| Image does not fit in the file (`base + SIZE`) | Refused | none |
| `SIZE` = `auto` and no (or conflicting) `SB_SECUR_EADR` write found | Refused | give `SIZE` |
| `SIZE` = `auto` finds a size other than `0x400` / `0x200000` (Atomiswave) | Warning only | — |
| `--reference` used (NAOMI) | Warning: experimental, not validated on hardware | — |
| NAOMI: closest reference in the folder differs by more than `0x1000` bytes | Warning only | — |
| `--set-stored` with `--reference` | Refused | none |

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
| `0` | OK: checksum matches the stored value |
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
With `SIZE` = `auto`, it also contains `"eadr"` and `"eadr_sites"`. With `--reference`,
`"stored"` is replaced by `"reference"`, `"fold"`, `"reference_checksum"` and `"reference_fold"`
(plus `"reference_distance"` and `"reference_group"` when `REF` is a folder).
On error, it contains `"ok": false` and an `"error"` message.

### Validation on hardware

`validate_g1_tests.py` replays a hardware test log against the script's checksum and prints
how well they agree:

```sh
python3 validate_g1_tests.py g1test.bin tests_physiques_G1.txt --size 0x400
python3 validate_g1_tests.py g1test.bin hardware_tests_G1.txt --size 0x400
```

- The first argument is the base BIOS, as a `.bin` file or as a C array export (`.c`).
- The second is the test log, in **French or English**. The language is detected on each line,
  so a log can mix both. One test per line:

  | Language | Format |
  |---|---|
  | French | `ADR=Llane OLD->NEW [; ADR=Llane OLD->NEW ...] \|\| G1=OUVERT` or `G1=FERME` |
  | English | `ADR=Llane OLD->NEW [; ADR=Llane OLD->NEW ...] \|\| G1=OPEN` or `G1=CLOSED` |

  Results are read without regard to case or accents (`FERMÉ` = `FERME`), and `OUVERTE`,
  `FERMEE`, `OPENED` and `CLOSE` are also accepted. Lines starting with `#` and blank lines are
  ignored. Results marked `ERR`, `ERREUR` or `ERROR` are skipped and counted. Any other result
  stops the script with the line number.
- For each test, the changes are applied to the base BIOS and the script predicts whether
  G1 opens. The result is a confusion matrix, followed by the mismatches:

```
base image     : 0x200000 bytes, size checked 0x400
tests          : 68245 (original byte mismatches: 0)
log language   : French (OUVERT/FERME) 68245
base checksum  : 0x0000, stored 0x0000 -> OK

                    hardware OPEN   hardware CLOSED
predicted OPEN              10169               208
predicted CLOSED                0             57868
agreement          : 99.695 %
```

- `original byte mismatches` counts the changes whose `OLD` byte doesn't match the base BIOS.
  It should be `0`; anything else means the log was recorded on a different BIOS.
- Options: `--size` (checked size, default `0x400`) and `--show N` (number of mismatches to
  list, default 20).

The test logs contain Develop BIOS bytes and are **not** included in this repository.
`validate_g1_tests.py` contains no BIOS data.

### NAOMI and NAOMI 2 (experimental)

> [!WARNING]
> The NAOMI rule is **not known**, and no NAOMI BIOS patched this way has been booted yet.
> Use it for experiments only, and keep the original BIOS.

Official NAOMI BIOSes don't match the stored-value rule. What they do show is that Sega adjusts
the **last 6 bytes** of each region variant, so those bytes feed the check. `--reference`
assumes that acceptance depends only on the final checksum state over all `0x200000` bytes, and
patches the last 6 bytes so a modified BIOS ends on the same state as an unmodified official one.

```sh
python3 holly_g1_checksum.py mybios.bin auto --verify --reference naomi_bioses/
python3 holly_g1_checksum.py modified.bin out.bin auto --reference naomi_bioses/
python3 holly_g1_checksum.py modified.bin out.bin auto --reference epr-21576a.ic27
```

| | Dreamcast (default) | NAOMI (`--reference`) |
|---|---|---|
| Checked area | first `SIZE - 2` bytes | all `SIZE` bytes |
| Target | stored value (last 2 bytes) | final checksum **and** fold of the reference |
| Default patch | 3 bytes, `SIZE - 5` to `SIZE - 3` | up to 6 bytes, `SIZE - 6` to `SIZE - 1` |

- **6 bytes, not 4:** matching the fold as well as the checksum needs 6 bytes. 4 bytes reach only
  87,381 of the 131,072 possible states; 6 bytes reach 131,071. Sega also uses exactly 6.
  The script tries 1 to 6 bytes and keeps the patch that changes the fewest.
- **Reproduces Sega's own files:** `21576a` + region `03` gives `21579` byte for byte; `21576b`
  and `21576d` + region `02` give `21578a` and `21578d`.
- **Choosing the reference:** a file is used as is; for a folder, the script picks the file with
  the fewest differing bytes and lists the others ending on the same state. Keep **only
  unmodified official dumps** in the folder.
- **Why it's experimental:** the 34 official NAOMI / NAOMI 2 BIOSes end on 17 different final
  values, and region variants of one build don't always share a value (see
  [NAOMI and Atomiswave: open questions](#naomi-and-atomiswave-open-questions)). So reaching a
  reference's final value may not be what HOLLY actually requires.

### Atomiswave (not supported)

`auto` finds the checked size (`0xA678` for `bios0` / `bios1`, `0xA674` for `fpr-24363` with
`--base 0x60000`), but official Atomiswave BIOSes don't follow the stored-value rule either.
The script prints a warning; don't rely on a patched Atomiswave BIOS.

### Changing the defaults

Constants at the top of the script:

```python
DEFAULT_FREE_AREA = 8         # bytes (64 bits) just before the last 2 bytes
MAX_BIOS_SIZE     = 0x200000  # largest expected BIOS size; above it --force is required
SEGA_TUNE         = 6         # NAOMI: last bytes Sega adjusts, may be overwritten without --force
NAOMI_LENGTH      = 6         # NAOMI: default patch length with --reference
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

### Where the size comes from: `SB_SECUR_EADR`

As described in MAME (`dccons_m.cpp`), after reset HOLLY's security state machine is in
"check in progress": G1 is locked, and every byte read over the G1 bus is summed. A write to
`SB_SECUR_EADR` sets the last address of the checked area; when that address is read, the sum is
compared and the state becomes "OK" (G1 unlocked) or "fail" (locked until reset).

The Dreamcast boot code arms the check with `0x1FFFFF` and then reads all of `0x0`–`0x1FFFFF`
in order, directly (uncached). That is exactly what this script computes, which is why
Dreamcast BIOSes validate. The Develop BIOS does the same with `0x3FF` over `0x400` bytes.

### Validation on hardware

The algorithm was checked against **68,245 unique tests** run on real **NAOMI** hardware with a
`0x400` Develop BIOS (see [Contribution](#contribution)). The same Develop BIOS also works on
Dreamcast:

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

### NAOMI and Atomiswave: open questions

NAOMI, NAOMI 2 and Atomiswave BIOSes use the same register and the same kind of sizes, but
the rule above does not explain them. What was checked, on 34 NAOMI / NAOMI 2 and 3
Atomiswave dumps:

- **Read order:** after arming the check, the NAOMI loader (run from RAM) copies `0x100`–`0x1FFFFF`
  in one pass, and Atomiswave reads `0x80` up to its end address. Testing **all 131,072**
  starting states at that point, no state makes the checksum equal the last word, for NAOMI
  or Atomiswave. This covers anything read before that point.
- **Other byte orders** (16-bit swap, 32-bit reverse, half swap) and code fetches mixed into
  the reads: no match. The same changes break Dreamcast.
- **Other fold constants** (all 256 spread values): only `0x1104` works, and only for Dreamcast.
- **Plain sums, XOR, CRC32:** no match.
- **Final values:** the 34 NAOMI / NAOMI 2 BIOSes end on 17 different checksum values over
  `0x200000` bytes. Region variants share the value in about half of the cases.
- **Layout:** retail NAOMI BIOSes end with a fixed `0x200`-byte block at `0x1FFE00`, followed by
  Sega's 6 adjusted bytes. The NAOMI Develop BIOS `21336a` has neither and still boots.

So on these boards either the comparison works differently, or HOLLY's internal "hardcoded
value" is not fixed. Only hardware tests can tell; see [Contribution](#contribution).

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

The target `T` is the stored value, read after your changes are applied.

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
