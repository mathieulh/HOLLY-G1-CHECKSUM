! Minimal NAOMI BIOS: unlocks G1 with the smallest validated area.
! Key (size) 0x15: Holly checks 0x000-0x015 (22 bytes). No RAM, no CPU init.
! Validated on NAOMI 2 (VROM IC27 in byte mode): 0x5F74EC = 3 (OPEN), 0x5F707C = FFFE.
!
! Rule observed on this setup: sum over the WHOLE area 0x000-0x015 == 0 (bytes 0x14/0x15 included),
! final fold = 0x1104 (the same image with a final fold of 0 stays closed).
! Linear execution from P2 ROM at reset; the CPU reads in 32-bit words. The key write
! goes out on the bus one word after the mov.l (between the reads of 0x13 and 0x14): Holly must
! still read at least one byte of the area afterwards, hence the minimum size of 0x15.
! bra to 0x18 (4-byte aligned): strictly linear read stream, with no re-reads (raw trace).
!
! Build: ./make_miniholly.sh
    .section .text
    .little
    .global _start
_start:
    .org 0x000
    mov     #95, r0             ! 0x00  r0 = 0x5F
    shll8   r0                  ! 0x02
    or      #116, r0            ! 0x04  0x5F74
    shll8   r0                  ! 0x06
    or      #228, r0            ! 0x08  r0 = 0x005F74E4 (P0: MMU and cache disabled at reset)
    mov     #21, r5             ! 0x0A  r5 = 0x15 = key / area size
    mov.l   r5, @r0             ! 0x0C  Write the key
    mov     #0, r8              ! 0x0E  compensation (free immediate, r8 unused)
    bra     next_area           ! 0x10  to 0x18, 4-byte aligned
    mov     #9, r8              ! 0x12  delay slot, compensation
    .byte   0x4B, 0x6B          ! 0x14  compensation: (0x000..0x015) = 0 (never executed)
    nop                         ! 0x16  outside the area, read with the word 0x14-0x17, not executed
next_area:                      ! 0x18
