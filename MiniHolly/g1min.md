A minimal NAOMI BIOS that unlocks the G1 bus without RAM and without any CPU init. Holly
checks only the first 22 bytes (offsets 0x000 to 0x015). This document covers four things:

1. what those 22 bytes are, as SH-4 instructions, in hexadecimal and binary;
2. how the SH-4 fetches them
3. the checksum Holly computes over them
4. that checksum computed by hand, one byte at a time, as column additions with the carries
   written on top.

## 1. Result on real hardware

Tested on a NAOMI 2
```
EC=00000003 E4=00000059 7C=FFFE      (0x5F74EC = 3 → G1 OPEN, every report line)
```

## 2. Memory layout of the checked zone

The key written to `0x5F74E4` is also the size of the checked zone: **0x15** means that bytes
0x000..0x015 (22 bytes) are checked.

The SH-4 runs little-endian, so each 16-bit instruction is stored low byte first. The bytes
`5F E0` at 0x00 therefore form the opcode `0xE05F`.

| Offset | ROM bytes | Opcode | Instruction | Role |
|---|---|---|---|---|
| 0x00 | `5F E0` | `E05F` | `mov #0x5F,r0` | r0 = 0x0000005F |
| 0x02 | `18 40` | `4018` | `shll8 r0` | r0 = 0x00005F00 |
| 0x04 | `74 CB` | `CB74` | `or #0x74,r0` | r0 = 0x00005F74 |
| 0x06 | `18 40` | `4018` | `shll8 r0` | r0 = 0x005F7400 |
| 0x08 | `E4 CB` | `CBE4` | `or #0xE4,r0` | r0 = **0x005F74E4** |
| 0x0A | `15 E5` | `E515` | `mov #0x15,r5` | r5 = 0x15 (key = zone size) |
| 0x0C | `52 20` | `2052` | `mov.l r5,@r0` | **key write** |
| 0x0E | `00 E8` | `E800` | `mov #0,r8` | compensation (free immediate) |
| 0x10 | `02 A0` | `A002` | `bra 0x18` | 0x10 + 4 + 2×2 = 0x18 |
| 0x12 | `09 E8` | `E809` | `mov #9,r8` | delay slot, compensation |
| 0x14 | `4B 6B` | (`6B4B`) | never executed | compensation |
| 0x16 | `09 00` | `0009` | `nop` | only for keep prefetched, never executed |

Notes:
- `mov #imm` sign-extends the 8-bit immediate. 0x5F and 0x15 are positive, so nothing changes.
  `or #imm,r0` zero-extends.
- `0x005F74E4` is a **P0** address. At reset the MMU is off and the cache is disabled, so P0
  goes straight to the physical address: the store reaches Holly's G1 lock register uncached.
  No `0xA0…` (P2) constant is needed, so there is no literal pool and the code needs no
  memory read of its own.
- r8 is never used. `mov #0,r8` and `mov #9,r8` only provide two free bytes (0x0E and 0x12)
  that change the checksum without changing what the code does.
- 0x14/0x15 sit after the branch and its delay slot, so they are never executed. They are
  plain data, chosen to bring the checksum to its final value.

## 3. How the SH-4 fetches the zone

At reset, the CPU fetches instructions from the boot ROM in **32-bit words**. The ROM is in
byte mode here, so each word becomes 4 byte reads:

- 840 ns between two bytes of the same word;
- 1360 ns between the last byte of a word and the first byte of the next one;
- **1560 ns** (+200 ns) where a bus write slips in between two word fetches.

