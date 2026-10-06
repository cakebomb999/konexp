"""Werksprofile der Kone XP als Daten (Reports 0x06 und 0x07).

Rekonstruiert aus den Reset-Pfaden und dem Tasten-Preset „Basic“ des Swarm-Plugins (siehe docs/PROTOCOL.md);
P0 wurde bytegenau gegen eine Kone XP im Werkszustand (FW 1.09) geprüft. P1–P4 unterscheiden sich nur in Byte 2 (Profil), bei 0x06 in der
Profilfarbe 0x9f–0xa1, und in der Checksumme.

Werksreset über Report 0x09 wird bewusst NICHT verwendet; stattdessen werden diese Bytes normal
über KoneXP.write() geschrieben.
"""
from .device import with_checksum

# Report 0x06, Profil 0, 174 B inkl. Checksumme
SETTINGS_P0_HEX = (
    '06ae00' '0606' '1f' '01'                 # ID, Länge, Profil, 0x03/0x04, DPI-Maske, aktive Stufe
    '08001000180020004000'                    # DPI X 400/800/1200/1600/3200
    '08001000180020004000'                    # DPI Y
    '000003' '0a06ff' '0f0000'                # 0x1b–0x1d, Effekt/Speed/Helligkeit, Timeout 0x21–0x23
    + '14ff0048ff64' * 20 +                   # 20 LEDs
    '0164ffc50bdc' '00000000000000000000' '093d'  # 0x9c–0xa1, 0xa2–0xab, Checksumme
)

# Profilfarben (RGB an 0x9f–0xa1) je Profil
PROFILE_COLORS = ('c50bdc', 'ffffff', 'f40000', '51ff00', 'f6ff39')

# Report 0x07, Profil 0, 125 B inkl. Checksumme (Preset [0] „Basic“)
BUTTONS_P0_HEX = (
    '077d00'
    '00000101' '00000201' '00000301' '00000701' '00000801' '00000901' '00000a01'
    '00000202' '00000302' '00000501' '00000601' '00150006' '000a0006' '0000010a' '00000108'
    '00000101' '00000201' '00000403' '00000203' '00000303' '00000703' '00000803'
    '00220006' '00230006' '00200006' '00210006' '001e0006' '001f0006' '00000000' '00000b08'
    '2e02'
)


def settings(profile):
    """Werks-Report 0x06 für Profil 0..4 (mit gültiger Checksumme)."""
    if not 0 <= profile <= 4:
        raise ValueError('Profil 0..4')
    buf = bytearray.fromhex(SETTINGS_P0_HEX)
    buf[2] = profile
    buf[0x9f:0xa2] = bytes.fromhex(PROFILE_COLORS[profile])
    return with_checksum(buf)


def buttons(profile):
    """Werks-Report 0x07 für Profil 0..4 (mit gültiger Checksumme)."""
    if not 0 <= profile <= 4:
        raise ValueError('Profil 0..4')
    buf = bytearray.fromhex(BUTTONS_P0_HEX)
    buf[2] = profile
    return with_checksum(buf)


# Report 0x11 Werkswert (Debounce 10 ms) – aus Dump 20261006-102656-r11.bin
ADVANCED_HEX = '11140a' + '00' * 15 + '2f00'
