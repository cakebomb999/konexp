"""Hintergrund-Ausführung für Geräte-Zugriffe (Laden ~2 s, Schreiben), damit die UI bedienbar bleibt."""
from PySide6.QtCore import QThread, Signal


class Task(QThread):
    """Führt fn(progress) im Thread aus. progress(i, n, text) → Signal im GUI-Thread."""
    progress = Signal(int, int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(lambda i, n, t: self.progress.emit(i, n, t))
        except Exception as e:  # noqa: BLE001 – jede Ausnahme als Meldung in die GUI
            self.failed.emit(f'{type(e).__name__}: {e}' if not str(e) else str(e))
            return
        self.done.emit(result)
