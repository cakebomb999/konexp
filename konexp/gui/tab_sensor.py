"""Tab Sensor: Polling (0x06 0x1d), Angle Snapping (0x06 0x1b), Debounce (0x11, global), DCU nur Anzeige."""
from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QLabel, QPushButton, QSpinBox, QVBoxLayout

from ..reports import POLLING_HZ
from .model import DCU_MODES, R06, R11
from .tab_base import TabBase


class SensorTab(TabBase):
    TITLE = 'Sensor'

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)

        prof = QGroupBox('Profil')
        f = QFormLayout(prof)
        self.polling = QComboBox()
        for hz in POLLING_HZ:
            self.polling.addItem(f'{hz} Hz', hz)
        self.polling.currentIndexChanged.connect(self._on_polling)
        f.addRow('Polling-Rate:', self.polling)
        self.snap = QCheckBox('Angle Snapping')
        self.snap.toggled.connect(self._on_snap)
        f.addRow('', self.snap)
        lay.addWidget(prof)

        glob = QGroupBox('Global (alle Profile)')
        g = QFormLayout(glob)
        self.debounce = QSpinBox()
        self.debounce.setRange(0, 10)
        self.debounce.setSuffix(' ms')
        self.debounce.valueChanged.connect(self._on_debounce)
        g.addRow('Debounce-Zeit:', self.debounce)
        self.dcu = QLabel()
        g.addRow('Lift-off (DCU):', self.dcu)
        self.calib = QPushButton('Kalibrierung (kommt später)')
        self.calib.setEnabled(False)
        g.addRow('', self.calib)
        hint = QLabel('Lift-off wird nur angezeigt (Report 0x0f), nicht geschrieben.')
        hint.setStyleSheet('color: gray')
        g.addRow('', hint)
        lay.addWidget(glob)
        lay.addStretch(1)

    def _refresh(self):
        s = self.settings
        hz = s.polling_hz
        idx = self.polling.findData(hz)
        if idx < 0:
            self.polling.setCurrentIndex(-1)
            self.polling.setPlaceholderText(f'unbekannt (0x{s.raw[0x1d]:02x})')
        else:
            self.polling.setCurrentIndex(idx)
        self.snap.setChecked(s.angle_snapping)
        self.debounce.setValue(min(self.config.advanced.debounce_ms, 10))
        r0f = self.config.r0f
        if r0f is None:
            self.dcu.setText('nicht lesbar')
        else:
            mode = r0f[2]
            text = DCU_MODES.get(mode, f'unbekannt ({mode})')
            self.dcu.setText(f'{text}' + (f'   [0x0f: {r0f.hex(" ")}]' if self.expert else ''))

    def is_dirty(self):
        offs = self.config.changed_offsets((R06, self.profile))
        return any(0x1b <= o <= 0x1d for o in offs) or self.config.is_key_dirty((R11, None))

    def _on_polling(self, idx):
        if self._loading or idx < 0:
            return
        self.settings.polling_hz = self.polling.itemData(idx)
        self.edit()

    def _on_snap(self, on):
        if self._loading:
            return
        self.settings.angle_snapping = on
        self.edit()

    def _on_debounce(self, v):
        if self._loading:
            return
        self.config.advanced.debounce_ms = v
        self.edit()
