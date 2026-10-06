"""Codecs für Report 0x06 (Profil-Settings), 0x07 (Tasten) und 0x11 (Debounce).

Die Klassen halten den kompletten Rohpuffer; unbekannte Bytes bleiben unverändert.
Feldkarte: docs/PROTOCOL.md.
"""
from .device import with_checksum

DPI_MIN, DPI_MAX, DPI_STEP = 50, 19000, 50
POLLING_HZ = (125, 250, 500, 1000)
EFFECTS = {1: 'Fully Lit', 2: 'Blinking', 3: 'Breathing', 4: 'Heartbeat',
           5: 'Photon FX', 9: 'AIMO', 10: 'Colorwave'}
SLEEP_EFFECTS = {0: 'Off', 1: 'Fully Lit', 2: 'Blinking', 3: 'Breathing', 4: 'Heartbeat', 9: 'AIMO'}
LED_COUNT = 20
LED_WHEEL, LED_DPI = 18, 19


class _Report:
    RID = None
    SIZE = None

    def __init__(self, raw):
        if len(raw) != self.SIZE or raw[0] != self.RID:
            raise ValueError(f'kein gültiger Report 0x{self.RID:02x}')
        self.raw = bytearray(raw)

    def to_bytes(self):
        return with_checksum(self.raw)

    def _u8(self, off, val, lo=0, hi=255):
        if not lo <= val <= hi:
            raise ValueError(f'Wert {val} außerhalb {lo}..{hi}')
        self.raw[off] = val


class Settings(_Report):
    RID, SIZE = 0x06, 174

    profile = property(lambda s: s.raw[2])

    # DPI
    @property
    def dpi_enabled(self):
        return [bool(self.raw[0x05] >> i & 1) for i in range(5)]

    def set_dpi_enabled(self, stage, on):
        mask = self.raw[0x05] & ~(1 << stage) | (on << stage)
        if not mask & 0x1f:
            raise ValueError('mindestens eine DPI-Stufe muss aktiv sein')
        self.raw[0x05] = mask

    @property
    def dpi_active(self):
        return self.raw[0x06]

    @dpi_active.setter
    def dpi_active(self, stage):
        self._u8(0x06, stage, 0, 4)

    def dpi(self, stage, axis='x'):
        off = (0x07 if axis == 'x' else 0x11) + 2 * stage
        return int.from_bytes(self.raw[off:off + 2], 'little') * DPI_STEP

    def set_dpi(self, stage, value, y=True):
        """Setzt DPI einer Stufe. Swarm schreibt nur X; wir setzen Y standardmäßig mit."""
        if not (DPI_MIN <= value <= DPI_MAX and value % DPI_STEP == 0):
            raise ValueError(f'DPI {value}: erlaubt {DPI_MIN}..{DPI_MAX} in {DPI_STEP}er-Schritten')
        raw = (value // DPI_STEP).to_bytes(2, 'little')
        self.raw[0x07 + 2 * stage:0x09 + 2 * stage] = raw
        if y:
            self.raw[0x11 + 2 * stage:0x13 + 2 * stage] = raw

    # Sensor
    @property
    def angle_snapping(self):
        return bool(self.raw[0x1b] & 1)

    @angle_snapping.setter
    def angle_snapping(self, on):
        self.raw[0x1b] = self.raw[0x1b] & ~1 | int(on)

    @property
    def polling_hz(self):
        i = self.raw[0x1d]
        return POLLING_HZ[i] if i < len(POLLING_HZ) else None

    @polling_hz.setter
    def polling_hz(self, hz):
        self.raw[0x1d] = POLLING_HZ.index(hz)

    # Licht
    @property
    def effect(self):
        return self.raw[0x1e]

    @effect.setter
    def effect(self, code):
        if code not in EFFECTS:
            raise ValueError(f'Effekt {code} unbekannt')
        self.raw[0x1e] = code

    speed = property(lambda s: s.raw[0x1f], lambda s, v: s._u8(0x1f, v, 1, 11))
    brightness = property(lambda s: s.raw[0x20], lambda s, v: s._u8(0x20, v))

    @property
    def led_timeout(self):
        return self.raw[0x21]

    @led_timeout.setter
    def led_timeout(self, v):
        self._u8(0x21, v)
        self.raw[0x23] = 0  # wie Swarm

    @property
    def sleep_effect(self):
        return self.raw[0x22]

    @sleep_effect.setter
    def sleep_effect(self, code):
        if code not in SLEEP_EFFECTS:
            raise ValueError(f'Schlaf-Effekt {code} unbekannt')
        self.raw[0x22] = code
        self.raw[0x23] = 0

    def led(self, i):
        """(alpha, r, g, b) der LED i."""
        o = 0x24 + 6 * i
        return tuple(self.raw[o + 1:o + 5])

    def set_led(self, i, r, g, b, alpha=0xff):
        o = 0x24 + 6 * i
        self.raw[o + 1:o + 5] = bytes([alpha, r, g, b])

    @property
    def profile_color(self):
        return tuple(self.raw[0x9f:0xa2])

    def set_profile_color(self, r, g, b):
        self.raw[0x9e:0xa2] = bytes([0xff, r, g, b])


# --- Report 0x07 ----------------------------------------------------------

BUTTONS = ['Links', 'Rechts', 'Radklick', 'Rad-Tilt links', 'Rad-Tilt rechts', 'Rad hoch',
           'Rad runter', 'Seitentaste vorn', 'Seitentaste hinten', 'Daumen 1', 'Daumen 2',
           'Daumen 3', 'Daumen 4', 'Easy-Shift', 'Taste hinter Rad']
N_BUTTONS = len(BUTTONS)


class Buttons(_Report):
    RID, SIZE = 0x07, 125

    profile = property(lambda s: s.raw[2])

    def entry(self, k, shift=False):
        o = 3 + 4 * (k + (N_BUTTONS if shift else 0))
        return tuple(self.raw[o:o + 4])

    def set_entry(self, k, entry, shift=False):
        if len(entry) != 4:
            raise ValueError('Eintrag = 4 Bytes [b0, b1, b2, typ]')
        o = 3 + 4 * (k + (N_BUTTONS if shift else 0))
        self.raw[o:o + 4] = bytes(entry)


# --- Report 0x11 ----------------------------------------------------------

class Advanced(_Report):
    RID, SIZE = 0x11, 20

    debounce_ms = property(lambda s: s.raw[2], lambda s, v: s._u8(2, v, 0, 10))