```
word      bytes read            gap before first byte   meaning
0x00-03   5F E0 18 40              —                     mov #95 / shll8
0x04-07   74 CB 18 40           1360 ns                  or #116 / shll8
0x08-0B   E4 CB 15 E5           1360 ns                  or #228 / mov #21,r5
0x0C-0F   52 20 00 E8           1360 ns                  mov.l r5,@r0 / mov #0,r8
0x10-13   02 A0 09 E8           1360 ns                  bra 0x18 / slot mov #9,r8
          ── key write to 0x5F74E4 goes out here (+200 ns) ──
0x14-17   4B 6B 09 00           1560 ns                  compensation + nop (prefetched)
0x18-1B   09 00 09 00           1360 ns                  branch target, aligned
0x1C-1F   09 00 09 00           1360 ns                  …strictly linear onward
```

What the trace shows:

1. **The fetch runs one word ahead of execution.** The `mov.l` is in word 0x0C-0x0F, but its
   write appears on the bus only after word 0x10-0x13 has been fetched. The prefetcher has
   already requested the next word by the time the store executes.
2. **Holly must still see reads inside the zone after the key arrives.** Here, bytes 0x14 and
   0x15 are read after the key write. With key 0x13, the whole zone (0x00-0x13) had already
   been read before the key arrived: Holly never finished (EC=0). That is why 0x15 is the
   smallest key that works with a 14-byte key sequence.
3. **The checksum still covers the bytes read before the key**, starting at the first fetch
   after reset. The sum below therefore starts at offset 0x00.
4. **The branch target is aligned on 4.** `bra 0x18` and its delay slot are both in word
   0x10-0x13. Word 0x14-0x17 is prefetched before the branch takes effect. The CPU then fetches
   0x18-0x1B, the next word in sequence, so nothing is fetched twice. Compare
   `g1min_k015.bin` (`bra 0x16`): 0x16 is not 4-aligned, so the CPU fetches word 0x14-0x17
   a second time and Holly sees the compensation bytes twice. That image opens too, but
   its bus stream is not linear.

## 4. The checksum (with the sticky carry)

Holly keeps a 16-bit accumulator **A** and a 16-bit **sticky carry** pattern **fold**. Both
start at 0. For every byte `b` read in the zone:

```
spread(b) = b with bit m moved to bit 2m      (8 bits → 16 bits, odd bits = 0)
term      = spread(b) XOR fold
A         = A + term
if A ≥ 0x10000:                               (carry out of bit 15)
    A    = A AND 0xFFFF                       the carry is NOT added back
    fold = fold XOR 0x1104                    it toggles the sticky carry instead
```

- **Spread.** `b7 b6 b5 b4 b3 b2 b1 b0` becomes `0b7 0b6 0b5 0b4 0b3 0b2 0b1 0b0`. The largest
  possible term is spread(0xFF) = 0x5555.
- **Sticky carry.** A carry out of the top bit is not lost, and it is not added back into
  A (an end-around carry). It toggles a pattern, 0x1104 = spread(0x52), and that pattern
  stays and is XORed into **every following term** until the next carry out toggles it back.
  The carry "sticks" to all the bytes that come after it, so only the parity of the number of
  overflows matters.
- **Rule observed on g1min (zone 0x15):** the image opens when A = 0 over the whole zone,
  bytes 0x14/0x15 included, with a final fold of 0x1104. The same image with a final fold of 0
  stays closed. This rule comes from bench results; it is not a documented specification.
  On the `develop` header, the rule is A == S instead, with S stored in the last 2 bytes.

A neat detail at offset 0x0C: the opcode byte `0x52` of `mov.l r5,@r0` spreads to exactly
0x1104. The sticky carry is active at that point, so term = 0x1104 XOR 0x1104 = 0 and that
byte adds nothing.

### Summary of the 22 steps

