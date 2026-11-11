"""Dialoge: Diff vor dem Schreiben, Tastatur-Shortcut, Easy-Aim-DPI, Makro."""
from PySide6.QtCore import QElapsedTimer, QEvent, QTimer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..functions import MODIFIERS
from ..i18n import tr
from ..paths import BACKUP_DIR
from ..reports import DPI_STEP, MACRO_MAX_PAUSE, macro
from .hidkeys import MOUSE, USAGES, hid_from_scancode
from .model import EASY_AIM_MAX, EASY_AIM_MIN


class DiffDialog(QDialog):
    def __init__(self, changes, plan_labels, demo=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Änderungen übernehmen'))
        self.resize(820, 480)
        lay = QVBoxLayout(self)
        if demo:
            head = tr('{n} Änderung(en) werden in den Demo-Speicher geschrieben.').format(n=len(changes))
        else:
            head = tr('{n} Änderung(en) werden auf die Maus geschrieben.').format(n=len(changes))
        lay.addWidget(QLabel(head + ' ' + tr('Reihenfolge: {order}').format(order=', '.join(plan_labels))))
        t = QTableWidget(len(changes), 5)
        t.setHorizontalHeaderLabels([tr('Profil'), tr('Report'), tr('Feld'), tr('alt'), tr('neu')])
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.verticalHeader().hide()
        for r, c in enumerate(changes):
            for col, text in enumerate((c.profile_label, f'0x{c.report:02x}', c.field, c.old, c.new)):
                t.setItem(r, col, QTableWidgetItem(text))
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table = t
        lay.addWidget(t)
        lay.addWidget(QLabel(tr('Jeder Report wird vorher gesichert ({dir}), nach dem Schreiben '
                                'zurückgelesen und bei Abweichung automatisch wiederhergestellt.')
                             .format(dir=BACKUP_DIR)))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr('Schreiben'))
        bb.button(QDialogButtonBox.Cancel).setText(tr('Abbrechen'))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)


class ShortcutDialog(QDialog):
    """Taste (HID-Usage, Page 0x07) + Modifier → Eintrag typ 06."""

    def __init__(self, usage=0x04, mods=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Tastatur-Shortcut'))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.key = QComboBox()
        for u, name in sorted(USAGES.items()):
            self.key.addItem(f'{name}  (0x{u:02x})', u)
        if usage not in USAGES and usage:
            self.key.addItem(f'HID 0x{usage:02x}', usage)
        idx = self.key.findData(usage)
        self.key.setCurrentIndex(max(idx, 0))
        form.addRow(tr('Taste:'), self.key)
        mods_row = QHBoxLayout()
        self.mods = []
        for bit, name in MODIFIERS:
            cb = QCheckBox(name)
            cb.setChecked(bool(mods & bit))
            self.mods.append((bit, cb))
            mods_row.addWidget(cb)
        form.addRow(tr('Modifier:'), mods_row)
        lay.addLayout(form)
        lay.addWidget(QLabel(tr('Tastennamen nach deutschem Layout; gespeichert wird die HID-Usage.')))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self):
        return self.key.currentData(), sum(bit for bit, cb in self.mods if cb.isChecked())


