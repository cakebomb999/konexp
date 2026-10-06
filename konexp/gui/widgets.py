"""Gemeinsame Widgets: Farbfeld-Button, LED-Ansichten, Tastenkarte.

Grafiken des Swarm-Plugins werden nur geladen, wenn extracted/plugin/res/ lokal existiert
(proprietär, nicht im Repo). Ohne sie zeichnen die Widgets eine eigene Skizze.
"""
import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap, QIcon
from PySide6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ..i18n import tr
from .model import LED_DPI, LED_GRID, LED_IMAGES, LED_WHEEL, RES_DIR, led_label
from ..reports import LED_COUNT

ILLU_DIR = os.path.join(RES_DIR, 'graphics', 'controls', 'Kone-XP_Illumination')
BTN_IMAGE = os.path.join(RES_DIR, 'graphics', 'controls', 'Kone_XP_Btn.png')

# Label-Positionen der Tasten (k=0..14) im 457×518-Koordinatensystem (siehe docs/PROTOCOL.md)
BUTTON_POS = [(240, 70), (344, 70), (290, 120), (250, 120), (330, 120), (290, 70), (290, 170),
              (170, 80), (160, 130), (100, 190), (110, 270), (40, 200), (40, 270), (130, 310),
              (290, 280)]


def argb_color(argb):
    a, r, g, b = argb
    return QColor(r, g, b, a)


def swatch_icon(color, size=16):
    pm = QPixmap(size, size)
    pm.fill(color)
    return QIcon(pm)


class ColorButton(QPushButton):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._color = QColor('black')
        self.setIconSize(QSize(24, 16))

    def set_color(self, color):
        self._color = QColor(color)
        self.setIcon(swatch_icon(self._color, 24))
        self.setToolTip(self._color.name())

    def color(self):
        return QColor(self._color)


def _fit(src_w, src_h, rect):
    s = min(rect.width() / src_w, rect.height() / src_h)
    w, h = src_w * s, src_h * s
    return QRectF(rect.x() + (rect.width() - w) / 2, rect.y() + (rect.height() - h) / 2, w, h), s


