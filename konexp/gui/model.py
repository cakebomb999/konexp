"""Datenmodell der GUI: Laden, Ändern, Diff, Schreibplan, Backup – ohne Qt, ohne Maus testbar.

Geräte-Zugriff läuft ausschließlich über ein Backend:
  DeviceBackend – echte Maus über konexp.device.KoneXP (write() mit Backup/Verify/Auto-Restore)
  DemoBackend   – Werksdaten + synthetisches P3, Writes nur im Speicher
"""
import datetime
import json
import os
import threading
import time
from dataclasses import dataclass

from .. import defaults
from ..device import SEL_SETTINGS, KoneXP, KoneXPError, checksum_ok
from ..i18n import tr
from ..functions import MACRO_MODES, NAMES, describe
from ..reports import (BUTTONS, DPI_STEP, EFFECTS, LED_COUNT, N_BUTTONS, POLLING_HZ, SLEEP_EFFECTS,
                       Advanced, Buttons, Settings)
from .hidkeys import shortcut_text

from ..paths import BACKUP_DIR, RES_DIR, UDEV_RULE  # noqa: F401 (Re-Export für GUI-Module)

NPROFILES = 5
R06, R07, R11 = 0x06, 0x07, 0x11
EASY_SHIFT = (0x00, 0x00, 0x01, 0x0a)
EASY_SHIFT_KEY = 13
DISABLED = (0, 0, 0, 0)
DCU_MODES = {0: 'Very Low', 1: 'Low', 2: tr('kalibriert (Custom)')}
EASY_AIM_MIN, EASY_AIM_MAX = 100, 19000

UDEV_HINT = tr(
    'Zugriff auf die Maus fehlt. udev-Regel installieren:\n'
    '  sudo cp {rule} /etc/udev/rules.d/\n'
    '  sudo udevadm control --reload && sudo udevadm trigger\n'
    'Danach Maus neu einstecken.').format(rule=UDEV_RULE)

# --- LEDs -------------------------------------------------------------------
# Index → Plugin-Bild / AIMO-Gitter (Spalte, Zeile) siehe docs/PROTOCOL.md „LEDs“.
# Gitterspalten 0–4 liegen links der Mittelachse (Rad/DPI = Spalte 5), 6–10 rechts
# (bestätigt durch die Lage der Plugin-Bilder LED-01..08 links, LED-09..16 rechts).
LED_IMAGES = ['LED-02', 'LED-01', 'LED-04', 'LED-03', 'LED-06', 'LED-05', 'LED-08', 'LED-07',
              'LED_I1', 'LED_J1', 'LED-10', 'LED-09', 'LED-12', 'LED-11', 'LED-14', 'LED-13',
              'LED-16', 'LED-15', 'Wheel-LED', 'DPI_LED']
