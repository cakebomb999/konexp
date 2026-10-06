"""Tab Beleuchtung: Effekt, Speed, Helligkeit, LED-Timeout, 20 LED-Farben."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from ..i18n import tr
from ..reports import EFFECTS, LED_COUNT, SLEEP_EFFECTS
from .model import LED_GROUPS, R06, led_label
from .tab_base import TabBase
from .widgets import LedGrid, LedImageView, argb_color

AIMO = 9
AIMO_WARN = tr('AIMO wird unter Windows von Swarm (Software) berechnet. Unter Linux läuft dafür nichts – '
               'die Beleuchtung bleibt dann ohne den erwarteten Effekt.')


def _slider_spin(lo, hi):
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    sl = QSlider(Qt.Horizontal)
    sl.setRange(lo, hi)
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sl.valueChanged.connect(sp.setValue)
    sp.valueChanged.connect(sl.setValue)
    h.addWidget(sl, 1)
    h.addWidget(sp)
    return w, sp


class LightTab(TabBase):
    TITLE = tr('Beleuchtung')

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        lay.addLayout(left, 1)

        eff = QGroupBox(tr('Effekt'))
        f = QFormLayout(eff)
        self.effect = QComboBox()
        for code, name in EFFECTS.items():
            self.effect.addItem(name, code)
        self.effect.currentIndexChanged.connect(self._on_effect)
        f.addRow(tr('Effekt:'), self.effect)
        self.aimo_warn = QLabel(AIMO_WARN)
        self.aimo_warn.setWordWrap(True)
        self.aimo_warn.setStyleSheet('color: #d06000')
        f.addRow('', self.aimo_warn)
        w, self.speed = _slider_spin(1, 11)
        self.speed.valueChanged.connect(self._on_speed)
        f.addRow(tr('Geschwindigkeit:'), w)
        w, self.bright = _slider_spin(0, 255)
        self.bright.valueChanged.connect(self._on_bright)
        f.addRow(tr('Helligkeit:'), w)
        self.timeout = QSpinBox()
        self.timeout.setRange(0, 255)
        self.timeout.setSpecialValueText(tr('aus'))
        self.timeout.valueChanged.connect(self._on_timeout)
        f.addRow(tr('LED-Timeout – Wert (vermutl. Minuten):'), self.timeout)
        self.sleep = QComboBox()
        for code, name in SLEEP_EFFECTS.items():
            self.sleep.addItem(name, code)
        self.sleep.currentIndexChanged.connect(self._on_sleep)
        f.addRow(tr('Effekt nach Timeout:'), self.sleep)
        left.addWidget(eff)

        leds = QGroupBox(tr('LED-Farben (Klick auf LED = Farbe wählen)'))
        v = QVBoxLayout(leds)
        self.grid = LedGrid()
        self.grid.ledClicked.connect(
            lambda i: self._pick([i], tr('LED {index}: {label}').format(index=i, label=led_label(i))))
        v.addWidget(self.grid, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr('Gruppe setzen:')))
        for name, members in LED_GROUPS.items():
            b = QPushButton(name)
            b.clicked.connect(lambda _=False, m=members, n=name: self._pick(m, n))
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        hint = QLabel(tr('Farbe inkl. Alpha (Intensität). Bei Colorwave/AIMO überschreibt der Effekt die Farben.'))
        hint.setStyleSheet('color: gray')
        v.addWidget(hint)
        left.addWidget(leds, 1)

        self.image = None
        if LedImageView.available():
            self.image = LedImageView()
            self.image.ledClicked.connect(
                lambda i: self._pick([i], tr('LED {index}: {label}').format(index=i, label=led_label(i))))
            lay.addWidget(self.image)

    def _colors(self):
        return [self.settings.led(i) for i in range(LED_COUNT)]

    def _refresh(self):
        s = self.settings
        self._set_combo(self.effect, s.effect)
        self.aimo_warn.setVisible(s.effect == AIMO or (s.sleep_effect == AIMO and s.led_timeout))
        self.speed.setValue(s.speed)
        self.bright.setValue(s.brightness)
        self.timeout.setValue(s.led_timeout)
        self._set_combo(self.sleep, s.sleep_effect)
        self.sleep.setEnabled(s.led_timeout != 0)
        changed = {(o - 0x24) // 6 for o in self.config.changed_offsets((R06, self.profile)) if 0x24 <= o < 0x9c}
        cols = self._colors()
        self.grid.set_colors(cols, changed)
        if self.image:
            self.image.set_colors(cols)

    @staticmethod
    def _set_combo(combo, code):
        idx = combo.findData(code)
        if idx < 0:
            combo.addItem(tr('unbekannt ({code})').format(code=code), code)
            idx = combo.findData(code)
        combo.setCurrentIndex(idx)

    def is_dirty(self):
        return any(0x1e <= o < 0x9c for o in self.config.changed_offsets((R06, self.profile)))

    def _pick(self, leds, title):
        if self.config is None:
            return
        start = argb_color(self.settings.led(leds[0]))
        col = QColorDialog.getColor(start, self, tr('Farbe – {title}').format(title=title),
                                    QColorDialog.ShowAlphaChannel)
        if not col.isValid():
            return
        self.config.set_leds(self.profile, leds, (col.alpha(), col.red(), col.green(), col.blue()))
        self.refresh()
        self.edit()

    def _on_effect(self, idx):
        if self._loading or idx < 0:
            return
        code = self.effect.itemData(idx)
        if code in EFFECTS:
            self.settings.effect = code
        self.refresh()
        self.edit()

    def _on_speed(self, v):
        if not self._loading:
            self.settings.speed = v
            self.edit()

    def _on_bright(self, v):
        if not self._loading:
            self.settings.brightness = v
            self.edit()

    def _on_timeout(self, v):
        if not self._loading:
            self.settings.led_timeout = v
            self.refresh()
            self.edit()

    def _on_sleep(self, idx):
        if self._loading or idx < 0:
            return
        code = self.sleep.itemData(idx)
        if code in SLEEP_EFFECTS:
            self.settings.sleep_effect = code
        self.refresh()
        self.edit()

