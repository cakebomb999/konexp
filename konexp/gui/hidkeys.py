"""HID-Usages (Keyboard-Page 0x07) für den Shortcut-Dialog und die Anzeige von typ-06-Einträgen."""
import string

from ..functions import MODIFIERS

USAGES = {}
for _i, _c in enumerate(string.ascii_uppercase):
    USAGES[0x04 + _i] = _c
for _i, _c in enumerate('1234567890'):
    USAGES[0x1e + _i] = _c
USAGES.update({
    0x28: 'Enter', 0x29: 'Esc', 0x2a: 'Rücktaste', 0x2b: 'Tab', 0x2c: 'Leertaste',
    0x2d: 'ß / -', 0x2e: '´ / =', 0x2f: 'Ü / [', 0x30: '+ / ]', 0x31: '# / \\', 0x33: 'Ö / ;',
    0x34: 'Ä / \'', 0x35: '^ / `', 0x36: ',', 0x37: '.', 0x38: '- / /', 0x39: 'Feststell',
    **{0x3a + i: f'F{i + 1}' for i in range(12)},
    0x46: 'Druck', 0x47: 'Rollen', 0x48: 'Pause', 0x49: 'Einfg', 0x4a: 'Pos1', 0x4b: 'Bild hoch',
    0x4c: 'Entf', 0x4d: 'Ende', 0x4e: 'Bild runter', 0x4f: 'Pfeil rechts', 0x50: 'Pfeil links',
    0x51: 'Pfeil runter', 0x52: 'Pfeil hoch', 0x53: 'Num', 0x54: 'Num /', 0x55: 'Num *',
    0x56: 'Num -', 0x57: 'Num +', 0x58: 'Num Enter',
    **{0x59 + i: f'Num {i + 1}' for i in range(9)}, 0x62: 'Num 0', 0x63: 'Num ,',
    0x64: '< > |', 0x65: 'Menü',
    **{0x68 + i: f'F{i + 13}' for i in range(12)},
})


def key_name(usage):
    return USAGES.get(usage, f'HID 0x{usage:02x}')


def shortcut_text(usage, mods):
    parts = [n for bit, n in MODIFIERS if mods & bit]
    return '+'.join(parts + [key_name(usage)])
