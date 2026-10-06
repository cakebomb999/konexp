"""Dialoge: Diff vor dem Schreiben, Tastatur-Shortcut, Easy-Aim-DPI."""
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QHeaderView, QLabel, QSpinBox, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..functions import MODIFIERS
from ..i18n import tr
from ..paths import BACKUP_DIR
from ..reports import DPI_STEP
from .hidkeys import USAGES
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
        t.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
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
