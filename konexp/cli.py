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
from .i18n import tr
from .paths import BACKUP_DIR
from .reports import BUTTONS, Buttons, Settings

USAGE = tr('''Kommandozeile: python3 -m konexp <befehl> …

  status                      alle Profile: aktive DPI-Stufe, DPI, Polling, Licht, DPI-/Profil-Tasten
  profile <0-4>               aktives Profil setzen
  dpi <profil> <stufe> <dpi>  DPI einer Stufe setzen (X und Y)
  dpi-active <profil> <stufe> aktive DPI-Stufe setzen
  restore <datei.bin>         gesichertes Backup zurückschreiben
''')


def status(dev):
    active = dev.active_profile()
    print(tr('aktives Profil: {num} (Index {idx})').format(num=active + 1, idx=active))
    for p in range(5):
        s = Settings(dev.read_settings(p))
        b = Buttons(dev.read_buttons(p))
        dpis = [f'{s.dpi(i)}' + (f'/{s.dpi(i, "y")}' if s.dpi(i) != s.dpi(i, 'y') else '')
                + ('*' if i == s.dpi_active else '') + ('' if s.dpi_enabled[i] else '(aus)')
                for i in range(5)]
        mark = '>' if p == active else ' '
        print(tr('{mark}P{p}: DPI {dpis} | {hz} Hz | Angle Snapping {snap} | Effekt {effect}').format(
            mark=mark, p=p, dpis=' '.join(dpis), hz=s.polling_hz,
            snap=tr('an') if s.angle_snapping else tr('aus'), effect=s.effect))
        for k in (7, 8, 14):
            print(tr('      {name:<18} {func:<28} Easy-Shift: {shift}').format(
                name=BUTTONS[k], func=describe(b.entry(k)), shift=describe(b.entry(k, True))))
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
                print(tr('Profil {num} aktiv').format(num=rest[0]))
            elif cmd == 'dpi':
                p, stage, value = rest
                s = Settings(dev.read_settings(p))
                s.set_dpi(stage, value)
                dev.write(s.to_bytes())
                print(tr('P{p} Stufe {stage}: {value} DPI').format(p=p, stage=stage, value=value))
            elif cmd == 'dpi-active':
                p, stage = rest
                s = Settings(dev.read_settings(p))
                s.dpi_active = stage
                dev.write(s.to_bytes())
                print(tr('P{p}: aktive Stufe {stage} ({dpi} DPI)').format(p=p, stage=stage, dpi=s.dpi(stage)))
            elif cmd == 'restore':
                data = open(args[1], 'rb').read()
                dev.write(data)
                print(tr('{path} zurückgeschrieben').format(path=args[1]))
            else:
                print(USAGE)
                return 2
    except (KoneXPError, ValueError, IndexError) as e:
        print(tr('Fehler: {err}').format(err=e), file=sys.stderr)
        return 1
    return 0
