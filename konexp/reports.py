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


# --- Report 0x08 ----------------------------------------------------------

MACRO_SIZE, MACRO_EVENTS, MACRO_END = 1043, 0x51, 0x411
# Maustasten im Makro (ROCCAT_Swarm_Monitor.exe, Namenstabelle bei 0x41673c): links, rechts, Mitte, Taste 4, 5
MOUSE_KEYS = (0xf0, 0xf1, 0xf2, 0xf3, 0xf4)
PAUSE_UNITS = {1: 20, 2: 50, 3: 100}  # Pausen-Block 00 <einheit> <u16 LE>
MACRO_MAX_PAUSE = 0xffff * 100


def parse_steps(text):
    """'+f0 1000 -f0 1500' -> [('+', 0xf0), 1000, ('-', 0xf0), 1500]. Taste = HID-Usage hex, Zahl = Pause in ms."""
    steps = []
    for t in text.split():
        try:
            if t[0] in '+-':
                key = int(t[1:], 16)
                if not 0 < key <= 0xff:
                    raise ValueError
                steps.append((t[0], key))
            else:
                steps.append(int(t))
                if not 0 <= steps[-1] <= MACRO_MAX_PAUSE:
                    raise ValueError
        except ValueError:
            raise ValueError(tr('Makro-Schritt „{step}“: erwartet +f0 / -f0 (Taste hex) oder Pause in ms').format(
                step=t)) from None
    return steps


def format_steps(steps):
    return ' '.join(f'{s[0]}{s[1]:02x}' if isinstance(s, tuple) else str(s) for s in steps)


def _pause_block(ms):
    """Größte Einheit, die ms exakt teilt (sonst 20 ms, gerundet)."""
    unit = next((u for u in (3, 2, 1) if ms % PAUSE_UNITS[u] == 0), 1)
    n = min(round(ms / PAUSE_UNITS[unit]), 0xffff) or 1
    return bytes([0, unit]) + n.to_bytes(2, 'little')


def macro(profile, slot, steps, name='konexp', group='konexp', repeat=None):
    """Report 0x08. repeat=None: Schleife solange gedrückt (wie Swarms Autoclicker), sonst n-mal bei Druck.

    steps: ('+', key) drücken, ('-', key) loslassen, int = Pause in ms vor dem nächsten Event.
    Pause davor 1–127 ms steckt im Event-Byte; längere: Block + Rest im Event (exakt, Rest 1–100 ms)."""
    if not any(isinstance(s, tuple) for s in steps):
        raise ValueError(tr('Makro ohne Tasten-Event'))
    if repeat is not None and not 1 <= repeat <= 0xffff:
        raise ValueError(tr('Wiederholungen 1..65535'))
    out, pause = bytearray(), 0
    for s in steps:
        if isinstance(s, int):
            pause += s
            if pause > MACRO_MAX_PAUSE:
                raise ValueError(tr('Makro-Pause zu lang'))
            continue
        updown, key = s
        if pause > 127:
            n = (pause - 1) // 100
            out += bytes([0, 3]) + n.to_bytes(2, 'little')
            pause -= 100 * n
        out += bytes([max(pause, 1) | (0x80 if updown == '-' else 0), key])
        pause = 0
    if pause:  # Pause am Ende: nur als Block, Raster 20/50/100 ms
        out += _pause_block(pause)
    if len(out) + 2 > MACRO_END - MACRO_EVENTS:
        raise ValueError(tr('Makro zu lang'))
    raw = bytearray(MACRO_SIZE)
    raw[:5] = bytes([0x08, 0x13, 0x04, profile, slot])
    raw[0x05:0x2c] = group.encode()[:39].ljust(39, b'\0')
    raw[0x2d:0x4c] = name.encode()[:31].ljust(31, b'\0')
    raw[0x4d] = repeat is None
    raw[0x4f:0x51] = (repeat or 0).to_bytes(2, 'little')
    raw[MACRO_EVENTS:MACRO_EVENTS + len(out)] = out
    return with_checksum(raw)


def parse_macro(raw):
    """Report 0x08 -> dict(name, group, repeat, steps); Gegenstück zu macro(). repeat None = Schleife."""
    if len(raw) != MACRO_SIZE or raw[0] != 0x08:
        raise ValueError(tr('kein gültiger Report 0x{rid:02x}').format(rid=0x08))
    text = lambda a, b: bytes(raw[a:b]).split(b'\0')[0].decode(errors='replace')  # noqa: E731
    steps, pause, o = [], 0, MACRO_EVENTS
    while o + 1 < MACRO_END:
        d, key = raw[o], raw[o + 1]
        if d == 0 and key == 0:
            break
        if d == 0:
            pause += PAUSE_UNITS.get(key, 0) * int.from_bytes(raw[o + 2:o + 4], 'little')
            o += 4
            continue
        pause += d & 0x7f
        steps += [pause, ('-' if d & 0x80 else '+', key)]
        pause, o = 0, o + 2
    if pause:
        steps.append(pause)
    loop = int.from_bytes(raw[0x4d:0x4f], 'little')
    return dict(name=text(0x2d, 0x4d), group=text(0x05, 0x2d), steps=steps,
                repeat=None if loop else int.from_bytes(raw[0x4f:0x51], 'little'))
