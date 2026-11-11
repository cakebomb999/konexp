"""GUI-Start ohne Maus (QT_QPA_PLATFORM=offscreen, DemoBackend) inkl. Bearbeiten und Übernehmen."""
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from konexp.gui import dialogs, main_window, model, tab_buttons  # noqa: E402
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

    def test_macro_from_combo(self):
        w = self.win
        buttons = w.tab_list[3]
        combo = buttons.combos[(9, False)]
        idx = combo.findData(tab_buttons.MACRO)
        if w.config.air:  # Air: Makros nicht unterstützt, Option fehlt
            self.assertEqual(idx, -1)
            return
        self.assertGreater(idx, 0)
        with mock.patch.object(dialogs.MacroDialog, 'exec', lambda self: QDialog.Accepted), \
                mock.patch.object(dialogs.DiffDialog, 'exec', lambda self: QDialog.Accepted):
            buttons._on_activated(9, False, idx)
            self.assertIn((2, 9), w.config.macros)
            w.apply()
            self.assertTrue(wait(lambda: not w.busy and not w.config.dirty))
        self.assertEqual([d[0] for d in self.be.writes], [0x08, R07])
        self.assertEqual(self.be.writes[0][0x51:0x57].hex(), '01f0b2f00000')  # Vorgabe: Klick links, 50 ms

    def test_macro_editor(self):
        from PySide6.QtCore import QEvent, Qt
        from PySide6.QtGui import QKeyEvent
        if self.win.config.air:
            return
        buttons = self.win.tab_list[3]
        # Demo-P3 Taste 15 ist ein Makro: Editor lädt es vom Backend (Swarm-Autoclicker)
        m = buttons._current_macro(14, False, self.win.config.buttons[2].entry(14))
        self.assertEqual((m['name'], m['repeat'], m['steps']), ('Linksklick', None, [1, ('+', 0xf0), 2, ('-', 0xf0)]))
        dlg = dialogs.MacroDialog(m['steps'], m['name'], m['repeat'])
        dlg.table.selectRow(3)
        dlg._add_pause()                       # hinter Zeile 3
        self.assertEqual(dlg.steps[-1], 100)
        dlg._move(-1)
        self.assertEqual(dlg.steps[3:], [100, ('-', 0xf0)])
        dlg._remove()
        dlg._toggle_record()
        for typ in (QEvent.KeyPress, QEvent.KeyRelease):  # Scancode 38 = evdev 30 = HID 0x04 (A)
            dlg.event(QKeyEvent(typ, Qt.Key_A, Qt.NoModifier, 38, 0, 0))
        dlg._toggle_record()
        self.assertEqual([x for x in dlg.steps if isinstance(x, tuple)][-2:], [('+', 0x04), ('-', 0x04)])
        dlg.mode.setCurrentIndex(1)
        dlg.repeat.setValue(3)
        steps, name, repeat = dlg.value()
        self.assertEqual((name, repeat), ('Linksklick', 3))
        self.win.config.set_macro(2, 14, False, steps, name, repeat)
        self.assertEqual(self.win.config.buttons[2].entry(14), (0, 1, 2, 0x07))

    def test_set_active_and_poll(self):
        w = self.win
        w.select_profile(4)
        w.set_active()
        self.assertTrue(wait(lambda: not w.busy and w.config.active == 4))
        self.be.set_active_profile(1)   # Wechsel „an der Maus“
        w.poll_active()
        self.assertEqual(w.config.active, 1)

    def test_battery_rate(self):
        w = self.win
        w.batt_start = None
        with mock.patch.object(self.be, 'battery', side_effect=[(90, True), (89, True), (87, True), (87, False)]):
            w.update_battery(now=0)
            w.update_battery(now=1800)
            self.assertNotIn('%/h', w.battery_label.text())  # 1 % Abfall: noch keine Rate
            w.update_battery(now=3600)
            self.assertIn('~3.0 %/h', w.battery_label.text())
            w.update_battery(now=3700)  # am Kabel: Rate neu
            self.assertNotIn('%/h', w.battery_label.text())

    def test_calibrate(self):
        w = self.win
        Q = main_window.QMessageBox
        with mock.patch.object(Q, 'question', side_effect=[Q.Yes, Q.Save]):
            w.tab_list[1].calib.click()
            self.assertTrue(wait(lambda: not w.busy and w.config.r0f[2] == 2))


class AirGuiTest(GuiTest):
    """Kone XP Air (Demo): alle Tabs, Schreiben wie Kone XP, Tastennamen in Air-Reihenfolge."""
    def setUp(self):
        app()
        self.be = DemoBackend(delay=0, air=True)
        self.win = main_window.MainWindow(self.be)
        self.win.show()
        self.assertTrue(wait(lambda: self.win.config is not None and not self.win.busy))

    def test_tabs_and_expert(self):
        w = self.win
        self.assertIn('Kone XP Air', w.windowTitle())
        self.assertTrue(wait(lambda: '90 %' in w.battery_label.text()))
        w.act_expert.setChecked(True)
        for i in range(w.tabs.count()):
            w.tabs.setCurrentIndex(i)
            app().processEvents()
            self.shot(f'air-tab{i}.png')
        self.assertTrue(w.readonly_label.isHidden())
        buttons = w.tab_list[3]
        self.assertEqual(buttons.table.item(3, 0).text(), 'Rad hoch')
        self.assertEqual(buttons.table.item(11, 0).text(), 'Rad-Tilt links')


class AirReadonlyGuiTest(AirGuiTest):
    """KONEXP_AIR_WRITE=0: Banner, Übernehmen und Profilwechsel gesperrt."""
    def setUp(self):
        patch = mock.patch.object(model, 'AIR_WRITE', False)
        patch.start()
        self.addCleanup(patch.stop)
        super().setUp()

    def test_tabs_and_expert(self):
        self.assertFalse(self.win.readonly_label.isHidden())

    def test_edit_and_apply(self):
        w = self.win
        w.config.settings[2].set_dpi(0, 900)
        w.on_changed()
        self.assertTrue(w.config.dirty)
        self.assertFalse(w.btn_apply.isEnabled())
        w.select_profile(0)  # nicht aktives Profil: Button wäre ohne Nur-Lesen-Sperre aktiv
        self.assertFalse(w.btn_active.isEnabled())

    def test_set_active_and_poll(self):
        pass  # Profilwechsel ist im Nur-Lesen-Modus gesperrt (test_edit_and_apply)

    def test_calibrate(self):
        self.assertFalse(self.win.tab_list[1].calib.isEnabled())


class CliStartTest(unittest.TestCase):
    def test_demo_start(self):
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen')
        r = subprocess.run([sys.executable, '-m', 'konexp.gui', '--demo', '--quit-after', '800'],
                           cwd=ROOT, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