LED_GRID = ([(i // 2, i % 2) for i in range(8)] + [(4, 0), (6, 0)]
            + [(7 + (i - 10) // 2, (i - 10) % 2) for i in range(10, 18)] + [(5, 0), (5, 1)])
LED_WHEEL, LED_DPI = 18, 19
LED_GROUPS = {
    tr('alle'): list(range(LED_COUNT)),
    tr('Leiste links'): list(range(0, 9)),
    tr('Leiste rechts'): list(range(9, 18)),
    tr('Rad'): [LED_WHEEL],
    tr('DPI-LED'): [LED_DPI],
}


def led_label(i):
    if i == LED_WHEEL:
        return tr('Mausrad')
    if i == LED_DPI:
        return tr('DPI-LED')
    side = tr('links') if i < 9 else tr('rechts')
    col, row = LED_GRID[i]
    return tr('Leiste {side}, Spalte {col}, {row}').format(side=side, col=col,
                                                           row=tr('vorn') if row == 0 else tr('hinten'))


# --- Tasten-Funktionen --------------------------------------------------------

TYPE_GROUPS = {
    0x00: tr('Allgemein'), 0x01: tr('Maus / Browser'), 0x02: tr('DPI / Easy-Aim'), 0x03: tr('Multimedia'),
    0x04: tr('Navigation / Modifier'), 0x05: tr('System'), 0x08: tr('Profile / Beleuchtung'),
    0x09: tr('Easy-Wheel'), 0x0a: tr('Easy-Shift'), 0x0b: tr('Host-Funktionen (wirken unter Linux nicht)'),
}


def is_host(entry):
    return entry[3] == 0x0b


def entry_text(entry):
    """Klartext für einen 0x07-Eintrag [b0, b1, b2, typ]."""
    b0, b1, b2, typ = entry
    if typ == 0x06:
        return tr('Shortcut {keys}').format(keys=shortcut_text(b1, b2))
    if typ == 0x07:
        return tr('Makro ({mode})').format(mode=MACRO_MODES.get(b2, tr('Modus {n}').format(n=b2)))
    text = describe(entry)
    if typ == 0x0b:
        text = tr('{name} – wirkt unter Linux nicht').format(name=text)
    return text


def function_catalog():
    """[(Gruppenname, [(entry, Name), …]), …] aus functions.NAMES, nach typ gruppiert."""
    groups = {}
    for (typ, b2), name in sorted(NAMES.items()):
        entry = (0, 0, b2, typ)
        if typ == 0x0b:
            name = tr('{name} – wirkt unter Linux nicht').format(name=name)
        groups.setdefault(typ, []).append((entry, name))
    return [(TYPE_GROUPS.get(t, tr('typ 0x{t:02x}').format(t=t)), items) for t, items in sorted(groups.items())]


def easy_aim_entry(dpi):
    if not (EASY_AIM_MIN <= dpi <= EASY_AIM_MAX and dpi % DPI_STEP == 0):
        raise ValueError(tr('Easy-Aim: {lo}..{hi} in {step}er-Schritten').format(
            lo=EASY_AIM_MIN, hi=EASY_AIM_MAX, step=DPI_STEP))
    hi, lo = (dpi // DPI_STEP).to_bytes(2, 'big')
    return (hi, lo, 0x0c, 0x02)


def shortcut_entry(usage, mods):
    if not 0 < usage <= 0xff or not 0 <= mods <= 0x0f:
        raise ValueError(tr('ungültiger Shortcut'))
    return (0, usage, mods, 0x06)


# --- Feldkarten für den Diff --------------------------------------------------

def _hex(b):
    return b.hex(' ')


def _dpi(b):
    return f'{int.from_bytes(b, "little") * DPI_STEP} DPI'


def _mask(b):
    on = [str(i + 1) for i in range(5) if b[0] >> i & 1]
    return tr('Stufen') + ' ' + (','.join(on) or '–') + (f' (0x{b[0]:02x})' if b[0] & 0xe0 else '')


def _onoff(b):
    return (tr('an') if b[0] & 1 else tr('aus')) + (f' (0x{b[0]:02x})' if b[0] & 0xfe else '')


def _polling(b):
    return f'{POLLING_HZ[b[0]]} Hz' if b[0] < len(POLLING_HZ) else f'0x{b[0]:02x}'


def _effect(b):
    return EFFECTS.get(b[0], tr('unbekannt ({n})').format(n=b[0]))


def _sleep(b):
    return SLEEP_EFFECTS.get(b[0], tr('unbekannt ({n})').format(n=b[0]))


def _timeout(b):
    return tr('aus') if b[0] == 0 else str(b[0])


def _argb(b):
    return f'#{b[1]:02x}{b[2]:02x}{b[3]:02x} α={b[0]}'


def _dec(b):
    return str(b[0])


def _stage(b):
    return tr('Stufe {n}').format(n=b[0] + 1)


FIELDS06 = [
    (0x03, 1, tr('unbekannt 0x03 (Sensitivity X?)'), _hex),
    (0x04, 1, tr('unbekannt 0x04 (Sensitivity Y?)'), _hex),
    (0x05, 1, tr('DPI-Stufen aktiv'), _mask),
    (0x06, 1, tr('aktive DPI-Stufe'), _stage),
    *[(0x07 + 2 * i, 2, tr('DPI Stufe {n} (X)').format(n=i + 1), _dpi) for i in range(5)],
    *[(0x11 + 2 * i, 2, tr('DPI Stufe {n} (Y)').format(n=i + 1), _dpi) for i in range(5)],
    (0x1b, 1, tr('Angle Snapping'), _onoff),
    (0x1c, 1, tr('unbekannt 0x1c'), _hex),
    (0x1d, 1, tr('Polling-Rate'), _polling),
    (0x1e, 1, tr('Lichteffekt'), _effect),
    (0x1f, 1, tr('Effekt-Geschwindigkeit'), _dec),
    (0x20, 1, tr('Helligkeit'), _dec),
    (0x21, 1, tr('LED-Timeout (Wert)'), _timeout),
    (0x22, 1, tr('Effekt nach Timeout'), _sleep),
    (0x23, 1, tr('Timeout-Flag 0x23'), _hex),
]
for _i in range(LED_COUNT):
    _o = 0x24 + 6 * _i
    FIELDS06 += [(_o, 1, tr('LED {i} Byte +0').format(i=_i), _hex),
                 (_o + 1, 4, tr('LED {i} Farbe ({label})').format(i=_i, label=led_label(_i)), _argb),
                 (_o + 5, 1, tr('LED {i} Byte +5').format(i=_i), _hex)]
FIELDS06 += [
    (0x9c, 1, tr('Profilfarbe aktiv'), _hex),
    (0x9d, 1, tr('unbekannt 0x9d'), _hex),
    (0x9e, 4, tr('Profilfarbe'), _argb),
    (0xa2, 1, tr('Tasten-Preset-Index'), _hex),
    (0xa3, 1, tr('AIMO-Parameter'), _hex),
    (0xa4, 1, tr('DPI-Stufen-Flag 0xa4'), _hex),
    (0xa5, 1, tr('unbekannt 0xa5'), _hex),
    (0xa6, 6, tr('Reserve 0xa6–0xab'), _hex),
]


def _entry_fmt(b):
    return entry_text(tuple(b))


FIELDS07 = [(3 + 4 * (k + (N_BUTTONS if sh else 0)), 4,
             tr('Taste {n} „{name}“ ({layer})').format(
                 n=k + 1, name=BUTTONS[k], layer=tr('Easy-Shift') if sh else tr('normal')), _entry_fmt)
            for sh in (False, True) for k in range(N_BUTTONS)]

FIELDS11 = [(0x02, 1, tr('Debounce (ms)'), _dec)]

FIELDS = {R06: FIELDS06, R07: FIELDS07, R11: FIELDS11}

# Bytes ohne bekannte Bedeutung (Expertenansicht, read-only)
UNKNOWN06 = [(0x03, tr('Sensitivity X? (unbekannt)')), (0x04, tr('Sensitivity Y? (unbekannt)')),
             (0x1c, tr('unbekannt')), (0x23, tr('Timeout-Flag (GUI setzt 0)')), (0x9c, tr('Profilfarbe aktiv?')),
             (0x9d, tr('unbekannt (Intensität?)')), (0xa2, tr('Tasten-Preset-Index')),
             (0xa3, tr('AIMO-Parameter')), (0xa4, tr('DPI-Stufen-Flag (Auto?)')), (0xa5, tr('unbekannt'))]


@dataclass
class Change:
    profile: object  # int oder None (global)
    report: int
    field: str
    old: str
    new: str

    @property
    def profile_label(self):
        return tr('global') if self.profile is None else f'P{self.profile + 1}'


def diff_report(rid, old, new):
    """Feldweiser Diff zweier Reports (Checksumme ignoriert). Liefert [(Feld, alt, neu)]."""
    changes, covered = [], set()
    for off, n, name, fmt in FIELDS.get(rid, []):
        covered.update(range(off, off + n))
        a, b = old[off:off + n], new[off:off + n]
        if a != b:
            changes.append((name, fmt(a), fmt(b)))
    for off in range(3, len(old) - 2):
        if off not in covered and old[off] != new[off]:
            changes.append((tr('Byte 0x{off:02x}').format(off=off), f'{old[off]:02x}', f'{new[off]:02x}'))
    return changes


# --- Config -----------------------------------------------------------------

@dataclass
class Snapshot:
    """Rohdaten eines vollständigen Lesevorgangs."""
    r05: bytes
    r06: list
    r07: list
    r11: bytes
    r0f: object = None  # bytes oder None, wenn nicht lesbar

    @property
    def active(self):
        return self.r05[2]


class Config:
    """Gerätezustand (orig) + bearbeiteter Zustand (Settings/Buttons/Advanced-Objekte)."""

    def __init__(self, snap):
        self.snapshot = snap
        self.active = snap.active
        self.r0f = snap.r0f
        self.orig = {}
        for p in range(NPROFILES):
            self.orig[(R06, p)] = bytes(snap.r06[p])
            self.orig[(R07, p)] = bytes(snap.r07[p])
        self.orig[(R11, None)] = bytes(snap.r11)
        self.settings = [Settings(snap.r06[p]) for p in range(NPROFILES)]
        self.buttons = [Buttons(snap.r07[p]) for p in range(NPROFILES)]
        self.advanced = Advanced(snap.r11)

    # Schlüssel in Swarm-Schreibreihenfolge: je Profil 0x07, dann 0x06; zuletzt 0x11
    KEYS = [(rid, p) for p in range(NPROFILES) for rid in (R07, R06)] + [(R11, None)]

    def obj(self, key):
        rid, p = key
        if rid == R06:
            return self.settings[p]
        if rid == R07:
            return self.buttons[p]
        return self.advanced

    def current(self, key):
        return self.obj(key).to_bytes()

    def is_key_dirty(self, key):
        return bytes(self.obj(key).raw[:-2]) != self.orig[key][:-2]

    def dirty_keys(self):
        return [k for k in self.KEYS if self.is_key_dirty(k)]

    @property
    def dirty(self):
        return bool(self.dirty_keys())

    def profile_dirty(self, p):
        return self.is_key_dirty((R06, p)) or self.is_key_dirty((R07, p))

    def changed_offsets(self, key):
        cur, old = self.obj(key).raw, self.orig[key]
        return {i for i in range(len(old) - 2) if cur[i] != old[i]}

    def changes(self):
        out = []
        for key in self.dirty_keys():
            rid, p = key
            for field, a, b in diff_report(rid, self.orig[key], bytes(self.obj(key).raw)):
                out.append(Change(p, rid, field, a, b))
        return out

    def write_plan(self):
        return [(k, self.current(k)) for k in self.dirty_keys()]

    def mark_written(self, key, data):
        self.orig[key] = bytes(data)

    def revert(self, key=None):
        keys = [key] if key else self.KEYS
        for k in keys:
            rid, p = k
            cls = {R06: Settings, R07: Buttons, R11: Advanced}[rid]
            obj = cls(self.orig[k])
            if rid == R06:
                self.settings[p] = obj
            elif rid == R07:
                self.buttons[p] = obj
            else:
                self.advanced = obj

    # --- Komfort-Operationen ---------------------------------------------

    def dpi_mismatch(self, p):
        s = self.settings[p]
        return [i for i in range(5) if s.dpi(i) != s.dpi(i, 'y')]

    def align_y(self, p):
        s = self.settings[p]
        for i in range(5):
            s.raw[0x11 + 2 * i:0x13 + 2 * i] = s.raw[0x07 + 2 * i:0x09 + 2 * i]

    def set_leds(self, p, leds, argb):
        a, r, g, b = argb
        for i in leds:
            self.settings[p].set_led(i, r, g, b, a)

    def set_button(self, p, k, shift, entry):
        """Setzt Eintrag; liefert Hinweise (Swarm-Regel: Easy-Shift auf Taste k → k (Shift) = Disabled)."""
        notes = []
        b = self.buttons[p]
        b.set_entry(k, tuple(entry), shift)
        if not shift and entry[3] == 0x0a and b.entry(k, True) != DISABLED:
            b.set_entry(k, DISABLED, True)
            notes.append(tr('Taste {n} (Easy-Shift-Ebene) auf „Deaktiviert“ gesetzt (Easy-Shift-Regel).')
                         .format(n=k + 1))
        return notes

    def easy_shift_ok(self, p):
        return self.buttons[p].entry(EASY_SHIFT_KEY)[3] == 0x0a

    def load_factory(self, p):
        """Profil p im Editor auf Werkswerte setzen (0x06 + 0x07). Schreiben erst über Übernehmen."""
        self.settings[p] = Settings(defaults.settings(p))
        self.buttons[p] = Buttons(defaults.buttons(p))

    # --- Backup ----------------------------------------------------------

    def backup_dict(self):
        return {
            'format': 'konexp-backup', 'version': 1,
            'created': datetime.datetime.now().isoformat(timespec='seconds'),
            'r05': self.snapshot.r05.hex(),
            'r06': [self.orig[(R06, p)].hex() for p in range(NPROFILES)],
            'r07': [self.orig[(R07, p)].hex() for p in range(NPROFILES)],
            'r11': self.orig[(R11, None)].hex(),
            'r0f': self.r0f.hex() if self.r0f else None,
        }

    def apply_backup(self, d):
        """Backup in den Editor laden (validiert). Schreiben erst über Übernehmen."""
        s, b, a = parse_backup(d)
        self.settings, self.buttons, self.advanced = s, b, a


def parse_backup(d):
    if d.get('format') != 'konexp-backup':
        raise ValueError(tr('keine konexp-Backup-Datei'))
    settings, buttons = [], []
    for p in range(NPROFILES):
        for rid, cls, lst in ((R06, Settings, settings), (R07, Buttons, buttons)):
            raw = bytes.fromhex(d[f'r{rid:02x}'][p])
            obj = cls(raw)
            if obj.raw[2] != p:
                raise ValueError(tr('Report 0x{rid:02x} an Position {p} gehört zu Profil {q}').format(
                    rid=rid, p=p, q=obj.raw[2]))
            if not checksum_ok(raw):
                raise ValueError(tr('Report 0x{rid:02x} P{n}: Checksumme falsch').format(rid=rid, n=p + 1))
            lst.append(obj)
    raw = bytes.fromhex(d['r11'])
    adv = Advanced(raw)
    if not checksum_ok(raw):
        raise ValueError(tr('Report 0x11: Checksumme falsch'))
    return settings, buttons, adv


def save_backup(config, filename):
    with open(filename, 'w') as f:
        json.dump(config.backup_dict(), f, indent=1)


def load_backup(filename):
    with open(filename) as f:
        return json.load(f)


# --- Backends -----------------------------------------------------------------

def _noop(*_):
    pass


class DeviceBackend:
    """Echte Maus. Alle Zugriffe serialisiert über einen Lock (Worker-Thread + Poll-Timer)."""
    name = tr('Maus')
    demo = False

    def __init__(self, node=None, backup_dir=BACKUP_DIR):
        self.node, self.backup_dir = node, backup_dir
        self.dev = None
        self.lock = threading.Lock()

    def _open(self):
        if self.dev is None:
            self.dev = KoneXP(self.node, backup_dir=self.backup_dir)
        return self.dev

    def close(self):
        if self.dev is not None:
            try:
                self.dev.close()
            finally:
                self.dev = None

    def _guard(self, fn):
        try:
            return fn()
        except OSError as e:
            self.close()
            raise KoneXPError(tr('E/A-Fehler: {err}').format(err=e)) from e

    def read_all(self, progress=_noop):
        with self.lock:
            return self._guard(lambda: self._read_all(progress))

    def _read_all(self, progress):
        dev = self._open()
        n, step = 2 * NPROFILES + 3, 0
        progress(step, n, tr('aktives Profil (0x05)'))
        r05 = dev.get(0x05)
        r06, r07 = [], []
        for p in range(NPROFILES):
            step += 1
            progress(step, n, tr('P{n} Einstellungen (0x06)').format(n=p + 1))
            r06.append(dev.read_settings(p))
            step += 1
            progress(step, n, tr('P{n} Tasten (0x07)').format(n=p + 1))
            r07.append(dev.read_buttons(p))
        step += 1
        progress(step, n, tr('Debounce (0x11)'))
        r11 = dev.get(0x11)
        try:
            r0f = dev.get(0x0f)
        except OSError:
            r0f = None
        dev.select(r05[2], SEL_SETTINGS)  # GET 0x06 ohne Select liefert wieder das aktive Profil
        progress(n, n, tr('fertig'))
        return Snapshot(r05, r06, r07, r11, r0f)

    def write(self, data):
        with self.lock:
            return self._guard(lambda: self._open().write(data))

    def set_active_profile(self, p):
        with self.lock:
            self._guard(lambda: self._open().set_active_profile(p))

    def read_report(self, key):
        """Aktuellen Gerätestand eines Reports lesen (für den Merge vor dem Schreiben)."""
        rid, p = key
        with self.lock:
            dev = self._guard(self._open)
            if rid == R06:
                return self._guard(lambda: dev.read_settings(p))
            if rid == R07:
                return self._guard(lambda: dev.read_buttons(p))
            return self._guard(lambda: dev.get(rid))

    def poll_active(self):
        """Nicht blockierend: None, wenn gerade ein Worker läuft oder die Maus fehlt."""
        if self.dev is None or not self.lock.acquire(blocking=False):
            return None
        try:
            return self.dev.active_profile()
        except OSError:
            return None
        finally:
            self.lock.release()


def demo_snapshot():
    """Werksprofile plus ein synthetisch angepasstes P3 (aktiv), damit alle Ansichten etwas zeigen."""
    r06 = [defaults.settings(p) for p in range(NPROFILES)]
    r07 = [defaults.buttons(p) for p in range(NPROFILES)]
    s = Settings(r06[2])
    s.raw[0x0d:0x0f] = (1200 // DPI_STEP).to_bytes(2, 'little')  # Stufe 4: X 1200, Y bleibt 1600
    s.dpi_active = 3
    s.angle_snapping = True
    s.effect = 9
    r06[2] = s.to_bytes()
    b = Buttons(r07[2])
    for k, shift, e in ((7, False, (0, 0, 0x06, 0x03)),    # Ton aus
                        (8, False, (0, 0x48, 0, 0x06)),     # Pause
                        (11, False, (0, 0x06, 0x01, 0x06)), # Strg+C
                        (12, False, (0, 0, 0x03, 0x04)),    # Pos1
                        (14, False, (0, 0, 0x01, 0x07)),    # Makro, solange gedrückt
                        (7, True, (0, 0, 0x02, 0x02)),      # DPI Up
                        (8, True, (0, 0, 0x03, 0x02))):     # DPI Down
        b.set_entry(k, e, shift)
    r07[2] = b.to_bytes()
    return Snapshot(bytes([0x05, 0x04, 0x02, 0x05]), r06, r07, bytes.fromhex(defaults.ADVANCED_HEX),
                    bytes.fromhex('0f0600000000'))


class DemoBackend:
    """Ohne Maus: Demo-Daten als Gerät, Writes nur im Speicher."""
    name = tr('Demo')
    demo = True

    def __init__(self, delay=0.05):
        self.delay = delay
        self.snap = demo_snapshot()
        self.lock = threading.Lock()
        self.writes = []

    def close(self):
        pass

    def read_all(self, progress=_noop):
        n = 2 * NPROFILES + 3
        for i in range(n):
            progress(i, n, tr('Demo-Daten'))
            time.sleep(self.delay / 4)
        s = self.snap
        return Snapshot(s.r05, list(s.r06), list(s.r07), s.r11, s.r0f)

    def write(self, data):
        from ..device import CHECKSUMMED, WRITABLE, with_checksum
        rid = data[0]
        if rid not in WRITABLE:
            raise KoneXPError(tr('Report 0x{rid:02x} ist gesperrt').format(rid=rid))
        if rid in CHECKSUMMED:
            data = with_checksum(data)
        time.sleep(self.delay)
        self.writes.append(bytes(data))
        if rid == R06:
            self.snap.r06[data[2]] = bytes(data)
        elif rid == R07:
            self.snap.r07[data[2]] = bytes(data)
        elif rid == R11:
            self.snap.r11 = bytes(data)
        return bytes(data)

    def set_active_profile(self, p):
        self.snap.r05 = bytes([0x05, 0x04, p, 0x05])

    def read_report(self, key):
        rid, p = key
        return {R06: lambda: self.snap.r06[p], R07: lambda: self.snap.r07[p], R11: lambda: self.snap.r11}[rid]()

    def poll_active(self):
        return self.snap.r05[2]


def merge_onto(fresh, orig, cur):
    """Überträgt nur die im Editor geänderten Bytes (cur != orig) auf den frischen Gerätestand.

    Verhindert, dass ein Write Änderungen zurücksetzt, die seit dem Laden an der Maus passiert sind
    (z.B. DPI-Stufe per Taste). Checksumme (letzte 2 B) wird vom Transport neu berechnet.
    """
    out = bytearray(fresh)
    for i in range(len(orig) - 2):
        if cur[i] != orig[i]:
            out[i] = cur[i]
    return bytes(out)


def run_plan(backend, plan, progress=_noop, base=None):
    """Schreibt plan [(key, bytes)] der Reihe nach. Bricht beim ersten Fehler ab.

    Mit `base` (key -> beim Laden gelesene Bytes) wird vor jedem Write frisch gelesen und nur
    die geänderten Bytes übertragen (merge_onto).

    Rückgabe: (geschrieben [(key, rücklese-bytes)], Fehlertext oder None)
    """
    done = []
    for i, (key, data) in enumerate(plan):
        rid, p = key
        label = f'0x{rid:02x}' + ('' if p is None else f' P{p + 1}')
        progress(i, len(plan), tr('schreibe {label}').format(label=label))
        try:
            if base is not None and key in base:
                data = merge_onto(backend.read_report(key), base[key], data)
            back = backend.write(data)
        except (KoneXPError, OSError, ValueError) as e:
            return done, f'{label}: {e}'
        done.append((key, back if back is not None else data))
    progress(len(plan), len(plan), tr('fertig'))
    return done, None