| Offset | Byte | spread | term (spread fold) | A after | carry out | fold after |
|---|---|---|---|---|---|---|
| 0x00 | `5F` | `1155` | `1155` | `1155` |  | `0000` |
| 0x01 | `E0` | `5400` | `5400` | `6555` |  | `0000` |
| 0x02 | `18` | `0140` | `0140` | `6695` |  | `0000` |
| 0x03 | `40` | `1000` | `1000` | `7695` |  | `0000` |
| 0x04 | `74` | `1510` | `1510` | `8BA5` |  | `0000` |
| 0x05 | `CB` | `5045` | `5045` | `DBEA` |  | `0000` |
| 0x06 | `18` | `0140` | `0140` | `DD2A` |  | `0000` |
| 0x07 | `40` | `1000` | `1000` | `ED2A` |  | `0000` |
| 0x08 | `E4` | `5410` | `5410` | `413A` | yes | `1104` |
| 0x09 | `CB` | `5045` | `4141` | `827B` |  | `1104` |
| 0x0A | `15` | `0111` | `1015` | `9290` |  | `1104` |
| 0x0B | `E5` | `5411` | `4515` | `D7A5` |  | `1104` |
| 0x0C | `52` | `1104` | `0000` | `D7A5` |  | `1104` |
| 0x0D | `20` | `0400` | `1504` | `ECA9` |  | `1104` |
| 0x0E | `00` | `0000` | `1104` | `FDAD` |  | `1104` |
| 0x0F | `E8` | `5440` | `4544` | `42F1` | no | `0000` |
| 0x10 | `02` | `0004` | `0004` | `42F5` |  | `0000` |
| 0x11 | `A0` | `4400` | `4400` | `86F5` |  | `0000` |
| 0x12 | `09` | `0041` | `0041` | `8736` |  | `0000` |
| 0x13 | `E8` | `5440` | `5440` | `DB76` |  | `0000` |
| 0x14 | `4B` | `1045` | `1045` | `EBBB` |  | `0000` |
| 0x15 | `6B` | `1445` | `1445` | `0000` | yes | `1104` |

Three carries out of bit 15, at 0x08, 0x0F and 0x15. That is an odd number, so the sticky
carry ends active (0x1104), and the last one lands exactly on 0x10000, leaving A = 0x0000.

## 5. Step-by-step column additions

Each step shows how the byte is spread, how the sticky carry is applied (XOR) when it is
active, and the addition A + term posed in columns, first in hexadecimal and then in binary.
Carries are written above the column they go into. The leftmost carry is the carry out of
bit 15, the one that toggles the sticky carry.

### Step  1 — offset 0x00, byte 0x5F (mov #95,r0 (imm))

```
Spread (bit m -> bit 2m):
  byte        0101 1111  = 0x5F
  insert 0s   00 01 00 01 01 01 01 01
  spread      0001 0001 0101 0101  = 0x1155

Sticky carry is clear: term = spread = 0x1155

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             0 0 0 0   (A)
         +   1 1 5 5   (term)
           ---------
             1 1 5 5

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... ....
             0000 0000 0000 0000   (A)
         +   0001 0001 0101 0101   (term)
           ---------------------
             0001 0001 0101 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x00: A = 0x1155, fold = 0x0000
```

### Step  2 — offset 0x01, byte 0xE0 (mov #95,r0 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1110 0000  = 0xE0
  insert 0s   01 01 01 00 00 00 00 00
  spread      0101 0100 0000 0000  = 0x5400

Sticky carry is clear: term = spread = 0x5400

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             1 1 5 5   (A)
         +   5 4 0 0   (term)
           ---------
             6 5 5 5

Binary addition (carries on top, "." = no carry):
  carries  . ..1. .... .... ....
             0001 0001 0101 0101   (A)
         +   0101 0100 0000 0000   (term)
           ---------------------
             0110 0101 0101 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x01: A = 0x6555, fold = 0x0000
```

### Step  3 — offset 0x02, byte 0x18 (shll8 r0)

```
Spread (bit m -> bit 2m):
  byte        0001 1000  = 0x18
  insert 0s   00 00 00 01 01 00 00 00
  spread      0000 0001 0100 0000  = 0x0140

Sticky carry is clear: term = spread = 0x0140

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             6 5 5 5   (A)
         +   0 1 4 0   (term)
           ---------
             6 6 9 5

