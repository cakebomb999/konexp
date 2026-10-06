"""Tastenfunktionen für Report-0x07-Einträge [b0, b1, b2, typ].

Quelle: docs/PROTOCOL.md (Swarm-Plugin-Menübuilder, Funktions-ID = typ<<8 | b2).
Typ 0x0b sind Host-Funktionen: Die Maus sendet nur ein Event (f1), ausgeführt hat sie unter
Windows Swarm. Unter Linux passiert ohne eigenen Daemon nichts.
"""

NAMES = {
    (0x00, 0x00): 'Deaktiviert',
    (0x01, 0x01): 'Linksklick', (0x01, 0x02): 'Rechtsklick (Menü)', (0x01, 0x03): 'Mittelklick',
    (0x01, 0x04): 'Doppelklick', (0x01, 0x05): 'Browser vor', (0x01, 0x06): 'Browser zurück',
    (0x01, 0x07): 'Tilt links', (0x01, 0x08): 'Tilt rechts', (0x01, 0x09): 'Scroll hoch',
    (0x01, 0x0a): 'Scroll runter',
    (0x02, 0x01): 'DPI Cycle', (0x02, 0x02): 'DPI Up', (0x02, 0x03): 'DPI Down',
    **{(0x02, 0x07 + i): f'Easy-Aim DPI-Stufe {i + 1}' for i in range(5)},
    (0x02, 0x0d): 'Easy-Aim 200 DPI',
    (0x03, 0x02): 'Vorheriger Titel', (0x03, 0x03): 'Nächster Titel', (0x03, 0x04): 'Play/Pause',
    (0x03, 0x05): 'Stop', (0x03, 0x06): 'Ton aus', (0x03, 0x07): 'Lauter', (0x03, 0x08): 'Leiser',
    (0x03, 0x0b): 'Browser Suche', (0x03, 0x0c): 'Browser Stop', (0x03, 0x0d): 'Browser Neu laden',
    (0x03, 0x0e): 'Neuer Tab', (0x03, 0x0f): 'Neues Fenster', (0x03, 0x10): 'Computer',
    (0x03, 0x11): 'Rechner', (0x03, 0x12): 'E-Mail',
    (0x04, 0x03): 'Pos1', (0x04, 0x04): 'Ende', (0x04, 0x05): 'Bild hoch', (0x04, 0x06): 'Bild runter',
    (0x04, 0x07): 'Strg links', (0x04, 0x08): 'Shift links', (0x04, 0x09): 'Alt links',
    (0x05, 0x01): 'Herunterfahren', (0x05, 0x02): 'Ruhezustand', (0x05, 0x03): 'Aufwachen',
    (0x08, 0x01): 'Profile Cycle', (0x08, 0x02): 'Nächstes Profil', (0x08, 0x03): 'Vorheriges Profil',
    **{(0x08, 0x04 + i): f'Profil {i + 1}' for i in range(5)},
    (0x08, 0x0b): 'Helligkeit umschalten',
    (0x09, 0x03): 'Easy-Wheel DPI', (0x09, 0x04): 'Easy-Wheel Lautstärke',
    (0x09, 0x05): 'Easy-Wheel Alt-Tab', (0x09, 0x06): 'Easy-Wheel Task View',
    (0x0a, 0x01): 'Easy-Shift[+]',
    (0x0b, 0x08): 'Mikrofon stumm (Host)',
}

# Typen, deren Funktion auf der Maus selbst läuft (keine Host-Software nötig)
ON_DEVICE = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a}

MODIFIERS = ((1, 'Strg'), (2, 'Shift'), (4, 'Alt'), (8, 'Win'))
MACRO_MODES = {1: 'solange gedrückt', 2: 'bei Druck'}


def describe(entry):
    b0, b1, b2, typ = entry
    if typ == 0x06:
        mods = '+'.join(n for bit, n in MODIFIERS if b2 & bit)
        return f'Taste HID 0x{b1:02x}' + (f' mit {mods}' if mods else '')
    if typ == 0x07:
        return f'Makro ({MACRO_MODES.get(b2, b2)})'
    if typ == 0x02 and b2 == 0x0c:
        return f'Easy-Aim {int.from_bytes(bytes([b0, b1]), "big") * 50} DPI'
    if typ == 0x0b and (typ, b2) not in NAMES:
        return f'Host-Funktion 0x{b2:02x}'
    return NAMES.get((typ, b2), f'unbekannt typ 0x{typ:02x} b2 0x{b2:02x}')


def entry_for(typ, b2, b1=0, b0=0):
    return (b0, b1, b2, typ)
