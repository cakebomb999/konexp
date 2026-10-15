"""Kommandozeile: python3 -m konexp <befehl> …

  status                      alle Profile: aktive DPI-Stufe, DPI, Polling, Licht, DPI-/Profil-Tasten
  profile <0-4>               aktives Profil setzen
  dpi <profil> <stufe> <dpi>  DPI einer Stufe setzen (X und Y)
  dpi-active <profil> <stufe> aktive DPI-Stufe setzen
  restore <datei.bin>         gesichertes Backup zurückschreiben
  dump [datei.json]           Diagnose-Datei für ein GitHub-Issue (nur Lesen, auch für unbekannte Mäuse)
"""
import glob
import json
import os
import sys
import time

from .device import AIR_BLOCKS, AIR_DONGLE, KoneXPAir, KoneXPError, checksum_ok, open_device
from .functions import describe
from .i18n import tr
from .paths import BACKUP_DIR
from .reports import Buttons, Settings, button_names

DUMP_VENDORS = (0x1E7D, 0x10F5)  # ROCCAT, Turtle Beach
ISSUE_URL = 'https://github.com/cakebomb999/konexp/issues/new?template=device.yml'

USAGE = tr('''Kommandozeile: python3 -m konexp <befehl> …

  status                      alle Profile: aktive DPI-Stufe, DPI, Polling, Licht, DPI-/Profil-Tasten
  profile <0-4>               aktives Profil setzen
  dpi <profil> <stufe> <dpi>  DPI einer Stufe setzen (X und Y)
  dpi-active <profil> <stufe> aktive DPI-Stufe setzen
  restore <datei.bin>         gesichertes Backup zurückschreiben
  dump [datei.json]           Diagnose-Datei für ein GitHub-Issue (nur Lesen, auch für unbekannte Mäuse)
''')


def status(dev):
    active = dev.active_profile()
    print(f'{dev.NAME} ({dev.node})' + (' – ' + tr('nur Lesen') if dev.readonly else ''))
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
                name=button_names(s.air)[k], func=describe(b.entry(k)), shift=describe(b.entry(k, True))))
    dev.select(active, 0x80)


def _sysfs(node):
    d = f'/sys/class/hidraw/{os.path.basename(node)}/device'
    out = {}
    for name, mode in (('uevent', 'r'), ('report_descriptor', 'rb')):
        try:
            with open(f'{d}/{name}', mode) as f:
                data = f.read()
            out[name] = data.hex() if mode == 'rb' else data
        except OSError as e:
            out[name] = f'ERROR {e}'
    return out


def _hid_devices():
    """Alle hidraw-Knoten von ROCCAT und Turtle Beach, nur aus sysfs: braucht keine udev-Regel, sendet nichts."""
    out = {}
    for d in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        info = _sysfs(d)
        if any(f':{v:08X}:' in info['uevent'] for v in DUMP_VENDORS):
            out['/dev/' + os.path.basename(d)] = info
    return out


def dump(dev, path, error=None):
    """Diagnose-Datei: alle ROCCAT-/Turtle-Beach-Geräte (sysfs), dazu bei bekannter Maus alles, was konexp nutzt.
    Jeder Schritt einzeln, Fehler werden notiert."""
    out = {'format': 'konexp-dump', 'created': time.strftime('%Y-%m-%dT%H:%M:%S'), 'devices': _hid_devices()}
    if dev is None:
        out['error'] = error
    else:
        out.update({'model': dev.NAME, 'pid': f'{dev.pid:04x}', 'node': dev.node,
                    'init': getattr(dev, 'init_log', None)})
        _read(dev, out)
    with open(path, 'w') as f:
        json.dump(out, f, indent=1)
    errors = [k for k, v in out.items() if isinstance(v, str) and v.startswith('ERROR')
              or isinstance(v, dict) and not (v.get('header_ok', True) and v.get('checksum_ok', True))]
    print(tr('{path} gespeichert, {n} Fehler').format(path=path, n=len(errors)) + (f': {", ".join(errors)}' if errors else ''))
    print(tr('Neue Maus oder Problem? Issue öffnen und die Datei anhängen: {url}').format(url=ISSUE_URL))
    return 1 if errors else 0


def _read(dev, out):
    def step(key, fn):
        print(f'  {key} …', flush=True)
        try:
            v = fn()
            out[key] = v.hex() if isinstance(v, bytes) else v
        except (OSError, KoneXPError, ValueError, IndexError) as e:
            out[key] = f'ERROR {type(e).__name__}: {e}'

    air = isinstance(dev, KoneXPAir)

    def block(rid, p):
        # Air: Rohdaten ohne Prüfung lesen, damit auch unerwartete Antworten im Dump landen
        if air:
            cmd, size = AIR_BLOCKS[rid]
            raw = dev.read_block(cmd, p, size)
        else:
            raw = (dev.read_settings if rid == 0x06 else dev.read_buttons)(p)
        return {'hex': raw.hex(), 'header_ok': raw[:3] == bytes([rid, len(raw), p]), 'checksum_ok': checksum_ok(raw)}

    step('r05', lambda: dev.get(0x05))
    for p in range(5):
        step(f'r06_p{p}', lambda p=p: block(0x06, p))
        step(f'r07_p{p}', lambda p=p: block(0x07, p))
    step('r11', lambda: dev.get(0x11))
    step('r0f', lambda: dev.get(0x0f))
    if air:  # ganze 30-Byte-Antworten (Byte 3 = Status)
        for cmd in (0x45, 0x44, 0x4f, 0x43, 0x35):
            step(f'air_{cmd:02x}', lambda cmd=cmd: dev.query(cmd, 0, frame=True))
        step('firmware', dev.firmware)
        if dev.pid == AIR_DONGLE:
            for cmd in (0x13, 0x25):
                step(f'air_{cmd:02x}', lambda cmd=cmd: dev.query(cmd, 0, target=0, frame=True))
    else:
        step('r09', lambda: dev.get(0x09))
    step('select_active', lambda: dev.select(dev.active_profile(), 0x80))  # wie nach status


def main(argv=None):
    args = (argv or sys.argv[1:]) or ['status']
    cmd, rest = args[0], [int(a, 0) for a in args[1:] if a.lstrip('-').isdigit() or a.startswith('0x')]
    if cmd == 'dump':
        path = args[1] if len(args) > 1 else f'konexp-dump-{time.strftime("%Y%m%d-%H%M%S")}.json'
        try:
            dev = open_device(backup_dir=BACKUP_DIR)
        except KoneXPError as e:  # unbekannte Maus oder kein Zugriff: nur die Geräteliste speichern
            print(tr('Fehler: {err}').format(err=e), file=sys.stderr)
            return dump(None, path, str(e))
        with dev:
            return dump(dev, path)
    try:
        with open_device(backup_dir=BACKUP_DIR) as dev:
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