Binary addition (carries on top, "." = no carry):
  carries  . .... ..1. 1... ....
             0110 0101 0101 0101   (A)
         +   0000 0001 0100 0000   (term)
           ---------------------
             0110 0110 1001 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x02: A = 0x6695, fold = 0x0000
```

### Step  4 — offset 0x03, byte 0x40 (shll8 r0)

```
Spread (bit m -> bit 2m):
  byte        0100 0000  = 0x40
  insert 0s   00 01 00 00 00 00 00 00
  spread      0001 0000 0000 0000  = 0x1000

Sticky carry is clear: term = spread = 0x1000

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             6 6 9 5   (A)
         +   1 0 0 0   (term)
           ---------
             7 6 9 5

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... ....
             0110 0110 1001 0101   (A)
         +   0001 0000 0000 0000   (term)
           ---------------------
             0111 0110 1001 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x03: A = 0x7695, fold = 0x0000
```

### Step  5 — offset 0x04, byte 0x74 (or #116,r0 (imm))

```
Spread (bit m -> bit 2m):
  byte        0111 0100  = 0x74
  insert 0s   00 01 01 01 00 01 00 00
  spread      0001 0101 0001 0000  = 0x1510

Sticky carry is clear: term = spread = 0x1510

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             7 6 9 5   (A)
         +   1 5 1 0   (term)
           ---------
             8 B A 5

Binary addition (carries on top, "." = no carry):
  carries  . 111. 1... ..1. ....
             0111 0110 1001 0101   (A)
         +   0001 0101 0001 0000   (term)
           ---------------------
             1000 1011 1010 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x04: A = 0x8BA5, fold = 0x0000
```

### Step  6 — offset 0x05, byte 0xCB (or #116,r0 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1100 1011  = 0xCB
  insert 0s   01 01 00 00 01 00 01 01
  spread      0101 0000 0100 0101  = 0x5045

Sticky carry is clear: term = spread = 0x5045

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             8 B A 5   (A)
         +   5 0 4 5   (term)
           ---------
             D B E A

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... 1.1.
             1000 1011 1010 0101   (A)
         +   0101 0000 0100 0101   (term)
           ---------------------
             1101 1011 1110 1010

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x05: A = 0xDBEA, fold = 0x0000
```

### Step  7 — offset 0x06, byte 0x18 (shll8 r0)

```
Spread (bit m -> bit 2m):
  byte        0001 1000  = 0x18
  insert 0s   00 00 00 01 01 00 00 00
  spread      0000 0001 0100 0000  = 0x0140

Sticky carry is clear: term = spread = 0x0140

Hex addition (carries on top, "." = no carry):
  carries  . . 1 . .
             D B E A   (A)
         +   0 1 4 0   (term)
           ---------
             D D 2 A

Binary addition (carries on top, "." = no carry):
  carries  . .... .111 1... ....
             1101 1011 1110 1010   (A)
         +   0000 0001 0100 0000   (term)
           ---------------------
             1101 1101 0010 1010

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x06: A = 0xDD2A, fold = 0x0000
```

### Step  8 — offset 0x07, byte 0x40 (shll8 r0)

```
Spread (bit m -> bit 2m):
  byte        0100 0000  = 0x40
  insert 0s   00 01 00 00 00 00 00 00
  spread      0001 0000 0000 0000  = 0x1000

Sticky carry is clear: term = spread = 0x1000

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             D D 2 A   (A)
         +   1 0 0 0   (term)
           ---------
             E D 2 A

Binary addition (carries on top, "." = no carry):
  carries  . ..1. .... .... ....
             1101 1101 0010 1010   (A)
         +   0001 0000 0000 0000   (term)
           ---------------------
             1110 1101 0010 1010

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x07: A = 0xED2A, fold = 0x0000
```

### Step  9 — offset 0x08, byte 0xE4 (or #228,r0 (imm))

