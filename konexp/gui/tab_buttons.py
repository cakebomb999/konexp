"""Tab Tasten: 15 Tasten × Ebene normal/Easy-Shift (Report 0x07)."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout)

from ..reports import BUTTONS, N_BUTTONS
from .dialogs import EasyAimDialog, ShortcutDialog
from .model import EASY_SHIFT_KEY, R07, easy_aim_entry, entry_text, function_catalog, is_host, shortcut_entry
from .tab_base import TabBase
from .widgets import ButtonMap

SHORTCUT, EASYAIM = 'shortcut', 'easyaim'
CATALOG = function_catalog()


class FunctionCombo(QComboBox):
    """Funktionsauswahl. Item-Daten: ('entry', tuple) | SHORTCUT | EASYAIM | None (Überschrift)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaxVisibleItems(30)
        self.entry = None

    def set_entry(self, entry):
        self.entry = tuple(entry)
        self.blockSignals(True)
        self.clear()
        model = self.model()
        known = {e for _, items in CATALOG for e, _n in items}
        if self.entry not in known:
            self.addItem(entry_text(self.entry) + '  (aktuell)', ('entry', self.entry))
            if is_host(self.entry) or self.entry[3] not in (0x02, 0x06):
                self.setItemData(0, QBrush(QColor('#d06000')), Qt.ForegroundRole)
        for group, items in CATALOG:
            self.addItem(f'— {group} —', None)
            it = model.item(self.count() - 1)
            it.setEnabled(False)
            f = QFont(self.font())
            f.setBold(True)
            it.setFont(f)
            for e, name in items:
                self.addItem('   ' + name, ('entry', e))
        self.addItem('— Weitere —', None)
        it = model.item(self.count() - 1)
        it.setEnabled(False)
        self.addItem('   Tastatur-Shortcut…', SHORTCUT)
        self.addItem('   Easy-Aim eigener DPI-Wert…', EASYAIM)
        for i in range(self.count()):
            if self.itemData(i) == ('entry', self.entry):
                self.setCurrentIndex(i)
                break
        self.setToolTip(entry_text(self.entry) + f'\nRoh: {bytes(self.entry).hex(" ")}')
        self.blockSignals(False)


class ButtonsTab(TabBase):
    TITLE = 'Tasten'

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        self.map = ButtonMap()
        self.map.buttonClicked.connect(self._select_row)
        lay.addWidget(self.map)
        right = QVBoxLayout()
        lay.addLayout(right, 1)
        self.table = QTableWidget(N_BUTTONS, 3)
        self.table.setMinimumHeight(320)
        self.table.setHorizontalHeaderLabels(['Taste', 'Normal', 'Easy-Shift-Ebene'])
        self.table.setVerticalHeaderLabels([str(k + 1) for k in range(N_BUTTONS)])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.combos = {}
        for k in range(N_BUTTONS):
            self.table.setItem(k, 0, QTableWidgetItem(BUTTONS[k]))
            for col, shift in ((1, False), (2, True)):
                c = FunctionCombo()
                c.activated.connect(lambda idx, k=k, shift=shift: self._on_activated(k, shift, idx))
                self.table.setCellWidget(k, col, c)
                self.combos[(k, shift)] = c
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.currentCellChanged.connect(lambda r, *_: self.map.set_selected(r))
        right.addWidget(self.table, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        right.addWidget(self.info)
        note = QLabel('Makros werden nur angezeigt (Bearbeitung nicht unterstützt). Host-Funktionen (typ 0b) '
                      'führt unter Windows Swarm aus – unter Linux passiert nichts.')
        note.setWordWrap(True)
        note.setStyleSheet('color: gray')
        right.addWidget(note)

    def _select_row(self, k):
        self.table.selectRow(k)
        self.map.set_selected(k)

    def _refresh(self):
        b = self.config.buttons[self.profile]
        dirty = self.config.changed_offsets((R07, self.profile))
        for (k, shift), combo in self.combos.items():
            combo.set_entry(b.entry(k, shift))
            off = 3 + 4 * (k + (N_BUTTONS if shift else 0))
            changed = any(o in dirty for o in range(off, off + 4))
            combo.setStyleSheet('font-weight: bold' if changed else '')
        warn = [k for k in range(N_BUTTONS) for sh in (False, True) if is_host(b.entry(k, sh))]
        msgs = []
        if not self.config.easy_shift_ok(self.profile):
            msgs.append('<span style="color:#c00000"><b>Warnung:</b> Taste 14 ist keine Easy-Shift-Taste – '
                        'die Easy-Shift-Ebene ist so nicht erreichbar.</span>')
        if warn:
            msgs.append('<span style="color:#d06000">Host-Funktionen (ohne Wirkung unter Linux) auf Taste '
                        + ', '.join(str(k + 1) for k in sorted(set(warn))) + '.</span>')
        self.info.setText('<br>'.join(msgs))
        self.info.setVisible(bool(msgs))
        self.map.set_warn(set(warn) | (set() if self.config.easy_shift_ok(self.profile) else {EASY_SHIFT_KEY}))

    def is_dirty(self):
        return self.config.is_key_dirty((R07, self.profile))

    def _on_activated(self, k, shift, idx):
        combo = self.combos[(k, shift)]
        data = combo.itemData(idx)
        old = combo.entry
        new = None
        if data is None:
            pass
        elif data == SHORTCUT:
            usage, mods = (old[1], old[2]) if old[3] == 0x06 else (0x04, 0)
            dlg = ShortcutDialog(usage, mods, self)
            if dlg.exec() == QDialog.Accepted:
                new = shortcut_entry(*dlg.value())
        elif data == EASYAIM:
            dpi = int.from_bytes(bytes(old[:2]), 'big') * 50 if old[3] == 0x02 and old[2] == 0x0c else 1200
            dlg = EasyAimDialog(dpi, self)
            if dlg.exec() == QDialog.Accepted:
                new = easy_aim_entry(dlg.value())
        else:
            new = data[1]
        if new is not None and tuple(new) != old:
            if k == EASY_SHIFT_KEY and not shift and new[3] != 0x0a:
                r = QMessageBox.warning(
                    self, 'Easy-Shift-Taste',
                    'Taste 14 ist die Easy-Shift-Taste. Ohne sie ist die Easy-Shift-Ebene aller Tasten '
                    'nicht mehr erreichbar.\n\nTrotzdem ändern?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if r != QMessageBox.Yes:
                    new = None
        if new is not None and tuple(new) != old:
            notes = self.config.set_button(self.profile, k, shift, new)
            if notes:
                QMessageBox.information(self, 'Tasten', '\n'.join(notes))
            self.edit()
        # Combo nach dem Signal neu aufbauen (nicht innerhalb des eigenen activated-Handlers)
        QTimer.singleShot(0, self.refresh)
