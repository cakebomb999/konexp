"""Tastenfunktionen für Report-0x07-Einträge [b0, b1, b2, typ].

Quelle: docs/PROTOCOL.md (Swarm-Plugin-Menübuilder, Funktions-ID = typ<<8 | b2).
Typ 0x0b sind Host-Funktionen: Die Maus sendet nur ein Event (f1), ausgeführt hat sie unter
Windows Swarm. Unter Linux passiert ohne eigenen Daemon nichts.
"""
from .i18n import tr

NAMES = {
    (0x00, 0x00): tr('Deaktiviert'),
    (0x01, 0x01): tr('Linksklick'), (0x01, 0x02): tr('Rechtsklick (Menü)'), (0x01, 0x03): tr('Mittelklick'),
    (0x01, 0x04): tr('Doppelklick'), (0x01, 0x05): tr('Browser vor'), (0x01, 0x06): tr('Browser zurück'),
    (0x01, 0x07): tr('Tilt links'), (0x01, 0x08): tr('Tilt rechts'), (0x01, 0x09): tr('Scroll hoch'),
    (0x01, 0x0a): tr('Scroll runter'),
    (0x02, 0x01): 'DPI Cycle', (0x02, 0x02): 'DPI Up', (0x02, 0x03): 'DPI Down',
    **{(0x02, 0x07 + i): tr('Easy-Aim DPI-Stufe {n}').format(n=i + 1) for i in range(5)},
    (0x02, 0x0d): 'Easy-Aim 200 DPI',
    (0x03, 0x02): tr('Vorheriger Titel'), (0x03, 0x03): tr('Nächster Titel'), (0x03, 0x04): 'Play/Pause',
    (0x03, 0x05): tr('Stop'), (0x03, 0x06): tr('Ton aus'), (0x03, 0x07): tr('Lauter'), (0x03, 0x08): tr('Leiser'),
    (0x03, 0x0b): tr('Browser Suche'), (0x03, 0x0c): tr('Browser Stop'), (0x03, 0x0d): tr('Browser Neu laden'),
    (0x03, 0x0e): tr('Neuer Tab'), (0x03, 0x0f): tr('Neues Fenster'), (0x03, 0x10): tr('Computer'),
    (0x03, 0x11): tr('Rechner'), (0x03, 0x12): tr('E-Mail'),
    (0x04, 0x03): tr('Pos1'), (0x04, 0x04): tr('Ende'), (0x04, 0x05): tr('Bild hoch'),
    (0x04, 0x06): tr('Bild runter'),
    (0x04, 0x07): tr('Strg links'), (0x04, 0x08): tr('Shift links'), (0x04, 0x09): tr('Alt links'),
    (0x05, 0x01): tr('Herunterfahren'), (0x05, 0x02): tr('Ruhezustand'), (0x05, 0x03): tr('Aufwachen'),
    (0x08, 0x01): 'Profile Cycle', (0x08, 0x02): tr('Nächstes Profil'), (0x08, 0x03): tr('Vorheriges Profil'),
    **{(0x08, 0x04 + i): tr('Profil {n}').format(n=i + 1) for i in range(5)},
    (0x08, 0x0b): tr('Helligkeit umschalten'),
    (0x09, 0x03): 'Easy-Wheel DPI', (0x09, 0x04): tr('Easy-Wheel Lautstärke'),
    (0x09, 0x05): tr('Easy-Wheel Alt-Tab'), (0x09, 0x06): 'Easy-Wheel Task View',
    (0x0a, 0x01): 'Easy-Shift[+]',
    (0x0b, 0x08): tr('Mikrofon stumm (Host)'),
}

# Typen, deren Funktion auf der Maus selbst läuft (keine Host-Software nötig)
ON_DEVICE = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a}

MODIFIERS = ((1, tr('Strg')), (2, 'Shift'), (4, 'Alt'), (8, 'Win'))
MACRO_MODES = {1: tr('solange gedrückt'), 2: tr('bei Druck')}


def describe(entry):
    b0, b1, b2, typ = entry
    if typ == 0x06:
        mods = '+'.join(n for bit, n in MODIFIERS if b2 & bit)
        return (tr('Taste HID 0x{code:02x} mit {mods}').format(code=b1, mods=mods) if mods
                else tr('Taste HID 0x{code:02x}').format(code=b1))
    if typ == 0x07:
        return tr('Makro ({mode})').format(mode=MACRO_MODES.get(b2, b2))
    if typ == 0x02 and b2 == 0x0c:
        return tr('Easy-Aim {dpi} DPI').format(dpi=int.from_bytes(bytes([b0, b1]), 'big') * 50)
    if typ == 0x0b and (typ, b2) not in NAMES:
        return tr('Host-Funktion 0x{code:02x}').format(code=b2)
    return NAMES.get((typ, b2)) or tr('unbekannt typ 0x{typ:02x} b2 0x{code:02x}').format(typ=typ, code=b2)


def entry_for(typ, b2, b1=0, b0=0):
    return (b0, b1, b2, typ)
