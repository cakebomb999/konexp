"""HID-Usages (Keyboard-Page 0x07) für den Shortcut-Dialog und die Anzeige von typ-06-Einträgen."""
import string

from ..functions import MODIFIERS
from ..i18n import tr

USAGES = {}
for _i, _c in enumerate(string.ascii_uppercase):
    USAGES[0x04 + _i] = _c
for _i, _c in enumerate('1234567890'):
    USAGES[0x1e + _i] = _c
USAGES.update({
    0x28: 'Enter', 0x29: 'Esc', 0x2a: tr('Rücktaste'), 0x2b: 'Tab', 0x2c: tr('Leertaste'),
    0x2d: 'ß / -', 0x2e: '´ / =', 0x2f: 'Ü / [', 0x30: '+ / ]', 0x31: '# / \\', 0x33: 'Ö / ;',
    0x34: 'Ä / \'', 0x35: '^ / `', 0x36: ',', 0x37: '.', 0x38: '- / /', 0x39: tr('Feststell'),
    **{0x3a + i: f'F{i + 1}' for i in range(12)},
    0x46: tr('Druck'), 0x47: tr('Rollen'), 0x48: 'Pause', 0x49: tr('Einfg'), 0x4a: tr('Pos1'), 0x4b: tr('Bild hoch'),
    0x4c: tr('Entf'), 0x4d: tr('Ende'), 0x4e: tr('Bild runter'), 0x4f: tr('Pfeil rechts'), 0x50: tr('Pfeil links'),
    0x51: tr('Pfeil runter'), 0x52: tr('Pfeil hoch'), 0x53: tr('Num'),
    0x54: tr('Num {key}').format(key='/'), 0x55: tr('Num {key}').format(key='*'),
    0x56: tr('Num {key}').format(key='-'), 0x57: tr('Num {key}').format(key='+'),
    0x58: tr('Num Enter'),
    **{0x59 + i: tr('Num {key}').format(key=i + 1) for i in range(9)},
    0x62: tr('Num {key}').format(key=0), 0x63: tr('Num {key}').format(key=','),
    0x64: '< > |', 0x65: tr('Menü'),
    **{0x68 + i: f'F{i + 13}' for i in range(12)},
})

USAGES.update({0xe0 + i: n for i, n in enumerate((tr('Strg links'), tr('Shift links'), tr('Alt links'), tr('Win links'),
                                                  tr('Strg rechts'), tr('Shift rechts'), tr('AltGr'),
                                                  tr('Win rechts')))})
# Nur im Makro: Maustasten (reports.MOUSE_KEYS)
MOUSE = dict(zip((0xf0, 0xf1, 0xf2, 0xf3, 0xf4), (tr('Maus links'), tr('Maus rechts'), tr('Maus Mitte'),
                                                  tr('Maus Taste 4'), tr('Maus Taste 5'))))

# Linux-evdev-Keycode -> HID-Usage, erzeugt aus linux/input-event-codes.h und der HID-Usage-Tabelle (Page 0x07).
# Qt liefert unter X11 und Wayland nativeScanCode = evdev + 8.
EVDEV_HID = {
    1: 0x29, 2: 0x1e, 3: 0x1f, 4: 0x20, 5: 0x21, 6: 0x22, 7: 0x23, 8: 0x24, 9: 0x25, 10: 0x26, 11: 0x27, 12: 0x2d,
    13: 0x2e, 14: 0x2a, 15: 0x2b, 16: 0x14, 17: 0x1a, 18: 0x08, 19: 0x15, 20: 0x17, 21: 0x1c, 22: 0x18, 23: 0x0c,
    24: 0x12, 25: 0x13, 26: 0x2f, 27: 0x30, 28: 0x28, 29: 0xe0, 30: 0x04, 31: 0x16, 32: 0x07, 33: 0x09, 34: 0x0a,
    35: 0x0b, 36: 0x0d, 37: 0x0e, 38: 0x0f, 39: 0x33, 40: 0x34, 41: 0x35, 42: 0xe1, 43: 0x31, 44: 0x1d, 45: 0x1b,
    46: 0x06, 47: 0x19, 48: 0x05, 49: 0x11, 50: 0x10, 51: 0x36, 52: 0x37, 53: 0x38, 54: 0xe5, 55: 0x55, 56: 0xe2,
    57: 0x2c, 58: 0x39, 59: 0x3a, 60: 0x3b, 61: 0x3c, 62: 0x3d, 63: 0x3e, 64: 0x3f, 65: 0x40, 66: 0x41, 67: 0x42,
    68: 0x43, 69: 0x53, 70: 0x47, 71: 0x5f, 72: 0x60, 73: 0x61, 74: 0x56, 75: 0x5c, 76: 0x5d, 77: 0x5e, 78: 0x57,
    79: 0x59, 80: 0x5a, 81: 0x5b, 82: 0x62, 83: 0x63, 86: 0x64, 87: 0x44, 88: 0x45, 96: 0x58, 97: 0xe4, 98: 0x54,
    99: 0x46, 100: 0xe6, 102: 0x4a, 103: 0x52, 104: 0x4b, 105: 0x50, 106: 0x4f, 107: 0x4d, 108: 0x51, 109: 0x4e,
    110: 0x49, 111: 0x4c, 119: 0x48, 125: 0xe3, 126: 0xe7, 127: 0x65, 183: 0x68, 184: 0x69, 185: 0x6a, 186: 0x6b,
    187: 0x6c, 188: 0x6d, 189: 0x6e, 190: 0x6f, 191: 0x70, 192: 0x71, 193: 0x72, 194: 0x73,
}


def key_name(usage):
    return MOUSE.get(usage) or USAGES.get(usage, f'HID 0x{usage:02x}')


def hid_from_scancode(native):
    return EVDEV_HID.get(native - 8)


def shortcut_text(usage, mods):
    parts = [n for bit, n in MODIFIERS if mods & bit]
    return '+'.join(parts + [key_name(usage)])