```
Spread (bit m -> bit 2m):
  byte        1110 0100  = 0xE4
  insert 0s   01 01 01 00 00 01 00 00
  spread      0101 0100 0001 0000  = 0x5410

Sticky carry is clear: term = spread = 0x5410

Hex addition (carries on top, "." = no carry):
  carries  1 1 . . .
             E D 2 A   (A)
         +   5 4 1 0   (term)
           ---------
           1 4 1 3 A

Binary addition (carries on top, "." = no carry):
  carries  1 1111 1... .... ....
             1110 1101 0010 1010   (A)
         +   0101 0100 0001 0000   (term)
           ---------------------
           1 0100 0001 0011 1010

Carry out of bit 15: it is NOT added back. A keeps 16 bits = 0x413A,
and the sticky carry toggles: fold 0x0000 -> 0x1104  (now ACTIVE)
State after offset 0x08: A = 0x413A, fold = 0x1104
```

### Step 10 — offset 0x09, byte 0xCB (or #228,r0 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1100 1011  = 0xCB
  insert 0s   01 01 00 00 01 00 01 01
  spread      0101 0000 0100 0101  = 0x5045

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0101 0000 0100 0101   0x5045
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0100 0001 0100 0001   0x4141

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             4 1 3 A   (A)
         +   4 1 4 1   (term)
           ---------
             8 2 7 B

Binary addition (carries on top, "." = no carry):
  carries  . 1... ..1. .... ....
             0100 0001 0011 1010   (A)
         +   0100 0001 0100 0001   (term)
           ---------------------
             1000 0010 0111 1011

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x09: A = 0x827B, fold = 0x1104
```

### Step 11 — offset 0x0A, byte 0x15 (mov #21,r5 (imm = key))

```
Spread (bit m -> bit 2m):
  byte        0001 0101  = 0x15
  insert 0s   00 00 00 01 00 01 00 01
  spread      0000 0001 0001 0001  = 0x0111

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0000 0001 0001 0001   0x0111
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0001 0000 0001 0101   0x1015

Hex addition (carries on top, "." = no carry):
  carries  . . . 1 .
             8 2 7 B   (A)
         +   1 0 1 5   (term)
           ---------
             9 2 9 0

Binary addition (carries on top, "." = no carry):
  carries  . .... .... 1111 111.
             1000 0010 0111 1011   (A)
         +   0001 0000 0001 0101   (term)
           ---------------------
             1001 0010 1001 0000

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x0A: A = 0x9290, fold = 0x1104
```

### Step 12 — offset 0x0B, byte 0xE5 (mov #21,r5 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1110 0101  = 0xE5
  insert 0s   01 01 01 00 00 01 00 01
  spread      0101 0100 0001 0001  = 0x5411

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0101 0100 0001 0001   0x5411
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0100 0101 0001 0101   0x4515

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             9 2 9 0   (A)
         +   4 5 1 5   (term)
           ---------
             D 7 A 5

Binary addition (carries on top, "." = no carry):
  carries  . .... .... ..1. ....
             1001 0010 1001 0000   (A)
         +   0100 0101 0001 0101   (term)
           ---------------------
             1101 0111 1010 0101

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x0B: A = 0xD7A5, fold = 0x1104
```

### Step 13 — offset 0x0C, byte 0x52 (mov.l r5,@r0)

```
Spread (bit m -> bit 2m):
  byte        0101 0010  = 0x52
  insert 0s   00 01 00 01 00 00 01 00
  spread      0001 0001 0000 0100  = 0x1104

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0001 0001 0000 0100   0x1104
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0000 0000 0000 0000   0x0000

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             D 7 A 5   (A)
         +   0 0 0 0   (term)
           ---------
             D 7 A 5

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... ....
             1101 0111 1010 0101   (A)
         +   0000 0000 0000 0000   (term)
           ---------------------
             1101 0111 1010 0101

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x0C: A = 0xD7A5, fold = 0x1104
```

### Step 14 — offset 0x0D, byte 0x20 (mov.l r5,@r0)

