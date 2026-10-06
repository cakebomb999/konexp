"""Model/Diff/Schreibplan/Backup ohne Maus (DemoBackend = Dumps)."""
import json
import os
import tempfile
import unittest

from konexp import defaults
from konexp.device import KoneXPError, checksum_ok
from konexp.gui.model import (EASY_SHIFT, R06, R07, R11, Config, DemoBackend, diff_report, easy_aim_entry,
                              entry_text, function_catalog, load_backup, parse_backup, run_plan, save_backup,
                              shortcut_entry)


def fresh():
    return Config(DemoBackend(delay=0).read_all())


class LoadTest(unittest.TestCase):
    def test_snapshot(self):
        c = fresh()
        self.assertEqual(c.active, 2)              # Demo: P3 aktiv
        self.assertFalse(c.dirty)
        self.assertEqual(c.dpi_mismatch(2), [3])   # Demo-P3: Stufe 4 X1200/Y1600
        self.assertEqual(c.dpi_mismatch(0), [])
        self.assertEqual(c.advanced.debounce_ms, 10)
        self.assertEqual(c.r0f[2], 0)


class EditDiffTest(unittest.TestCase):
    def test_dpi_sets_x_and_y(self):
        c = fresh()
        c.settings[0].set_dpi(1, 900)
        self.assertEqual(c.dirty_keys(), [(R06, 0)])
        ch = {x.field: (x.old, x.new) for x in c.changes()}
        self.assertEqual(ch['DPI Stufe 2 (X)'], ('800 DPI', '900 DPI'))
        self.assertEqual(ch['DPI Stufe 2 (Y)'], ('800 DPI', '900 DPI'))
        self.assertEqual(len(ch), 2)

    def test_align_y(self):
        c = fresh()
        c.align_y(2)
        self.assertEqual(c.dpi_mismatch(2), [])
        [chg] = c.changes()
        self.assertEqual((chg.profile_label, chg.field, chg.old, chg.new),
                         ('P3', 'DPI Stufe 4 (Y)', '1600 DPI', '1200 DPI'))

    def test_sensor_light_fields(self):
        c = fresh()
        s = c.settings[1]
        s.polling_hz = 500
        s.angle_snapping = True
        s.effect = 1
        s.set_led(18, 1, 2, 3, 0x80)
        s.set_profile_color(1, 2, 3)
        c.advanced.debounce_ms = 4
        ch = {(x.profile_label, x.field): (x.old, x.new) for x in c.changes()}
        self.assertEqual(ch[('P2', 'Polling-Rate')], ('1000 Hz', '500 Hz'))
        self.assertEqual(ch[('P2', 'Angle Snapping')], ('aus', 'an'))
        self.assertEqual(ch[('P2', 'Lichteffekt')], ('Colorwave', 'Fully Lit'))
        self.assertEqual(ch[('P2', 'LED 18 Farbe (Mausrad)')], ('#0048ff α=255', '#010203 α=128'))
        self.assertEqual(ch[('P2', 'Profilfarbe')], ('#ffffff α=255', '#010203 α=255'))
        self.assertEqual(ch[('global', 'Debounce (ms)')], ('10', '4'))

    def test_unknown_byte_reported(self):
        old = defaults.settings(0)
        new = bytearray(old)
        new[0x1c] = 5
        self.assertIn(('unbekannt 0x1c', '00', '05'), diff_report(R06, old, bytes(new)))

    def test_write_order_and_checksum(self):
        c = fresh()
        c.advanced.debounce_ms = 3
        c.settings[3].brightness = 10
        c.set_button(3, 7, False, (0, 0, 0x0b, 0x08))
        c.settings[0].speed = 2
        keys = [k for k, _ in c.write_plan()]
        self.assertEqual(keys, [(R06, 0), (R07, 3), (R06, 3), (R11, None)])
        for _, data in c.write_plan():
            self.assertTrue(checksum_ok(data))

    def test_revert(self):
        c = fresh()
        c.settings[0].speed = 2
        c.revert()
        self.assertFalse(c.dirty)


class ButtonsTest(unittest.TestCase):
    def test_entry_texts(self):
        c = fresh()
        b = c.buttons[2]
        self.assertEqual(entry_text(b.entry(11)), 'Shortcut Strg+C')
        self.assertEqual(entry_text(b.entry(8)), 'Shortcut Pause')
        self.assertEqual(entry_text(b.entry(14)), 'Makro (solange gedrückt)')
        self.assertIn('wirkt unter Linux nicht', entry_text((0, 0, 0x08, 0x0b)))

    def test_easy_shift_rule(self):
        c = fresh()
        notes = c.set_button(0, 9, False, EASY_SHIFT)
        self.assertEqual(c.buttons[0].entry(9, True), (0, 0, 0, 0))
        self.assertTrue(notes)
        self.assertTrue(c.easy_shift_ok(0))
        c.set_button(0, 13, False, (0, 0, 1, 1))
        self.assertFalse(c.easy_shift_ok(0))

    def test_special_entries(self):
        self.assertEqual(easy_aim_entry(1200), (0x00, 0x18, 0x0c, 0x02))
        self.assertEqual(easy_aim_entry(19000), (0x01, 0x7c, 0x0c, 0x02))
        with self.assertRaises(ValueError):
            easy_aim_entry(50)
        self.assertEqual(shortcut_entry(0x10, 7), (0, 0x10, 7, 0x06))
        self.assertEqual(entry_text(easy_aim_entry(1250)), 'Easy-Aim 1250 DPI')

    def test_catalog_complete(self):
        entries = [e for _, items in function_catalog() for e, _ in items]
        self.assertIn(EASY_SHIFT, entries)
        self.assertEqual(len(entries), len(set(entries)))
        self.assertTrue(all(e[3] not in (0x06, 0x07) for e in entries))

    def test_factory_profile(self):
        c = fresh()
        c.load_factory(2)
        self.assertEqual(c.current((R06, 2)), defaults.settings(2))
        self.assertEqual(c.current((R07, 2)), defaults.buttons(2))
        self.assertEqual({k[1] for k in c.dirty_keys()}, {2})


