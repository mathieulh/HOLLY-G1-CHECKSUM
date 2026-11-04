# HOLLY G1 Checksum

Patch a Dreamcast BIOS image so its **HOLLY G1 checksum** comes out at `0x0000` (or another
target). You can change bytes anywhere in the image; the script then corrects the checksum by
writing **3 bytes** at the end of a small free area just before the last 2 bytes of the image.

If the parity/checksum does not pass HOLLY's verification the G1 bus (GD ROM on Dreamcast, CART/DIMM on NAOMI)
remains in a locked state, only after the check pass does the G1 bus become unlocked.

- Works on an already modified BIOS, or applies your changes for you (`--write` / `--file`)
- With the default settings, always reaches `0x0000` (checked for every possible checksum state)
- Changes as few bytes as possible
- Refuses to overwrite real data or to write over the input file
- Can also produce an **IPS** or **BPS** patch, so you can share changes without the BIOS

> **NAOMI:** the size and offset of the area HOLLY checks in the NAOMI BIOS are **not known**.
> This tool cannot be used to patch NAOMI BIOSes until those values are known.
> See [BIOS sizes](#bios-sizes).

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
```

The input file is never modified.

### BIOS sizes

`SIZE` must be the size of the area HOLLY checks, not just the file size.

| BIOS | `SIZE` | Status |
|---|---|---|
| Retail Dreamcast BIOS | `0x200000` | Supported |
| NAOMI / Dreamcast **Develop** BIOS | `0x400` | Supported |
| NAOMI BIOS | unknown | **Not supported**: the size and offset of the checked area are not known |

For the NAOMI BIOS, guessing values will produce a file whose checksum is "correct" for the
wrong area, and HOLLY will not accept it. If the values become known, use `SIZE` and `--base`
to point the script at the right area.

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
| `--verify` | | Only check the checksum of the input. Writes nothing. |
| `--write OFF=HEX` | | Write hex bytes at offset `OFF`. Repeatable. Spaces are allowed if the argument is quoted. |
| `--file OFF=PATH` | | Write the contents of a file at offset `OFF`. Repeatable. |
| `--base OFF` | `0x0` | Where the BIOS image starts inside the file. |
| `--free-area N` | `8` | Size of the free area, in bytes, just before the last 2 bytes of the image. |
| `--offset OFF` | end of free area | Place the patch at a specific offset inside the free area. |
| `--length N` | `3` (at end), `4` (with `--offset`) | Patch length, 1 to 6 bytes. Fewer than 3 bytes can fail. |
| `--force` | | Allow the patch to overwrite non-padding bytes, and allow a `SIZE` above `0x200000`. A warning is still printed. |
| `--patch-file PATH` | | Also write an IPS (`.ips`) or BPS (`.bps`) patch from input to output. |
| `--target VALUE` | `0x0000` | Checksum value to reach. |
| `--init VALUE` | `0x0000` | Initial value of the checksum accumulator. |
| `--quiet` | | Print only warnings and errors. |
| `--json` | | Print a single JSON result object (also on errors). |

`--quiet` and `--json` cannot be used together.

### Offsets, size and base

All offsets (`--write`, `--file`, `--offset`, and the messages) are **relative to the start of
the BIOS image**, not the file. When `--base` is not 0, messages also show the file offset.

```
file   |-------------------------------- file size --------------------------------|
image          |<------------------------------ SIZE ----------------------------->|
               ^ --base
               |<------------- checked: first SIZE - 2 bytes ------------->|<-2 B->|
                                                       |<--- free area --->|
                                                                 |<-patch->|
```

- The checksum covers the first `SIZE - 2` bytes of the image. The free area and the patch
  are **inside** that range. The last 2 bytes are not checked and are never touched.
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
| Not checked, never touched | `0x3FE`–`0x3FF` |
| Copied unchanged | `0x400`–`0x1FFFFF` |

### Example output

```
file             = 0x200000 bytes, BIOS image = 0x0 .. 0x3FF (the rest is copied unchanged)
free area        = 0x3F6 .. 0x3FD (inclusive)
write @ 0x10 : F9 C5 E7 20 -> DE AD BE EF
checksum before  = 0xB768
patch @ 0x3FB : FF FF FF -> 03 5B 7B (3 byte(s) changed)
patch file       = out.ips (25 bytes, verified)
checksum after   = 0x0000 -> OK
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
difference between the input and output files: your changes and the checksum patch.

| Format | Notes |
|---|---|
| IPS | Widely supported. Files up to 16 MiB only. |
| BPS | No size limit. Contains CRC32s of the source, target and patch, so it only applies to the right BIOS. |

### Scripting: exit codes and JSON

| Exit code | Meaning |
|---|---|
| `0` | OK: checksum matches the target |
| `1` | Failed or refused: checksum mismatch, safety check, I/O error |
| `2` | Invalid command-line arguments |

```sh
python3 holly_g1_checksum.py dump.bin out.bin 0x400 --base 0x10000 --write 0x5=AA --json
```

Example result (values depend on the input):

```json
{
  "warnings": [],
  "input": "dump.bin",
  "size": "0x400",
  "base": "0x10000",
  "target": "0x0000",
  "mode": "patch",
  "output": "out.bin",
  "free_area": ["0x3F6", "0x3FD"],
  "writes": [{"offset": "0x5", "length": "0x1"}],
  "checksum_before": "0x028C",
  "patch": {
    "offset": "0x3FB",
    "old": "00 00 00",
    "new": "E4 E4 FE",
    "changed_bytes": 3,
    "padding": "0x00"
  },
  "checksum_after": "0x0000",
  "ok": true
}
```

On error, the object contains `"ok": false` and an `"error"` message.

### Changing the defaults

Two constants at the top of the script:

```python
DEFAULT_FREE_AREA = 8         # bytes (64 bits) just before the last 2 bytes
MAX_BIOS_SIZE     = 0x200000  # largest expected BIOS size; above it --force is required
```

---

## Part 2 — How it works

### The HOLLY G1 checksum

The checksum is computed over the first `SIZE - 2` bytes of the image with a 16-bit
accumulator `A` and a "sticky" fold value that is either `0` or `0x1104`.

For each byte `b`:

1. **Spread** the byte to 16 bits: bit *m* moves to bit *2m*.
   `0xFF` becomes `0x5555`, the largest possible value.
2. **Add** `spread(b) XOR fold` to `A`.
3. On **overflow** (`A ≥ 0x10000`), keep the low 16 bits and **toggle** `fold` between
   `0` and `0x1104`.

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
```

A valid image gives `0x0000`. Unmodified retail Dreamcast BIOSes give `0x0000` over
`0x200000` bytes.

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
the default patch is at `SIZE - 5` to `SIZE - 3`, just before the 2 unchecked bytes. Your own
changes can then go anywhere.

### Why 3 bytes

| Patch length at the end | Starting states that can reach `0x0000` |
|---|---|
| 2 bytes | about 7% (random sample of 200 states) |
| **3 bytes** | **131,072 / 131,072 (exhaustive check)** |

Each byte adds one of only 256 values between `0` and `0x5555`, so 2 bytes give too few
combinations to hit an exact 16-bit target from most states. With 3 bytes, every one of the
131,072 states was checked and all of them can reach `0x0000`. This is why the default patch
always succeeds, and why an 8-byte (64-bit) free area is more than enough.

The exhaustive check was done for target `0x0000`. Other `--target` values usually work but
are not guaranteed.

### Finding the patch

**Patch at the end (default).** The first `length - 1` bytes are searched; the last one is
computed directly.

1. Run the checksum up to the patch offset to get the starting state.
2. For each patch byte except the last, extend every current state with all 256 byte values,
   then **merge identical states**. This keeps the search to at most 131,072 states per step,
   whatever the length.
3. For the last byte, solve for it instead of trying all values. To reach target `T`:

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

1. Copy the input in memory, apply `--write` / `--file`, then apply the patch.
2. Write the result to a temporary file in the output directory and flush it to disk (`fsync`).
3. Read the temporary file back and check its content and checksum.
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

The checksum algorithm was worked out from close to **70,000 tests on real hardware**.

The test setup:

- A **NAOMI** with a socket holding a **custom-made EEPROM emulator**.
- The emulator runs a custom **Develop BIOS** with a defined padding area.
- At boot, the BIOS checks the **G1 state** (open or closed) and reports it.
- For each test, the padding area was changed and the NAOMI was reset/rebooted.

Each test took about **7 seconds**, so 70,000 tests add up to roughly **136 hours** (about
5.7 days) of continuous hardware testing. The results of these tests are what made it possible
to reduce the checksum to the algorithm in [Part 2](#part-2--how-it-works).

## Contributors

- [Guimli/Nicolas Weill](https://github.com/Guimli)

* Ran all the tests and designed the custom hardware, worked on the algorithm

- [Mathieulh](https://github.com/Mathieulh)

* Worked on the algorithm, wrote the script, tested across all 131,072 states over 0x200000 bytes
