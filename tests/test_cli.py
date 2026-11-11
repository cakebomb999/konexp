"""dump ohne bekannte Maus: nur Geräteliste aus sysfs, gefiltert nach ROCCAT / Turtle Beach."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from konexp import cli, reports
from konexp.device import checksum_ok


@unittest.skipIf(sys.platform == 'win32', 'sysfs')
class DumpTest(unittest.TestCase):
    def test_unknown_mouse(self):
        uevent = {'hidraw1': 'HID_ID=0003:000010F5:00007001\n', 'hidraw2': 'HID_ID=0003:0000046D:0000C52B\n'}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(cli.glob, 'glob', lambda _p: ['/sys/class/hidraw/hidraw1', '/sys/class/hidraw/hidraw2']), \
                mock.patch.object(cli, '_sysfs', lambda d: {'uevent': uevent[os.path.basename(d)]}):
            path = os.path.join(tmp, 'd.json')
            self.assertEqual(cli.dump(None, path, 'nicht gefunden'), 0)
            out = json.load(open(path))
        self.assertEqual(list(out['devices']), ['/dev/hidraw1'])
        self.assertEqual(out['error'], 'nicht gefunden')


class ArgsTest(unittest.TestCase):
    def test_bad_number_is_an_error_not_a_crash(self):
        with mock.patch.object(cli, 'open_device', side_effect=AssertionError('Gerät nicht anfassen')), \
                mock.patch('sys.stderr'):
            self.assertEqual(cli.main(['dpi', '0', '1', '0800']), 1)


class MacroTest(unittest.TestCase):
    # Profil 2 Taste 14, von Swarm geschrieben (Preset „Autoclicker“), von der Maus gelesen
    SWARM = bytes.fromhex('081304020e4175746f636c69636b6572' + '00' * 29 + '4c696e6b736b6c69636b' + '00' * 22
                          + '0100000001f082f0')

    def test_matches_swarm(self):
        raw = reports.macro(2, 14, reports.parse_steps('+f0 2 -f0'), name='Linksklick', group='Autoclicker')
        self.assertEqual(raw[:len(self.SWARM)], self.SWARM)
        self.assertEqual(raw[-2:], bytes([0x18, 0x0b]))
        self.assertTrue(checksum_ok(raw))

    def test_long_pauses(self):
        raw = reports.macro(0, 0, reports.parse_steps('+f0 1000 -f0 1500'))
        # 1000 ms = Block 9×100 + 100 im Event (exakt); Pause am Ende nur als Block
        self.assertEqual(raw[0x51:0x5f].hex(), '01f0' '00030900' 'e4f0' '00030f00' '0000')

    def test_roundtrip_and_repeat(self):
        steps = reports.parse_steps('5 +e0 128 +04 1 -04 1 -e0 340')
        m = reports.parse_macro(reports.macro(1, 3, steps, name='Strg+A', repeat=3))
        self.assertEqual((m['name'], m['repeat'], m['steps']), ('Strg+A', 3, steps))
        self.assertIsNone(reports.parse_macro(self.SWARM.ljust(1043, b'\0'))['repeat'])
        with self.assertRaises(ValueError):
            reports.macro(0, 0, [1000])


if __name__ == '__main__':
    unittest.main()
