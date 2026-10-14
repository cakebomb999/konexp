"""Codecs für Report 0x06 (Profil-Settings), 0x07 (Tasten) und 0x11 (Debounce).

Die Klassen halten den kompletten Rohpuffer; unbekannte Bytes bleiben unverändert.
Kone XP und Kone XP Air nutzen dieselben Formate; die Air-Blöcke sind kürzer (0x06: 78 statt 174 B,
7 LED-Zonen à 5 B, Debounce 19 statt 20 B). Das Modell ergibt sich aus der Länge.
Feldkarte: docs/PROTOCOL.md, docs/PROTOCOL-XP-AIR.md.
"""
from .device import with_checksum
from .i18n import tr

DPI_MIN, DPI_MAX, DPI_STEP = 50, 19000, 50
POLLING_HZ = (125, 250, 500, 1000)
EFFECTS = {1: 'Fully Lit', 2: 'Blinking', 3: 'Breathing', 4: 'Heartbeat',
           5: 'Photon FX', 9: 'AIMO', 10: 'Colorwave'}
EFFECTS_AIR = {**EFFECTS, 0x13: 'Battery Indication'}
SLEEP_EFFECTS = {0: 'Off', 1: 'Fully Lit', 2: 'Blinking', 3: 'Breathing', 4: 'Heartbeat', 9: 'AIMO'}
LED_COUNT = 20
LED_WHEEL, LED_DPI = 18, 19


class _Report:
    RID = None
    SIZES = ()  # (Kone XP, Kone XP Air)

    def __init__(self, raw):
        if len(raw) not in self.SIZES or raw[0] != self.RID:
            raise ValueError(tr('kein gültiger Report 0x{rid:02x}').format(rid=self.RID))
        self.raw = bytearray(raw)

    @property
    def air(self):
        return len(self.raw) != self.SIZES[0]

    def to_bytes(self):
        return with_checksum(self.raw)

    def _u8(self, off, val, lo=0, hi=255):
        if not lo <= val <= hi:
            raise ValueError(tr('Wert {val} außerhalb {lo}..{hi}').format(val=val, lo=lo, hi=hi))
        self.raw[off] = val


# Lage der LEDs und der Profilfarbe (RGB), Byte mit Alpha der Profilfarbe, DPI-Einheit im Rohwert
LAYOUT06 = {174: dict(leds=LED_COUNT, stride=6, color=0x9f, alpha=0x9e, dpi_unit=DPI_STEP),
            78: dict(leds=7, stride=5, color=0x49, alpha=None, dpi_unit=1)}


