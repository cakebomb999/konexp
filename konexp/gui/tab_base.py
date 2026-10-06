"""Basisklasse der Tabs: hält Config + bearbeitetes Profil, meldet Änderungen."""
from contextlib import contextmanager

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget


class TabBase(QWidget):
    changed = Signal()
    TITLE = ''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.config = None
        self.profile = 0
        self.expert = False
        self._loading = False

    def set_context(self, config, profile):
        self.config, self.profile = config, profile
        self.refresh()

    def set_expert(self, on):
        self.expert = on
        self.refresh()

    @contextmanager
    def loading(self):
        old, self._loading = self._loading, True
        try:
            yield
        finally:
            self._loading = old

    def refresh(self):
        if self.config is None:
            self.setEnabled(False)
            return
        self.setEnabled(True)
        with self.loading():
            self._refresh()

    def _refresh(self):
        raise NotImplementedError

    def is_dirty(self):
        return False

    def edit(self):
        """Nach einer Model-Änderung aufrufen."""
        if not self._loading:
            self.changed.emit()

    @property
    def settings(self):
        return self.config.settings[self.profile]