class LedGrid(QWidget):
    """Eigene Skizze: Maus von oben, LEDs im AIMO-Gitter (11 Spalten × 2 Zeilen)."""
    ledClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.colors = [(255, 0, 0, 0)] * LED_COUNT
        self.highlight = set()
        self.setMinimumSize(360, 170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_colors(self, colors, highlight=()):
        self.colors = list(colors)
        self.highlight = set(highlight)
        self.update()

    def _layout(self):
        r = QRectF(self.rect()).adjusted(10, 4, -10, -4)
        tile_w = r.width() / 11
        tile_h = min((r.height() - 50) / 2, tile_w * 1.4)
        top = r.center().y() - tile_h - 4 + 8
        rects = []
        for i in range(LED_COUNT):
            col, row = LED_GRID[i]
            x = r.x() + col * tile_w + 3
            y = top + row * (tile_h + 8)
            rects.append(QRectF(x, y, tile_w - 6, tile_h))
        self._body = QRectF(r.x(), top - 14, r.width(), 2 * tile_h + 36)
        return r, rects

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r, rects = self._layout()
        body = QPainterPath()
        body.addRoundedRect(self._body, 40, 40)
        p.fillPath(body, QColor(40, 40, 44))
        p.setPen(QPen(QColor(90, 90, 96), 2))
        p.drawPath(body)
        f = QFont(self.font())
        f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        p.setFont(f)
        for i, rc in enumerate(rects):
            col = argb_color(self.colors[i])
            p.setBrush(QBrush(col))
            pen = QPen(QColor('white') if i in self.highlight else QColor(20, 20, 20), 3 if i in self.highlight else 1)
            p.setPen(pen)
            if i in (LED_WHEEL, LED_DPI):
                p.drawEllipse(rc)
            else:
                p.drawRoundedRect(rc, 5, 5)
            lum = col.red() * 0.3 + col.green() * 0.59 + col.blue() * 0.11
            p.setPen(QColor('black') if lum > 140 and col.alpha() > 100 else QColor('white'))
            p.drawText(rc, Qt.AlignCenter, {LED_WHEEL: tr('Rad'), LED_DPI: 'DPI'}.get(i, str(i)))
        p.setPen(QColor(170, 170, 170))
        p.drawText(QRectF(r.x() + 8, r.y(), r.width() - 16, 18), Qt.AlignLeft, tr('◀ links'))
        p.drawText(QRectF(r.x(), r.y(), r.width(), 18), Qt.AlignCenter, tr('obere Reihe = vorn (Kabelseite)'))
        p.drawText(QRectF(r.x() + 8, r.y(), r.width() - 16, 18), Qt.AlignRight, tr('rechts ▶'))

    def _hit(self, pos):
        _, rects = self._layout()
        for i, rc in enumerate(rects):
            if rc.contains(QPointF(pos)):
                return i
        return None

    def mouseMoveEvent(self, e):
        i = self._hit(e.position())
        self.setToolTip(tr('LED {index}: {label}').format(index=i, label=led_label(i)) if i is not None else '')

    def mousePressEvent(self, e):
        i = self._hit(e.position())
        if i is not None:
            self.ledClicked.emit(i)


class LedImageView(QWidget):
    """Vorschau mit Plugin-Grafiken (nur wenn lokal extrahiert). Klick wählt die hellste LED am Punkt."""
    ledClicked = Signal(int)

    @staticmethod
    def available():
        return os.path.isfile(os.path.join(ILLU_DIR, 'Kone-XP_Base.png'))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.base = QImage(os.path.join(ILLU_DIR, 'Kone-XP_Base.png')).convertToFormat(QImage.Format_ARGB32)
        self.leds = [QImage(os.path.join(ILLU_DIR, f'Kone-XP_{n}.png')).convertToFormat(QImage.Format_ARGB32)
                     for n in LED_IMAGES]
        self.colors = [(255, 0, 0, 0)] * LED_COUNT
        self._cache = {}
        self.setMinimumSize(170, 260)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_colors(self, colors, highlight=()):
        self.colors = list(colors)
        self.update()

    def _tinted(self, i, argb):
        key = (i, argb[1:])
        if key not in self._cache:
            src = self.leds[i]
            img = QImage(src.size(), QImage.Format_ARGB32_Premultiplied)
            img.fill(Qt.transparent)
            q = QPainter(img)
            q.drawImage(0, 0, src)
            q.setCompositionMode(QPainter.CompositionMode_SourceIn)
            q.fillRect(img.rect(), QColor(argb[1], argb[2], argb[3]))
            q.end()
            self._cache[key] = img
        return self._cache[key]

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        target, _s = _fit(self.base.width(), self.base.height(), QRectF(self.rect()))
        p.drawImage(target, self.base)
        for i in range(LED_COUNT):
            argb = self.colors[i]
            if argb[0] == 0 or self.leds[i].isNull():
                continue
            p.setOpacity(argb[0] / 255)
            p.drawImage(target, self._tinted(i, argb))
        p.setOpacity(1)

    def mousePressEvent(self, e):
        target, s = _fit(self.base.width(), self.base.height(), QRectF(self.rect()))
        x = int((e.position().x() - target.x()) / s)
        y = int((e.position().y() - target.y()) / s)
        best, best_a = None, 40
        for i, img in enumerate(self.leds):
            if 0 <= x < img.width() and 0 <= y < img.height():
                a = img.pixelColor(x, y).alpha()
                if a > best_a:
                    best, best_a = i, a
        if best is not None:
            self.ledClicked.emit(best)


class ButtonMap(QWidget):
    """Tastenkarte: Plugin-Grafik (falls vorhanden) oder eigene Skizze, nummerierte Marker 1–15."""
    buttonClicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image = QImage(BTN_IMAGE) if os.path.isfile(BTN_IMAGE) else None
        self.selected = None
        self.warn = set()
        self.setMinimumSize(230, 260)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

    def set_selected(self, k):
        self.selected = k
        self.update()

    def set_warn(self, keys):
        self.warn = set(keys)
        self.update()

    def _sketch(self, p):
        p.setPen(QPen(QColor(110, 110, 118), 2))
        p.setBrush(QColor(45, 45, 50))
        body = QPainterPath()
        body.moveTo(230, 30)
        body.cubicTo(150, 30, 160, 200, 175, 300)
        body.cubicTo(185, 420, 200, 500, 290, 505)
        body.cubicTo(400, 505, 430, 400, 420, 250)
        body.cubicTo(415, 120, 400, 30, 330, 30)
        body.closeSubpath()
        p.drawPath(body)
        p.drawLine(QPointF(290, 30), QPointF(290, 200))
        p.drawRoundedRect(QRectF(275, 95, 30, 60), 10, 10)       # Rad
        p.drawRoundedRect(QRectF(278, 250, 24, 60), 10, 10)      # Taste hinter Rad
        p.setBrush(QColor(55, 55, 62))
        p.drawRoundedRect(QRectF(15, 170, 110, 160), 18, 18)     # Daumen-Inset
        p.setPen(QColor(150, 150, 150))
        p.drawText(QRectF(15, 335, 110, 20), Qt.AlignCenter, tr('Daumenseite'))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        target, s = _fit(457, 518, QRectF(self.rect()))
        p.translate(target.x(), target.y())
        p.scale(s, s)
        if self.image is not None:
            p.drawImage(QRectF(0, 0, 457, 518), self.image)
        else:
            self._sketch(p)
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(10)
        p.setFont(f)
        for k, (x, y) in enumerate(BUTTON_POS):
            sel = k == self.selected
            p.setBrush(QColor(230, 160, 20) if sel else (QColor(200, 60, 60) if k in self.warn else QColor(30, 30, 30, 200)))
            p.setPen(QPen(QColor('white'), 2))
            p.drawEllipse(QPointF(x, y), 13, 13)
            p.drawText(QRectF(x - 13, y - 13, 26, 26), Qt.AlignCenter, str(k + 1))

    def mousePressEvent(self, e):
        target, s = _fit(457, 518, QRectF(self.rect()))
        x = (e.position().x() - target.x()) / s
        y = (e.position().y() - target.y()) / s
        for k, (bx, by) in enumerate(BUTTON_POS):
            if (x - bx) ** 2 + (y - by) ** 2 <= 16 ** 2:
                self.buttonClicked.emit(k)
                return
