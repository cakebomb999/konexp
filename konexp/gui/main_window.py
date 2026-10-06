"""Hauptfenster: Profilleiste, Tabs, Übernehmen/Verwerfen, Menüs, Worker-Steuerung, Live-Poll von 0x05."""
import os
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (QButtonGroup, QColorDialog, QDialog, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
                               QFrame, QMessageBox, QProgressBar, QPushButton, QScrollArea, QTabWidget, QVBoxLayout,
                               QWidget)

from ..device import KoneXPError
from .dialogs import DiffDialog
from .model import BACKUP_DIR, NPROFILES, UDEV_HINT, Config, load_backup, run_plan, save_backup
from .tab_buttons import ButtonsTab
from .tab_dpi import DpiTab
from .tab_expert import ExpertTab
from .tab_light import LightTab
from .tab_sensor import SensorTab
from .widgets import ColorButton, swatch_icon
from .worker import Task

POLL_MS = 2000


class MainWindow(QMainWindow):
    def __init__(self, backend):
        super().__init__()
        self.backend = backend
        self.config = None
        self.profile = 0
        self.task = None
        self.setWindowTitle('Kone XP Konfiguration' + (' – DEMO' if backend.demo else ''))
        self.resize(1100, 720)

        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)

        # Profilleiste
        bar = QHBoxLayout()
        bar.addWidget(QLabel('Profil:'))
        self.pgroup = QButtonGroup(self)
        self.pbuttons = []
        for p in range(NPROFILES):
            b = QPushButton(f'P{p + 1}')
            b.setCheckable(True)
            b.setMinimumWidth(90)
            self.pgroup.addButton(b, p)
            bar.addWidget(b)
            self.pbuttons.append(b)
        self.pbuttons[0].setChecked(True)
        self.pgroup.idClicked.connect(self.select_profile)
        self.btn_active = QPushButton('Als aktiv setzen')
        self.btn_active.clicked.connect(self.set_active)
        bar.addWidget(self.btn_active)
        self.btn_color = ColorButton('Profilfarbe…')
        self.btn_color.clicked.connect(self.pick_profile_color)
        bar.addWidget(self.btn_color)
        bar.addStretch(1)
        lay.addLayout(bar)

        # Tabs
        self.tabs = QTabWidget()
        self.tab_list = [DpiTab(), SensorTab(), LightTab(), ButtonsTab(), ExpertTab()]
        self.tab_pages = {}
        for t in self.tab_list:
            # Scrollbereich: bei kleinem Fenster scrollen statt Inhalte auf 0 Höhe zu quetschen
            page = QScrollArea()
            page.setWidgetResizable(True)
            page.setFrameShape(QFrame.NoFrame)
            page.setWidget(t)
            self.tab_pages[t] = page
            self.tabs.addTab(page, t.TITLE)
            t.changed.connect(self.on_changed)
        self.expert_tab = self.tab_list[-1]
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_pages[self.expert_tab]), False)
        lay.addWidget(self.tabs, 1)

        # Aktionen unten
        bottom = QHBoxLayout()
        self.dirty_label = QLabel()
        bottom.addWidget(self.dirty_label, 1)
        self.btn_discard = QPushButton('Verwerfen')
        self.btn_discard.setToolTip('Änderungen verwerfen und alles neu von der Maus laden')
        self.btn_discard.clicked.connect(self.discard)
        self.btn_apply = QPushButton('Übernehmen')
        self.btn_apply.setDefault(True)
        self.btn_apply.clicked.connect(self.apply)
        bottom.addWidget(self.btn_discard)
        bottom.addWidget(self.btn_apply)
        lay.addLayout(bottom)

        # Statuszeile
        self.status_label = QLabel()
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.hide()
        self.statusBar().addWidget(self.status_label, 1)
        self.statusBar().addPermanentWidget(self.progress)

        self._menus()
        self.poll = QTimer(self)
        self.poll.setInterval(POLL_MS)
        self.poll.timeout.connect(self.poll_active)
        self.refresh_all()
        QTimer.singleShot(0, self.reload)

    # --- Menüs -----------------------------------------------------------

    def _menus(self):
        m = self.menuBar().addMenu('&Datei')
        self.act_reload = m.addAction('Neu laden', self.discard)
        m.addSeparator()
        m.addAction('Beenden', self.close)

        m = self.menuBar().addMenu('&Werkzeuge')
        self.act_backup = m.addAction('Backup aller Profile speichern…', self.save_backup)
        self.act_restore = m.addAction('Backup wiederherstellen…', self.restore_backup)
        m.addSeparator()
        self.act_factory = m.addAction('Profil auf Werkseinstellung', self.factory_profile)

        m = self.menuBar().addMenu('&Ansicht')
        self.act_expert = QAction('Expertenmodus', self, checkable=True)
        self.act_expert.toggled.connect(self.set_expert)
        m.addAction(self.act_expert)
        self.act_live = QAction('Profilwechsel an der Maus verfolgen (alle 2 s)', self, checkable=True)
        self.act_live.setChecked(True)
        self.act_live.toggled.connect(lambda on: self.poll.start() if on and self.config else self.poll.stop())
        m.addAction(self.act_live)

        m = self.menuBar().addMenu('&Hilfe')
        m.addAction('Über', lambda: QMessageBox.about(
            self, 'Kone XP', 'ROCCAT Kone XP – Linux-Konfiguration\n\nSchreibt nur Reports 0x07, 0x06, 0x11 '
            '(und 0x05 für das aktive Profil). Werksreset über Report 0x09 wird nicht verwendet.'))

    # --- Zustand ---------------------------------------------------------

    @property
    def busy(self):
        return self.task is not None and self.task.isRunning()

    def refresh_all(self):
        for t in self.tab_list:
            t.set_context(self.config, self.profile)
        self.refresh_chrome()

    def refresh_chrome(self):
        c = self.config
        has = c is not None
        for p, b in enumerate(self.pbuttons):
            text = f'P{p + 1}'
            if has and p == c.active:
                text += ' ● aktiv'
            if has and c.profile_dirty(p):
                text += ' *'
            b.setText(text)
            if has:
                b.setIcon(swatch_icon(QColor(*c.settings[p].profile_color)))
            f = b.font()
            f.setBold(has and p == c.active)
            b.setFont(f)
        for i, t in enumerate(self.tab_list):
            star = has and t is not self.expert_tab and t.is_dirty()
            self.tabs.setTabText(i, t.TITLE + (' *' if star else ''))
        if has:
            self.btn_color.set_color(QColor(*c.settings[self.profile].profile_color))
            n = len(c.changes())
            self.dirty_label.setText(f'{n} ungespeicherte Änderung(en)' if n else 'keine Änderungen')
        else:
            self.dirty_label.setText('')
        self.tabs.setEnabled(has)
        self.btn_apply.setEnabled(has and c.dirty and not self.busy)
        self.btn_discard.setEnabled(not self.busy)
        self.act_reload.setEnabled(not self.busy)
        self.btn_active.setEnabled(has and not self.busy and self.profile != c.active)
        self.btn_color.setEnabled(has)
        for a in (self.act_backup, self.act_restore, self.act_factory):
            a.setEnabled(has and not self.busy)
        self.setWindowModified(has and c.dirty)

    def on_changed(self):
        # anderen Tabs Bescheid geben (z. B. Expertenansicht, Sternchen)
        sender = self.sender()
        for t in self.tab_list:
            if t is not sender and (t is self.expert_tab or t.isVisible()):
                t.refresh()
        self.refresh_chrome()

    def select_profile(self, p):
        self.profile = p
        self.pbuttons[p].setChecked(True)
        self.refresh_all()

    def set_expert(self, on):
        self.tabs.setTabVisible(self.tabs.indexOf(self.tab_pages[self.expert_tab]), on)
        for t in self.tab_list:
            t.expert = on
        self.refresh_all()

    def status(self, text):
        self.status_label.setText(f'{time.strftime("%H:%M:%S")}  {text}')

    # --- Worker ----------------------------------------------------------

    def run_task(self, fn, on_done, label):
        if self.busy:
            QMessageBox.information(self, 'Bitte warten', 'Es läuft bereits ein Gerätezugriff.')
            return
        self.task = Task(fn, self)
        self.task.progress.connect(self._on_progress)
        self.task.done.connect(on_done)
        self.task.failed.connect(lambda msg: self._on_failed(label, msg))
        self.task.finished.connect(self._on_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status(label + '…')
        self.task.start()
        self.refresh_chrome()

    def _on_progress(self, i, n, text):
        self.progress.setRange(0, max(n, 1))
        self.progress.setValue(i)
        self.progress.setFormat(text)
        self.progress.setTextVisible(True)

    def _on_finished(self):
        self.progress.hide()
        self.refresh_chrome()

    def _on_failed(self, label, msg):
        self.status(f'{label} fehlgeschlagen')
        hint = '' if self.backend.demo else '\n\n' + UDEV_HINT + '\n\nOhne Maus testen: python3 -m konexp.gui --demo'
        QMessageBox.critical(self, label, f'{label} fehlgeschlagen:\n{msg}{hint}')

    # --- Laden / Schreiben -----------------------------------------------

    def reload(self):
        self.poll.stop()
        self.run_task(self.backend.read_all, self._loaded, 'Laden')

    def _loaded(self, snap):
        self.config = Config(snap)
        self.status(f'{self.backend.name}: 5 Profile geladen, aktiv P{self.config.active + 1}')
        self.profile = self.config.active
        self.pbuttons[self.profile].setChecked(True)
        self.refresh_all()
        if self.act_live.isChecked():
            self.poll.start()

    def discard(self):
        if self.config and self.config.dirty:
            r = QMessageBox.question(self, 'Verwerfen', 'Alle ungespeicherten Änderungen verwerfen und neu laden?')
            if r != QMessageBox.Yes:
                return
        self.reload()

    def apply(self):
        c = self.config
        if c is None or not c.dirty:
            return
        bad = [p for p in range(NPROFILES) if c.profile_dirty(p) and not c.easy_shift_ok(p)]
        if bad:
            r = QMessageBox.warning(self, 'Easy-Shift', 'In ' + ', '.join(f'P{p + 1}' for p in bad)
                                    + ' ist Taste 14 keine Easy-Shift-Taste. Trotzdem schreiben?',
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        plan = c.write_plan()
        labels = [f'0x{rid:02x}' + ('' if p is None else f' P{p + 1}') for (rid, p), _ in plan]
        dlg = DiffDialog(c.changes(), labels, self.backend.demo, self)
        if dlg.exec() != QDialog.Accepted:
            return
        self.poll.stop()
        self.run_task(lambda prog: run_plan(self.backend, plan, prog, base=dict(c.orig)), self._written, 'Schreiben')

    def _written(self, result):
        done, err = result
        for key, data in done:
            self.config.mark_written(key, data)
        self.refresh_all()
        if err:
            self.status(f'Schreiben abgebrochen nach {len(done)} Report(s)')
            QMessageBox.critical(self, 'Schreiben', f'Fehler: {err}\n\n{len(done)} Report(s) wurden geschrieben, '
                                 'der Rest nicht (bleibt als Änderung markiert).')
        else:
            self.status(f'{len(done)} Report(s) geschrieben und verifiziert')
        if self.act_live.isChecked():
            self.poll.start()

    def set_active(self):
        p = self.profile
        self.poll.stop()

        def done(_):
            self.config.active = p
            self.status(f'P{p + 1} ist jetzt aktiv')
            self.refresh_chrome()
            if self.act_live.isChecked():
                self.poll.start()
        self.run_task(lambda prog: self.backend.set_active_profile(p), done, 'Profil aktivieren')

    def poll_active(self):
        if self.config is None or self.busy:
            return
        try:
            a = self.backend.poll_active()
        except KoneXPError:
            a = None
        if a is not None and 0 <= a < NPROFILES and a != self.config.active:
            self.config.active = a
            self.status(f'Profil an der Maus gewechselt → P{a + 1}')
            self.refresh_chrome()

    def pick_profile_color(self):
        if self.config is None:
            return
        s = self.config.settings[self.profile]
        col = QColorDialog.getColor(QColor(*s.profile_color), self, f'Profilfarbe P{self.profile + 1}')
        if col.isValid():
            s.set_profile_color(col.red(), col.green(), col.blue())
            self.on_changed()

    # --- Werkzeuge -------------------------------------------------------

    def save_backup(self):
        if self.config.dirty:
            QMessageBox.information(self, 'Backup', 'Gespeichert wird der zuletzt von der Maus gelesene '
                                                    'Zustand, nicht die ungespeicherten Änderungen.')
        os.makedirs(BACKUP_DIR, exist_ok=True)
        name = os.path.join(BACKUP_DIR, f'kone-xp-backup-{time.strftime("%Y%m%d-%H%M%S")}.json')
        fn, _ = QFileDialog.getSaveFileName(self, 'Backup speichern', name, 'Kone-XP-Backup (*.json)')
        if fn:
            save_backup(self.config, fn)
            self.status(f'Backup gespeichert: {fn}')

    def restore_backup(self):
        fn, _ = QFileDialog.getOpenFileName(self, 'Backup wiederherstellen', BACKUP_DIR, 'Kone-XP-Backup (*.json)')
        if not fn:
            return
        try:
            self.config.apply_backup(load_backup(fn))
        except (OSError, ValueError, KeyError, IndexError) as e:
            QMessageBox.critical(self, 'Backup', f'Backup ungültig: {e}')
            return
        self.refresh_all()
        QMessageBox.information(self, 'Backup', 'Backup in den Editor geladen. Mit „Übernehmen“ prüfen und schreiben.')

    def factory_profile(self):
        p = self.profile
        r = QMessageBox.question(self, 'Werkseinstellung',
                                 f'P{p + 1} (Einstellungen + Tasten) im Editor auf Werkswerte setzen?\n'
                                 'Geschrieben wird erst mit „Übernehmen“. Makros (0x08) bleiben unberührt.')
        if r == QMessageBox.Yes:
            self.config.load_factory(p)
            self.refresh_all()

    def closeEvent(self, e):
        if self.config and self.config.dirty:
            r = QMessageBox.question(self, 'Beenden', 'Ungespeicherte Änderungen verwerfen und beenden?')
            if r != QMessageBox.Yes:
                e.ignore()
                return
        self.poll.stop()
        if self.task is not None:
            self.task.wait()
        self.backend.close()
        e.accept()
