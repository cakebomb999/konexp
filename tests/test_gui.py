"""GUI-Start ohne Maus (QT_QPA_PLATFORM=offscreen, DemoBackend) inkl. Bearbeiten und Übernehmen."""
import os
import subprocess
import sys
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from konexp.gui import dialogs, main_window  # noqa: E402
from konexp.gui.model import R06, R07, R11, DemoBackend  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = os.environ.get('KONEXP_SHOTS')  # optional: Screenshots ablegen


def app():
    return QApplication.instance() or QApplication([])


def wait(cond, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        app().processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False


class GuiTest(unittest.TestCase):
    def setUp(self):
        app()
        self.be = DemoBackend(delay=0)
        self.win = main_window.MainWindow(self.be)
        self.win.show()
        self.assertTrue(wait(lambda: self.win.config is not None and not self.win.busy))

    def tearDown(self):
        if self.win.config:
            self.win.config.revert()
        self.win.close()
        self.win.deleteLater()
        app().processEvents()
        del self.win

    def shot(self, name):
        if SHOTS:
            self.win.grab().save(os.path.join(SHOTS, name))

    def test_tabs_and_expert(self):
        w = self.win
        self.assertEqual(w.profile, 2)
        self.assertIn('aktiv', w.pbuttons[2].text())
        w.act_expert.setChecked(True)
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            app().processEvents()
            self.shot(f'tab{i}.png')
        dpi = w.tab_list[0]
        self.assertFalse(dpi.align_btn.isHidden())
        self.assertIn('1600', dpi.ylabels[3].text())

    def test_edit_and_apply(self):
        w = self.win
        dpi, sensor, light, buttons = w.tab_list[:4]
        dpi.spins[0].setValue(450)
        sensor.debounce.setValue(4)
        light.speed.setValue(9)
        w.select_profile(0)
        buttons.combos[(7, False)].set_entry((0, 0, 0, 0))
        w.config.set_button(0, 7, False, (0, 0, 0x0b, 0x08))
        buttons.edit()
        w.refresh_all()
        self.assertTrue(w.tabs.tabText(3).endswith('*'))
        self.assertTrue(w.pbuttons[2].text().endswith('*'))
        self.shot('dirty.png')
        ch = w.config.changes()
        self.assertTrue(any(c.field == 'DPI Stufe 1 (X)' and c.new == '450 DPI' for c in ch))
        orig_exec = dialogs.DiffDialog.exec
        dialogs.DiffDialog.exec = lambda self: QDialog.Accepted
        try:
            w.apply()
            self.assertTrue(wait(lambda: not w.busy and not w.config.dirty))
        finally:
            dialogs.DiffDialog.exec = orig_exec
        self.assertEqual([(d[0], d[2] if d[0] != 0x11 else None) for d in self.be.writes],
                         [(R07, 0), (R06, 2), (R11, None)])
        self.assertFalse(w.tabs.tabText(3).endswith('*'))

    def test_set_active_and_poll(self):
        w = self.win
        w.select_profile(4)
        w.set_active()
        self.assertTrue(wait(lambda: not w.busy and w.config.active == 4))
        self.be.set_active_profile(1)   # Wechsel „an der Maus“
        w.poll_active()
        self.assertEqual(w.config.active, 1)


class CliStartTest(unittest.TestCase):
    def test_demo_start(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        r = subprocess.run([sys.executable, '-m', 'konexp.gui', '--demo', '--quit-after', '800'],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