```
Spread (bit m -> bit 2m):
  byte        0010 0000  = 0x20
  insert 0s   00 00 01 00 00 00 00 00
  spread      0000 0100 0000 0000  = 0x0400

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0000 0100 0000 0000   0x0400
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0001 0101 0000 0100   0x1504

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             D 7 A 5   (A)
         +   1 5 0 4   (term)
           ---------
             E C A 9

Binary addition (carries on top, "." = no carry):
  carries  . ..1. 111. .... 1...
             1101 0111 1010 0101   (A)
         +   0001 0101 0000 0100   (term)
           ---------------------
             1110 1100 1010 1001

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x0D: A = 0xECA9, fold = 0x1104
```

### Step 15 — offset 0x0E, byte 0x00 (mov #0,r8 (imm, compensation))

```
Spread (bit m -> bit 2m):
  byte        0000 0000  = 0x00
  insert 0s   00 00 00 00 00 00 00 00
  spread      0000 0000 0000 0000  = 0x0000

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0000 0000 0000 0000   0x0000
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0001 0001 0000 0100   0x1104

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             E C A 9   (A)
         +   1 1 0 4   (term)
           ---------
             F D A D

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... ....
             1110 1100 1010 1001   (A)
         +   0001 0001 0000 0100   (term)
           ---------------------
             1111 1101 1010 1101

No carry out of bit 15: fold unchanged (0x1104).
State after offset 0x0E: A = 0xFDAD, fold = 0x1104
```

### Step 16 — offset 0x0F, byte 0xE8 (mov #0,r8 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1110 1000  = 0xE8
  insert 0s   01 01 01 00 01 00 00 00
  spread      0101 0100 0100 0000  = 0x5440

Sticky carry is ACTIVE: term = spread XOR 0x1104
      0101 0100 0100 0000   0x5440
  XOR 0001 0001 0000 0100   0x1104
  -----------------------
    = 0100 0101 0100 0100   0x4544

Hex addition (carries on top, "." = no carry):
  carries  1 1 . 1 .
             F D A D   (A)
         +   4 5 4 4   (term)
           ---------
           1 4 2 F 1

Binary addition (carries on top, "." = no carry):
  carries  1 1111 1.1. ...1 1...
             1111 1101 1010 1101   (A)
         +   0100 0101 0100 0100   (term)
           ---------------------
           1 0100 0010 1111 0001

Carry out of bit 15: it is NOT added back. A keeps 16 bits = 0x42F1,
and the sticky carry toggles: fold 0x1104 -> 0x0000  (now CLEAR)
State after offset 0x0F: A = 0x42F1, fold = 0x0000
```

### Step 17 — offset 0x10, byte 0x02 (bra 0x18 (disp))

```
Spread (bit m -> bit 2m):
  byte        0000 0010  = 0x02
  insert 0s   00 00 00 00 00 00 01 00
  spread      0000 0000 0000 0100  = 0x0004

Sticky carry is clear: term = spread = 0x0004

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             4 2 F 1   (A)
         +   0 0 0 4   (term)
           ---------
             4 2 F 5

Binary addition (carries on top, "." = no carry):
  carries  . .... .... .... ....
             0100 0010 1111 0001   (A)
         +   0000 0000 0000 0100   (term)
           ---------------------
             0100 0010 1111 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x10: A = 0x42F5, fold = 0x0000
```

### Step 18 — offset 0x11, byte 0xA0 (bra 0x18 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1010 0000  = 0xA0
  insert 0s   01 00 01 00 00 00 00 00
  spread      0100 0100 0000 0000  = 0x4400

Sticky carry is clear: term = spread = 0x4400

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             4 2 F 5   (A)
         +   4 4 0 0   (term)
           ---------
             8 6 F 5

Binary addition (carries on top, "." = no carry):
  carries  . 1... .... .... ....
             0100 0010 1111 0101   (A)
         +   0100 0100 0000 0000   (term)
           ---------------------
             1000 0110 1111 0101

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x11: A = 0x86F5, fold = 0x0000
```