class EasyAimDialog(QDialog):
    def __init__(self, dpi=1200, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Easy-Aim: eigener DPI-Wert'))
        lay = QVBoxLayout(self)
        self.spin = QSpinBox()
        self.spin.setRange(EASY_AIM_MIN, EASY_AIM_MAX)
        self.spin.setSingleStep(DPI_STEP)
        self.spin.setSuffix(' DPI')
        self.spin.setValue(dpi)
        form = QFormLayout()
        form.addRow(tr('DPI, solange die Taste gehalten wird:'), self.spin)
        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def value(self):
        v = self.spin.value()
        return v - v % DPI_STEP



class MacroDialog(QDialog):
    """Makro-Editor: eine Zeile je Schritt (Taste drücken/loslassen oder Pause), Aufnahme, Modus.

    Schritte wie reports.macro: ('+', key) / ('-', key) / int ms."""
    DOWN, UP, PAUSE = 0, 1, 2
    recording = False  # Klassenattribut: event() läuft schon während super().__init__

    def __init__(self, steps=None, name='konexp', repeat=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Makro-Editor'))
        self.resize(560, 560)
        self.steps = list(steps if steps is not None else [('+', 0xf0), 50, ('-', 0xf0)])
        self.timer = QElapsedTimer()
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(name)
        self.name.setMaxLength(31)
        form.addRow(tr('Name:'), self.name)
        mode = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems([tr('Schleife, solange gedrückt'), tr('Bei Druck abspielen')])
        self.repeat = QSpinBox()
        self.repeat.setRange(1, 0xffff)
        self.repeat.setSuffix(tr('×'))
        self.mode.currentIndexChanged.connect(lambda i: self.repeat.setEnabled(i == 1))
        self.mode.setCurrentIndex(0 if repeat is None else 1)
        self.repeat.setValue(repeat or 1)
        self.repeat.setEnabled(repeat is not None)
        mode.addWidget(self.mode, 1)
        mode.addWidget(self.repeat)
        form.addRow(tr('Modus:'), mode)
        lay.addLayout(form)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr('Aktion'), tr('Taste / Dauer')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.table, 1)

        row = QHBoxLayout()
        for text, fn in ((tr('+ Taste / Klick'), self._add_key), (tr('+ Pause'), self._add_pause),
                         (tr('Entfernen'), self._remove), ('↑', lambda: self._move(-1)), ('↓', lambda: self._move(1))):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        rec = QHBoxLayout()
        self.rec = QPushButton(tr('● Aufnahme starten'))
        self.rec.setAutoDefault(False)
        self.rec.clicked.connect(self._toggle_record)
        self.rec_pauses = QCheckBox(tr('Pausen mitschreiben'))
        self.rec_pauses.setChecked(True)
        rec.addWidget(self.rec)
        rec.addWidget(self.rec_pauses)
        rec.addStretch(1)
        lay.addLayout(rec)
        self.total = QLabel()
        lay.addWidget(self.total)
        help_ = QLabel(tr('Aufnahme: Tastatur-Tasten werden mit Zeitabständen eingefügt (an der markierten Zeile). '
                          'Maustasten über „+ Taste / Klick“ und die Tastenauswahl. '
                          'Pause am Ende: Raster 20 ms.'))
        help_.setWordWrap(True)
        help_.setStyleSheet('color: gray')
        lay.addWidget(help_)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._rebuild()

    # --- Tabelle ----------------------------------------------------------

    def _rebuild(self, select=None):
        self.table.setRowCount(len(self.steps))
        for r, st in enumerate(self.steps):
            action = QComboBox()
            action.addItems([tr('Taste drücken'), tr('Taste loslassen'), tr('Pause')])
            if isinstance(st, int):
                action.setCurrentIndex(self.PAUSE)
                val = QSpinBox()
                val.setRange(0, MACRO_MAX_PAUSE)
                val.setSuffix(' ms')
                val.setValue(st)
                val.valueChanged.connect(lambda v, r=r: self._set(r, v))
            else:
                action.setCurrentIndex(self.UP if st[0] == '-' else self.DOWN)
                val = QComboBox()
                for u, n in list(MOUSE.items()) + sorted(USAGES.items()):
                    val.addItem(f'{n}  (0x{u:02x})', u)
                if val.findData(st[1]) < 0:
                    val.addItem(f'HID 0x{st[1]:02x}', st[1])
                val.setCurrentIndex(val.findData(st[1]))
                val.activated.connect(lambda _i, r=r, w=val: self._set(r, (self.steps[r][0], w.currentData())))
            action.activated.connect(lambda i, r=r: self._set_action(r, i))
            self.table.setCellWidget(r, 0, action)
            self.table.setCellWidget(r, 1, val)
        if select is not None:
            self.table.selectRow(select)
        self._update_total()

    def _set(self, r, value):
        self.steps[r] = value
        self._update_total()

    def _set_action(self, r, i):
        st = self.steps[r]
        if i == self.PAUSE:
            self.steps[r] = st if isinstance(st, int) else 50
        else:
            self.steps[r] = ('-' if i == self.UP else '+', 0xf0 if isinstance(st, int) else st[1])
        QTimer.singleShot(0, lambda: self._rebuild(r))  # nicht im eigenen Signal-Handler umbauen

    def _row(self):
        r = self.table.currentRow()
        return r if 0 <= r < len(self.steps) else None

    def _insert(self, items):
        r = self._row()
        at = len(self.steps) if r is None else r + 1
        self.steps[at:at] = items
        self._rebuild(at + len(items) - 1)

    def _add_key(self):
        r = self._row()
        key = next((s[1] for s in reversed(self.steps[:None if r is None else r + 1]) if isinstance(s, tuple)), 0xf0)
        self._insert([('+', key), 50, ('-', key)])

    def _add_pause(self):
        self._insert([100])

    def _remove(self):
        r = self._row()
        if r is not None:
            del self.steps[r]
            self._rebuild(min(r, len(self.steps) - 1) if self.steps else None)

    def _move(self, d):
        r = self._row()
        if r is not None and 0 <= r + d < len(self.steps):
            self.steps[r], self.steps[r + d] = self.steps[r + d], self.steps[r]
            self._rebuild(r + d)

    def _update_total(self):
        ms = sum(s for s in self.steps if isinstance(s, int))
        n = sum(isinstance(s, tuple) for s in self.steps)
        self.total.setText(tr('{n} Events, Dauer {s:.2f} s').format(n=n, s=ms / 1000))

    # --- Aufnahme ---------------------------------------------------------

    def _toggle_record(self):
        self.recording = not self.recording
        if self.recording:
            self.timer.invalidate()
            self.grabKeyboard()
            self.rec.setText(tr('■ Aufnahme stoppen (Klick)'))
        else:
            self.releaseKeyboard()
            self.rec.setText(tr('● Aufnahme starten'))

    def event(self, e):
        if self.recording and e.type() in (QEvent.KeyPress, QEvent.KeyRelease, QEvent.ShortcutOverride):
            if e.type() != QEvent.ShortcutOverride and not e.isAutoRepeat():
                self.record(hid_from_scancode(e.nativeScanCode()), e.type() == QEvent.KeyPress)
            e.accept()
            return True
        return super().event(e)

    def record(self, usage, down):
        """Ein Tasten-Event anhängen, Pause seit dem letzten Event davor."""
        if usage is None:
            return
        items = []
        if self.timer.isValid() and self.rec_pauses.isChecked():
            items.append(max(int(self.timer.elapsed()), 1))
        self.timer.start()
        items.append(('+' if down else '-', usage))
        self._insert(items)

    # --- Ergebnis ---------------------------------------------------------

    def _ok(self):
        if self.recording:
            self._toggle_record()
        try:
            macro(0, 0, self.steps, repeat=self.value()[2])
        except ValueError as e:
            QMessageBox.warning(self, self.windowTitle(), str(e))
            return
        self.accept()

    def value(self):
        """(Schritte, Name, Wiederholungen oder None für Schleife)"""
        return list(self.steps), self.name.text() or 'konexp', None if self.mode.currentIndex() == 0 else self.repeat.value()
