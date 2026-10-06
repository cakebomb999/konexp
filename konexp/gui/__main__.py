"""python3 -m konexp.gui [--demo] [--node /dev/hidrawN] [--quit-after MS] [--screenshot DATEI]"""
import argparse
import sys


def main(argv=None):
    ap = argparse.ArgumentParser(prog='python3 -m konexp.gui', description='Kone-XP-Konfiguration')
    ap.add_argument('--demo', action='store_true', help='ohne Maus: Werksdaten + Beispielprofil, Writes nur im Speicher')
    ap.add_argument('--node', help='hidraw-Gerät (Standard: automatisch, Interface 3)')
    ap.add_argument('--quit-after', type=int, metavar='MS', help='nach MS Millisekunden beenden (Tests)')
    ap.add_argument('--screenshot', metavar='DATEI', help='vor dem Beenden Screenshot speichern (mit --quit-after)')
    args = ap.parse_args(argv)

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .model import DemoBackend, DeviceBackend

    app = QApplication(sys.argv[:1])
    app.setApplicationName('Kone XP')
    backend = DemoBackend() if args.demo else DeviceBackend(args.node)
    win = MainWindow(backend)
    win.show()
    if args.quit_after:
        def finish():
            if args.screenshot:
                win.grab().save(args.screenshot)
            if win.config is not None:
                win.config.revert()  # kein Nachfragen beim Test-Beenden
            win.close()
            app.quit()
        QTimer.singleShot(args.quit_after, finish)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
