"""Werksdaten (konexp/defaults.py): Konsistenz und bekannte Checksummen."""
import unittest

from konexp import defaults
from konexp.device import checksum_ok
from konexp.reports import Buttons, Settings


class DefaultsTest(unittest.TestCase):
    def test_checksums(self):
        # Werte einer Kone XP im Werkszustand (FW 1.09), P0 bytegenau gegen Gerät geprüft
        self.assertEqual([defaults.settings(p)[0xac:].hex() for p in range(5)],
                         ['093d', '5b3e', '533c', 'b03c', '8f3d'])
        self.assertEqual([defaults.buttons(p)[0x7b:].hex() for p in range(5)],
                         ['2e02', '2f02', '3002', '3102', '3202'])
        self.assertTrue(checksum_ok(bytes.fromhex(defaults.ADVANCED_HEX)))

    def test_p0_fields(self):
        s = Settings(defaults.settings(0))
        self.assertEqual([s.dpi(i) for i in range(5)], [400, 800, 1200, 1600, 3200])
        self.assertEqual((s.dpi_active, s.polling_hz, s.effect, s.angle_snapping), (1, 1000, 10, False))
        b = Buttons(defaults.buttons(0))
        self.assertEqual(b.entry(13), (0, 0, 0x01, 0x0a))   # Easy-Shift
        self.assertEqual(b.entry(14), (0, 0, 0x01, 0x08))   # Profile Cycle

    def test_profiles_differ_only_in_index_color_checksum(self):
        p0 = defaults.settings(0)
        for p in range(1, 5):
            d = defaults.settings(p)
            self.assertTrue(checksum_ok(d))
            diff = {i for i in range(len(p0)) if p0[i] != d[i]}
            self.assertTrue(diff <= {0x02, 0x9f, 0xa0, 0xa1, 0xac, 0xad}, diff)
            self.assertEqual(d[2], p)

    def test_range(self):
        with self.assertRaises(ValueError):
            defaults.settings(5)


if __name__ == '__main__':
    unittest.main()