class Settings(_Report):
    RID, SIZES = 0x06, (174, 78)

    profile = property(lambda s: s.raw[2])
    layout = property(lambda s: LAYOUT06[len(s.raw)])
    effects = property(lambda s: EFFECTS_AIR if s.air else EFFECTS)
    led_count = property(lambda s: s.layout['leds'])

    @property
    def led_end(self):
        """Erstes Byte hinter den LED-Daten."""
        return 0x24 + self.layout['stride'] * self.led_count

    def led_index(self, off):
        """LED, zu der Byte `off` gehört, sonst None."""
        return (off - 0x24) // self.layout['stride'] if 0x24 <= off < self.led_end else None

    # DPI
    @property
    def dpi_enabled(self):
        return [bool(self.raw[0x05] >> i & 1) for i in range(5)]

    def set_dpi_enabled(self, stage, on):
        mask = self.raw[0x05] & ~(1 << stage) | (on << stage)
        if not mask & 0x1f:
            raise ValueError(tr('mindestens eine DPI-Stufe muss aktiv sein'))
        self.raw[0x05] = mask

    @property
    def dpi_active(self):
        return self.raw[0x06]

    @dpi_active.setter
    def dpi_active(self, stage):
        self._u8(0x06, stage, 0, 4)

    def dpi(self, stage, axis='x'):
        off = (0x07 if axis == 'x' else 0x11) + 2 * stage
        return int.from_bytes(self.raw[off:off + 2], 'little') * self.layout['dpi_unit']

    def set_dpi(self, stage, value, y=True):
        """Setzt DPI einer Stufe. Swarm schreibt nur X; wir setzen Y standardmäßig mit."""
        if not (DPI_MIN <= value <= DPI_MAX and value % DPI_STEP == 0):
            raise ValueError(tr('DPI {value}: erlaubt {lo}..{hi} in {step}er-Schritten').format(
                value=value, lo=DPI_MIN, hi=DPI_MAX, step=DPI_STEP))
        raw = (value // self.layout['dpi_unit']).to_bytes(2, 'little')
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
        if code not in self.effects:
            raise ValueError(tr('Effekt {code} unbekannt').format(code=code))
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
            raise ValueError(tr('Schlaf-Effekt {code} unbekannt').format(code=code))
        self.raw[0x22] = code
        self.raw[0x23] = 0

    def led(self, i):
        """(alpha, r, g, b) der LED i."""
        o = 0x24 + self.layout['stride'] * i
        return tuple(self.raw[o + 1:o + 5])

    def set_led(self, i, r, g, b, alpha=0xff):
        o = 0x24 + self.layout['stride'] * i
        self.raw[o + 1:o + 5] = bytes([alpha, r, g, b])

    @property
    def profile_color(self):
        c = self.layout['color']
        return tuple(self.raw[c:c + 3])

    def set_profile_color(self, r, g, b):
        c, a = self.layout['color'], self.layout['alpha']
        self.raw[c:c + 3] = bytes([r, g, b])
        if a is not None:
            self.raw[a] = 0xff


# --- Report 0x07 ----------------------------------------------------------

BUTTONS = [tr('Links'), tr('Rechts'), tr('Radklick'), tr('Rad-Tilt links'), tr('Rad-Tilt rechts'), tr('Rad hoch'),
           tr('Rad runter'), tr('Seitentaste vorn'), tr('Seitentaste hinten'), tr('Daumen 1'), tr('Daumen 2'),
           tr('Daumen 3'), tr('Daumen 4'), tr('Easy-Shift'), tr('Taste hinter Rad')]
N_BUTTONS = len(BUTTONS)
# Kone XP Air: gleiche 15 Tasten, andere Reihenfolge im Block. Geräte-Index -> Index der Kone XP
AIR_BUTTON_ORDER = (0, 1, 2, 5, 6, 9, 10, 7, 8, 11, 12, 3, 4, 13, 14)
BUTTONS_AIR = [BUTTONS[i] for i in AIR_BUTTON_ORDER]


def button_names(air):
    return BUTTONS_AIR if air else BUTTONS


class Buttons(_Report):
    RID, SIZES = 0x07, (125, 125)

    profile = property(lambda s: s.raw[2])

    def entry(self, k, shift=False):
        o = 3 + 4 * (k + (N_BUTTONS if shift else 0))
        return tuple(self.raw[o:o + 4])

    def set_entry(self, k, entry, shift=False):
        if len(entry) != 4:
            raise ValueError(tr('Eintrag = 4 Bytes [b0, b1, b2, typ]'))
        o = 3 + 4 * (k + (N_BUTTONS if shift else 0))
        self.raw[o:o + 4] = bytes(entry)


# --- Report 0x11 ----------------------------------------------------------

class Advanced(_Report):
    RID, SIZES = 0x11, (20, 19)

    @property
    def debounce_ms(self):
        return self.raw[3 if self.air else 2]

    @debounce_ms.setter
    def debounce_ms(self, v):
        if not self.air:
            return self._u8(2, v, 0, 10)
        # Air wie Swarm (SetZeroDebounce): Enable, Wert in Byte 3 und 4, übrige 12 Werte auf 10
        self._u8(3, v, 0, 10)
        self.raw[4] = v
        self.raw[2] = 1
        self.raw[5:0x11] = bytes([0x0a]) * 12
