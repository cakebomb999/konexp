"""Kommandozeile: python3 -m konexp <befehl> …

  status                      alle Profile: aktive DPI-Stufe, DPI, Polling, Licht, DPI-/Profil-Tasten
  profile <0-4>               aktives Profil setzen
  dpi <profil> <stufe> <dpi>  DPI einer Stufe setzen (X und Y)
  dpi-active <profil> <stufe> aktive DPI-Stufe setzen
  restore <datei.bin>         gesichertes Backup zurückschreiben
"""
import sys

from .device import KoneXP, KoneXPError
from .functions import describe
from .paths import BACKUP_DIR
from .reports import BUTTONS, Buttons, Settings


def status(dev):
    active = dev.active_profile()
    print(f'aktives Profil: {active + 1} (Index {active})')
    for p in range(5):
        s = Settings(dev.read_settings(p))
        b = Buttons(dev.read_buttons(p))
        dpis = [f'{s.dpi(i)}' + (f'/{s.dpi(i, "y")}' if s.dpi(i) != s.dpi(i, 'y') else '')
                + ('*' if i == s.dpi_active else '') + ('' if s.dpi_enabled[i] else '(aus)')
                for i in range(5)]
        mark = '>' if p == active else ' '
        print(f'{mark}P{p}: DPI {" ".join(dpis)} | {s.polling_hz} Hz | Angle Snapping '
              f'{"an" if s.angle_snapping else "aus"} | Effekt {s.effect}')
        for k in (7, 8, 14):
            print(f'      {BUTTONS[k]:<18} {describe(b.entry(k)):<28} Easy-Shift: {describe(b.entry(k, True))}')
    dev.select(active, 0x80)


def main(argv=None):
    args = (argv or sys.argv[1:]) or ['status']
    cmd, rest = args[0], [int(a, 0) for a in args[1:] if a.lstrip('-').isdigit() or a.startswith('0x')]
    try:
        with KoneXP(backup_dir=BACKUP_DIR) as dev:
            if cmd == 'status':
                status(dev)
            elif cmd == 'profile':
                dev.set_active_profile(rest[0])
                print(f'Profil {rest[0]} aktiv')
            elif cmd == 'dpi':
                p, stage, value = rest
                s = Settings(dev.read_settings(p))
                s.set_dpi(stage, value)
                dev.write(s.to_bytes())
                print(f'P{p} Stufe {stage}: {value} DPI')
            elif cmd == 'dpi-active':
                p, stage = rest
                s = Settings(dev.read_settings(p))
                s.dpi_active = stage
                dev.write(s.to_bytes())
                print(f'P{p}: aktive Stufe {stage} ({s.dpi(stage)} DPI)')
            elif cmd == 'restore':
                data = open(args[1], 'rb').read()
                dev.write(data)
                print(f'{args[1]} zurückgeschrieben')
            else:
                print(__doc__)
                return 2
    except (KoneXPError, ValueError, IndexError) as e:
        print(f'Fehler: {e}', file=sys.stderr)
        return 1
    return 0
