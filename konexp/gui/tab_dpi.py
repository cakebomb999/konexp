"""Tab DPI: 5 Stufen (Maske 0x05), Werte X (+Y gleich), aktive Stufe 0x06."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QRadioButton, QSlider, QSpinBox, QVBoxLayout)

from ..reports import DPI_MAX, DPI_MIN, DPI_STEP
from .model import R06
from .tab_base import TabBase


class DpiTab(TabBase):
    TITLE = 'DPI'

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        grid = QGridLayout()
        for c, h in enumerate(['Stufe', 'DPI', '', 'aktiv', 'Y (Experte)']):
            lbl = QLabel(f'<b>{h}</b>')
            grid.addWidget(lbl, 0, c)
            if c == 4:
                self.y_header = lbl
        self.checks, self.sliders, self.spins, self.radios, self.ylabels = [], [], [], [], []
        self.radio_group = QButtonGroup(self)
        for i in range(5):
            cb = QCheckBox(f'Stufe {i + 1}')
            sl = QSlider(Qt.Horizontal)
            sl.setRange(DPI_MIN // DPI_STEP, DPI_MAX // DPI_STEP)
            sl.setMinimumWidth(260)
            sp = QSpinBox()
            sp.setRange(DPI_MIN, DPI_MAX)
            sp.setSingleStep(DPI_STEP)
            sp.setSuffix(' DPI')
            sp.setKeyboardTracking(False)
            rb = QRadioButton()
            yl = QLabel()
            self.radio_group.addButton(rb, i)
            grid.addWidget(cb, i + 1, 0)
            grid.addWidget(sl, i + 1, 1)
            grid.addWidget(sp, i + 1, 2)
            grid.addWidget(rb, i + 1, 3, alignment=Qt.AlignCenter)
            grid.addWidget(yl, i + 1, 4)
            cb.toggled.connect(lambda on, i=i: self._on_enable(i, on))
            sl.valueChanged.connect(lambda v, i=i: self._on_slider(i, v))
            sp.valueChanged.connect(lambda v, i=i: self._on_spin(i, v))
            self.checks.append(cb)
            self.sliders.append(sl)
            self.spins.append(sp)
            self.radios.append(rb)
            self.ylabels.append(yl)
        self.radio_group.idToggled.connect(self._on_active)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        row = QHBoxLayout()
        self.y_info = QLabel()
        self.y_info.setWordWrap(True)
        self.align_btn = QPushButton('Y an X angleichen')
        self.align_btn.clicked.connect(self._align)
        row.addWidget(self.y_info, 1)
        row.addWidget(self.align_btn)
        lay.addLayout(row)
        note = QLabel('Swarm zeigt je Stufe nur einen Wert (X). Diese GUI setzt beim Ändern X und Y gleich. '
                      'Wertebereich 50–19000 DPI in 50er-Schritten.')
        note.setWordWrap(True)
        note.setStyleSheet('color: gray')
        lay.addWidget(note)
        lay.addStretch(1)

    def _refresh(self):
        s = self.settings
        mismatch = self.config.dpi_mismatch(self.profile)
        for i in range(5):
            on = s.dpi_enabled[i]
            self.checks[i].setChecked(on)
            self.sliders[i].setValue(s.dpi(i) // DPI_STEP)
            self.spins[i].setValue(s.dpi(i))
            self.radios[i].setChecked(s.dpi_active == i)
            self.radios[i].setEnabled(on)
            y = s.dpi(i, 'y')
            self.ylabels[i].setText(f'{y}' + (' ≠ X' if i in mismatch else ''))
            self.ylabels[i].setStyleSheet('color: #d06000; font-weight: bold' if i in mismatch else '')
            self.ylabels[i].setVisible(self.expert)
        self.y_header.setVisible(self.expert)
        show = self.expert and bool(mismatch)
        self.y_info.setText('Y-DPI weicht ab bei Stufe ' + ', '.join(str(i + 1) for i in mismatch)
                            + ' (Swarm schreibt nur X; Wirkung von Y ungeprüft).' if mismatch else '')
        self.y_info.setVisible(show)
        self.align_btn.setVisible(show)

    def is_dirty(self):
        return any(0x05 <= o <= 0x1a for o in self.config.changed_offsets((R06, self.profile)))

    # --- Handler ---------------------------------------------------------

    def _on_enable(self, i, on):
        if self._loading:
            return
        s = self.settings
        if not on and s.dpi_active == i:
            QMessageBox.warning(self, 'DPI', 'Die aktive Stufe kann nicht deaktiviert werden. '
                                             'Zuerst eine andere Stufe als aktiv wählen.')
            self.refresh()
            return
        try:
            s.set_dpi_enabled(i, on)
        except ValueError as e:
            QMessageBox.warning(self, 'DPI', str(e))
        self.refresh()
        self.edit()

    def _on_slider(self, i, v):
        if not self._loading:
            self.spins[i].setValue(v * DPI_STEP)

    def _on_spin(self, i, v):
        if self._loading:
            return
        v -= v % DPI_STEP
        v = max(DPI_MIN, v)
        self.settings.set_dpi(i, v, y=True)
        self.refresh()
        self.edit()

    def _on_active(self, i, checked):
        if self._loading or not checked:
            return
        self.settings.dpi_active = i
        self.edit()

    def _align(self):
        self.config.align_y(self.profile)
        self.refresh()
        self.edit()
