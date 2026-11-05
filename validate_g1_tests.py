#!/usr/bin/env python3
"""Replay real-hardware G1 tests against the checksum in holly_g1_checksum.py.

Input:
  - the base BIOS file (e.g. g1test.bin) or its C array export (g1test.c)
  - a test log, one test per line, in French or English (detected per line):
        ADR=Llane OLD->NEW ... [; ADR=... ] || G1=OUVERT/FERME     (French)
        ADR=Llane OLD->NEW ... [; ADR=... ] || G1=OPEN/CLOSED      (English)
    Lines starting with '#' and blank lines are ignored. Results that are neither
    open nor closed (ERR/ERREUR/ERROR) are skipped and counted.

For each test, the changes are applied to the base image, then holly_check()
predicts OPEN if checksum(first size-2 bytes) == stored value (last 2 bytes, LE).
Prints a confusion matrix and lists the mismatches.

Examples:
  validate_g1_tests.py g1test.c tests_physiques_G1.txt --size 0x400
  validate_g1_tests.py g1test.bin hardware_tests_G1.txt --size 0x400
"""
import argparse
import collections
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from holly_g1_checksum import FOLD, SPREAD, stored_value  # noqa: E402

LINE = re.compile(r'\s*([0-9A-Fa-f]+)=L\d\s+([0-9A-Fa-f]{2})->([0-9A-Fa-f]{2})')
RESULT = re.compile(r'G1\s*[=:]\s*([A-Za-z\u00C0-\u017F]+)', re.IGNORECASE)

# result keyword (accents removed, upper case) -> (opened, language)
KEYWORDS = {
    'OUVERT': (True, 'fr'), 'OUVERTE': (True, 'fr'),
    'FERME': (False, 'fr'), 'FERMEE': (False, 'fr'),
    'OPEN': (True, 'en'), 'OPENED': (True, 'en'),
    'CLOSED': (False, 'en'), 'CLOSE': (False, 'en'),
}
SKIPPED = {'ERR', 'ERREUR', 'ERROR'}


def _plain(word):
    """Upper case without accents: 'fermé' -> 'FERME'."""
    return ''.join(c for c in unicodedata.normalize('NFD', word)
                   if unicodedata.category(c) != 'Mn').upper()


def load_image(path):
    data = open(path, 'rb').read()
    if path.lower().endswith('.c'):
        text = data.decode('latin-1')
        body = text[text.index('{') + 1:text.rindex('}')]
        data = bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', body))
    return data


def load_tests(path, base):
    """Return (tests, original byte mismatches, languages Counter, skipped results)."""
    tests, mismatch = [], 0
    langs, skipped = collections.Counter(), collections.Counter()
    with open(path, encoding='utf-8-sig', errors='replace') as fh:
        for n, line in enumerate(fh, 1):
            if line.lstrip().startswith('#') or '||' not in line:
                continue
            mods, res = line.rsplit('||', 1)
            m = RESULT.search(res)
            if not m:
                sys.exit(f"line {n}: cannot read the G1 result in '{res.strip()}' "
                         "(expected G1=OUVERT/FERME or G1=OPEN/CLOSED)")
            word = _plain(m[1])
            if word in SKIPPED:
                skipped[word] += 1
                continue
            if word not in KEYWORDS:
                sys.exit(f"line {n}: unknown G1 result '{m[1]}' "
                         "(expected OUVERT/FERME or OPEN/CLOSED)")
            opened, lang = KEYWORDS[word]
            changes = []
            for part in mods.split(';'):
                pm = LINE.match(part)
                if not pm:
                    sys.exit(f"line {n}: cannot parse '{part.strip()}'")
                a, old, new = int(pm[1], 16), int(pm[2], 16), int(pm[3], 16)
                if a >= len(base):
                    sys.exit(f"line {n}: address {a:#x} is outside the base BIOS "
                             f"({len(base):#x} bytes)")
                if base[a] != old:
                    mismatch += 1
                changes.append((a, new))
            langs[lang] += 1
            tests.append((n, changes, opened, line.strip()))
    return tests, mismatch, langs, skipped


def main():
    p = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    p.add_argument("bios", help="base BIOS (.bin) or C array export (.c)")
    p.add_argument("tests", help="test log in French (tests_physiques_G1.txt) or English")
    p.add_argument("--size", type=lambda x: int(x, 0), default=0x400,
                   help="BIOS image size (default 0x400)")
    p.add_argument("--show", type=int, default=20, help="mismatches to print (default 20)")
    args = p.parse_args()

    base = load_image(args.bios)
    size, zone = args.size, args.size - 2
    tests, mismatch, langs, skipped = load_tests(args.tests, base)
    if not tests:
        sys.exit("no test found in the log")
    names = {'fr': 'French (OUVERT/FERME)', 'en': 'English (OPEN/CLOSED)'}
    print(f"base image     : {len(base):#x} bytes, size checked {size:#x}")
    print(f"tests          : {len(tests)} (original byte mismatches: {mismatch})")
    print(f"log language   : " + ", ".join(f"{names[k]} {v}" for k, v in langs.items()))
    if skipped:
        print(f"skipped        : " + ", ".join(f"{k} {v}" for k, v in skipped.items()))

    # checksum state before every offset of the base image (fast replay)
    states, A, f = [(0, 0)], 0, 0
    for b in base[:zone]:
        A += SPREAD[b] ^ f
        if A >= 0x10000:
            A &= 0xFFFF
            f ^= FOLD
        states.append((A, f))
    ok_base = states[zone][0] == stored_value(base, size)
    print(f"base checksum  : {states[zone][0]:#06x}, stored {stored_value(base, size):#06x}"
          f" -> {'OK' if ok_base else 'FAIL'}")

    matrix = collections.Counter()
    wrong = []
    for n, changes, opened, text in tests:
        img = bytearray(base[:size])
        for a, v in changes:
            if a < size:
                img[a] = v
        start = min(min(a for a, _ in changes), zone)
        A, f = states[start]
        for b in img[start:zone]:
            A += SPREAD[b] ^ f
            if A >= 0x10000:
                A &= 0xFFFF
                f ^= FOLD
        predicted = A == stored_value(img, size)
        matrix[(predicted, opened)] += 1
        if predicted != opened:
            wrong.append((n, A, stored_value(img, size), text))

    tp, tn = matrix[(True, True)], matrix[(False, False)]
    fp, fn = matrix[(True, False)], matrix[(False, True)]
    print()
    print("                    hardware OPEN   hardware CLOSED")
    print(f"predicted OPEN      {tp:>13}   {fp:>15}")
    print(f"predicted CLOSED    {fn:>13}   {tn:>15}")
    print(f"agreement          : {100 * (tp + tn) / len(tests):.3f} %")

    if wrong:
        addr = collections.Counter(a for n, *_ in wrong
                                   for a, _ in next(t[1] for t in tests if t[0] == n))
        print(f"\nmismatches: {len(wrong)}; most common changed addresses:",
              ", ".join(f"{a:#x} ({c})" for a, c in addr.most_common(5)))
        for n, A, s, text in wrong[:args.show]:
            print(f"  line {n}: checksum {A:#06x} stored {s:#06x} | {text[:150]}")


if __name__ == '__main__':
    main()
