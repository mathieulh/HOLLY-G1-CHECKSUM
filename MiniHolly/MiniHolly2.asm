! MiniHolly2: minimal BIOS that unlocks G1, intended for both NAOMI and Dreamcast.
! Key (size) 0x3F: Holly checks 0x000-0x03F (64 bytes). No RAM, no CPU init.
!
! Differences from MiniHolly (g1min, key 0x15, tested on NAOMI 2 only):
!  - Follows the stored-value rule used by every official Dreamcast BIOS and confirmed by
!    the 68,245 Develop BIOS tests on NAOMI 2: checksum of 0x000-0x03D == stored value at
!    0x03E (00 00), with fold 0 before AND after the stored bytes (Dreamcast-safe fold).
!    The whole area therefore ends on (0x0000, fold 0), exactly like retail Dreamcast BIOSes.
!  - The key is written long before the end of the area: on NAOMI 2 the write reached the bus
!    after word 0x10-0x13 was fetched; here 11 more words (0x14-0x3F) are still read
!    afterwards, so a faster or 16-bit boot ROM bus (Dreamcast) still leaves margin.
!  - Linear fetch: the only branch inside the area targets 0x40 (4-byte aligned), so no word
!    is fetched twice.
!
! Note: no image can satisfy both this rule and MiniHolly's "whole area = 0 with fold 0x1104"
! (checked for all 65,536 stored values), and a 0x400 Develop BIOS ending on MiniHolly's state
! stayed closed. MiniHolly2 therefore follows the stored-value rule only.
!
! Verify: python3 holly_g1_checksum.py --verify miniholly2.bin auto  -> OK (size 0x40)
! Build:  sh-elf-as -little -o MiniHolly2.o MiniHolly2.asm
!         sh-elf-objcopy -O binary MiniHolly2.o MiniHolly2.raw   (then pad to the chip size)
    .section .text
    .little
    .global _start
_start:
    .org 0x000
    mov     #95, r0             ! 0x00  5F E0  r0 = 0x5F
    shll8   r0                  ! 0x02  18 40
    or      #116, r0            ! 0x04  74 CB  r0 = 0x5F74
    shll8   r0                  ! 0x06  18 40
    or      #228, r0            ! 0x08  E4 CB  r0 = 0x005F74E4 (P0: MMU and cache off at reset)
    mov     #63, r5             ! 0x0A  3F E5  r5 = 0x3F = key / last checked offset
    mov.l   r5, @r0             ! 0x0C  52 20  write the key
    mov     #4, r8              ! 0x0E  04 E8  compensation (r8 unused)
    .rept   20                  ! 0x10-0x37    linear fill, read after the key write
    nop                         !       09 00
    .endr
    mov     #-43, r8            ! 0x38  D5 E8  compensation (0xD5)
    bra     idle                ! 0x3A  01 A0  to 0x40, 4-byte aligned
    mov     #-75, r8            ! 0x3C  B5 E8  delay slot, compensation (0xB5)
    .byte   0x00, 0x00          ! 0x3E  stored value 0x0000 (never executed)
idle:                           ! 0x40  outside the checked area
    bra     idle                ! 0x40  FE AF
    nop                         ! 0x42  09 00
