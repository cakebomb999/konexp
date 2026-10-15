"""dump ohne bekannte Maus: nur Geräteliste aus sysfs, gefiltert nach ROCCAT / Turtle Beach."""
import json
import os
import tempfile
import unittest
from unittest import mock

from konexp import cli


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


if __name__ == '__main__':
    unittest.main()
