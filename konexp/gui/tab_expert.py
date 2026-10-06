"""Expertenansicht (read-only): Hex der Reports mit markierten Änderungen, unbekannte Bytes."""
import html

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QTextBrowser, QVBoxLayout

from .model import R06, R07, R11, UNKNOWN06
from .tab_base import TabBase


def hex_html(cur, orig):
    rows = []
    for base in range(0, len(cur), 16):
        cells = []
        for i in range(base, min(base + 16, len(cur))):
            h = f'{cur[i]:02x}'
            if i >= len(cur) - 2 and cur[0] in (0x06, 0x07, 0x11):
                cells.append(f'<span style="color:gray">{h}</span>')
            elif orig is not None and cur[i] != orig[i]:
                cells.append(f'<span style="background:#e0a000;color:black" title="alt {orig[i]:02x}">{h}</span>')
            else:
                cells.append(h)
        rows.append(f'{base:02x}: ' + ' '.join(cells))
    return '<pre>' + '\n'.join(rows) + '</pre>'


class ExpertTab(TabBase):
    TITLE = 'Experte'

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        lay.addWidget(self.view)

    def _refresh(self):
        c, p = self.config, self.profile
        s = c.settings[p]
        out = [f'<h3>Profil P{p + 1} – Report 0x06 (Einstellungen)</h3>',
               hex_html(bytes(s.to_bytes()), c.orig[(R06, p)]),
               f'<h3>Profil P{p + 1} – Report 0x07 (Tasten)</h3>',
               hex_html(bytes(c.buttons[p].to_bytes()), c.orig[(R07, p)]),
               '<h3>Global</h3>',
               '<b>0x05</b> (aktives Profil)' + hex_html(c.snapshot.r05, None),
               '<b>0x11</b> (Debounce)' + hex_html(bytes(c.advanced.to_bytes()), c.orig[(R11, None)]),
               '<b>0x0f</b> (DCU, nur lesen)' + (hex_html(c.r0f, None) if c.r0f else ' nicht lesbar'),
               '<h3>Unbekannte / nicht bearbeitete Bytes in 0x06 (nur Anzeige)</h3><table>']
        for off, name in UNKNOWN06:
            out.append(f'<tr><td>0x{off:02x}</td><td>&nbsp;{s.raw[off]:02x}&nbsp;</td><td>{html.escape(name)}</td></tr>')
        led0 = sorted({s.raw[0x24 + 6 * i] for i in range(20)})
        led5 = sorted({s.raw[0x29 + 6 * i] for i in range(20)})
        out.append(f'<tr><td>LED +0</td><td>&nbsp;{" ".join(f"{v:02x}" for v in led0)}&nbsp;</td><td>Werte über alle LEDs</td></tr>')
        out.append(f'<tr><td>LED +5</td><td>&nbsp;{" ".join(f"{v:02x}" for v in led5)}&nbsp;</td><td>Werte über alle LEDs</td></tr>')
        out.append('</table><p style="color:gray">Markiert = geändert, noch nicht geschrieben. '
                   'Letzte 2 Bytes = Checksumme (wird beim Schreiben neu berechnet).</p>')
        self.view.setHtml(''.join(out))