### Step 19 — offset 0x12, byte 0x09 (mov #9,r8 (imm, compensation))

```
Spread (bit m -> bit 2m):
  byte        0000 1001  = 0x09
  insert 0s   00 00 00 00 01 00 00 01
  spread      0000 0000 0100 0001  = 0x0041

Sticky carry is clear: term = spread = 0x0041

Hex addition (carries on top, "." = no carry):
  carries  . . 1 . .
             8 6 F 5   (A)
         +   0 0 4 1   (term)
           ---------
             8 7 3 6

Binary addition (carries on top, "." = no carry):
  carries  . .... ...1 1... ..1.
             1000 0110 1111 0101   (A)
         +   0000 0000 0100 0001   (term)
           ---------------------
             1000 0111 0011 0110

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x12: A = 0x8736, fold = 0x0000
```

### Step 20 — offset 0x13, byte 0xE8 (mov #9,r8 (opcode))

```
Spread (bit m -> bit 2m):
  byte        1110 1000  = 0xE8
  insert 0s   01 01 01 00 01 00 00 00
  spread      0101 0100 0100 0000  = 0x5440

Sticky carry is clear: term = spread = 0x5440

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             8 7 3 6   (A)
         +   5 4 4 0   (term)
           ---------
             D B 7 6

Binary addition (carries on top, "." = no carry):
  carries  . .... 1... .... ....
             1000 0111 0011 0110   (A)
         +   0101 0100 0100 0000   (term)
           ---------------------
             1101 1011 0111 0110

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x13: A = 0xDB76, fold = 0x0000
```

### Step 21 — offset 0x14, byte 0x4B (data (compensation))

```
Spread (bit m -> bit 2m):
  byte        0100 1011  = 0x4B
  insert 0s   00 01 00 00 01 00 01 01
  spread      0001 0000 0100 0101  = 0x1045

Sticky carry is clear: term = spread = 0x1045

Hex addition (carries on top, "." = no carry):
  carries  . . . . .
             D B 7 6   (A)
         +   1 0 4 5   (term)
           ---------
             E B B B

Binary addition (carries on top, "." = no carry):
  carries  . ..1. .... 1... 1...
             1101 1011 0111 0110   (A)
         +   0001 0000 0100 0101   (term)
           ---------------------
             1110 1011 1011 1011

No carry out of bit 15: fold unchanged (0x0000).
State after offset 0x14: A = 0xEBBB, fold = 0x0000
```

### Step 22 — offset 0x15, byte 0x6B (data (compensation))

```
Spread (bit m -> bit 2m):
  byte        0110 1011  = 0x6B
  insert 0s   00 01 01 00 01 00 01 01
  spread      0001 0100 0100 0101  = 0x1445

Sticky carry is clear: term = spread = 0x1445

Hex addition (carries on top, "." = no carry):
  carries  1 1 1 1 .
             E B B B   (A)
         +   1 4 4 5   (term)
           ---------
           1 0 0 0 0

Binary addition (carries on top, "." = no carry):
  carries  1 1111 1111 1111 111.
             1110 1011 1011 1011   (A)
         +   0001 0100 0100 0101   (term)
           ---------------------
           1 0000 0000 0000 0000

Carry out of bit 15: it is NOT added back. A keeps 16 bits = 0x0000,
and the sticky carry toggles: fold 0x0000 -> 0x1104  (now ACTIVE)
State after offset 0x15: A = 0x0000, fold = 0x1104
```

## 6. Final check

```
A    = 0x0000   (whole zone 0x000..0x015, bytes 0x14/0x15 included)
fold = 0x1104   (3 carries out of bit 15: odd)
```

You can recompute it with the local checksum module:

```
python3 -c "from holly_g1_checksum import state; \
print([hex(x) for x in state(open('g1min.bin','rb').read()[:0x16])])"
# ['0x0', '0x1104']
```