class BackupTest(unittest.TestCase):
    def test_roundtrip(self):
        c = fresh()
        with tempfile.TemporaryDirectory() as d:
            fn = os.path.join(d, 'b.json')
            save_backup(c, fn)
            data = load_backup(fn)
        c2 = fresh()
        c2.settings[0].speed = 1
        c2.buttons[4].set_entry(0, (0, 0, 0, 0))
        c2.apply_backup(data)
        self.assertFalse(c2.dirty)

    def test_rejects_wrong_profile_and_checksum(self):
        d = fresh().backup_dict()
        bad = json.loads(json.dumps(d))
        bad['r06'][0], bad['r06'][1] = bad['r06'][1], bad['r06'][0]
        with self.assertRaises(ValueError):
            parse_backup(bad)
        bad = json.loads(json.dumps(d))
        raw = bytearray.fromhex(bad['r07'][0])
        raw[5] ^= 1
        bad['r07'][0] = raw.hex()
        with self.assertRaises(ValueError):
            parse_backup(bad)


class FailingBackend(DemoBackend):
    def __init__(self, fail_on):
        super().__init__(delay=0)
        self.fail_on = fail_on

    def write(self, data):
        if data[0] == self.fail_on:
            raise KoneXPError('Verify fehlgeschlagen')
        return super().write(data)


class RunPlanTest(unittest.TestCase):
    def test_success_marks_written(self):
        be = DemoBackend(delay=0)
        c = Config(be.read_all())
        c.settings[1].speed = 3
        c.advanced.debounce_ms = 2
        done, err = run_plan(be, c.write_plan())
        self.assertIsNone(err)
        self.assertEqual([w[0] for w in be.writes], [0x06, 0x11])
        for k, data in done:
            c.mark_written(k, data)
        self.assertFalse(c.dirty)

    def test_abort_on_error(self):
        be = FailingBackend(0x06)
        c = Config(be.read_all())
        c.settings[1].speed = 3
        c.set_button(1, 7, False, (0, 0, 1, 1))
        c.advanced.debounce_ms = 2
        done, err = run_plan(be, c.write_plan())
        self.assertEqual([k for k, _ in done], [(R07, 1)])
        self.assertIn('0x06 P2', err)
        self.assertEqual([w[0] for w in be.writes], [0x07])  # 0x11 nicht mehr geschrieben

    def test_locked_reports(self):
        be = DemoBackend(delay=0)
        for rid in (0x09, 0x0a, 0x0d, 0x10, 0x12, 0x13):
            with self.assertRaises(KoneXPError):
                be.write(bytes([rid, 0, 0, 0]))



class DeviceErrorTest(unittest.TestCase):
    def test_missing_node_gives_konexp_error(self):
        from konexp.gui.model import UDEV_HINT, DeviceBackend
        with self.assertRaises(KoneXPError):
            DeviceBackend(node='/dev/does-not-exist').read_all()
        self.assertIn('70-kone-xp.rules', UDEV_HINT)


if __name__ == '__main__':
    unittest.main()


class MergeTest(unittest.TestCase):
    """Änderungen an der Maus seit dem Laden dürfen durch Übernehmen nicht zurückgesetzt werden."""

    def test_dpi_stage_changed_on_device_survives(self):
        from konexp.gui.model import DemoBackend, merge_onto
        be = DemoBackend(delay=0)
        c = Config(be.read_all())
        c.settings[0].set_dpi(4, 6400)                 # Nutzer ändert Stufe 5 in der GUI
        dev = bytearray(be.snap.r06[0])
        dev[0x06] = 4                                   # parallel: DPI-Taste an der Maus
        be.snap.r06[0] = bytes(dev)
        done, err = run_plan(be, c.write_plan(), base=dict(c.orig))
        self.assertIsNone(err)
        written = be.writes[-1]
        self.assertEqual(written[0x06], 4)              # Gerätestand bleibt
        self.assertEqual(int.from_bytes(written[0x0f:0x11], 'little') * 50, 6400)
        self.assertEqual(merge_onto(b'\x01\x02\x00\x00', b'\x01\x02\x00\x00', b'\x01\x09\x00\x00'),
                         b'\x01\x09\x00\x00')
