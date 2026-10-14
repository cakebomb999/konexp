"""Kone XP Air ohne Maus: Transport gegen ein simuliertes Gerät (Verhalten laut docs/PROTOCOL-XP-AIR.md), Codecs, Model."""
import unittest
from unittest import mock

from konexp import defaults, device
from konexp.device import AIR_CHUNK, KoneXPAir, KoneXPError
from konexp.gui.model import R06, R11, Config, DemoBackend
from konexp.reports import Advanced, Buttons, Settings


class FakeAir:
    """Feature-Report 0x06, 30 B: [06 ziel cmd op len daten…]. Blöcke 0x46/0x47 über Kopf [index, profil]."""

    def __init__(self):
        self.blocks = {(0x46, p): bytearray(defaults.air_settings(p)) for p in range(5)}
        self.blocks.update({(0x47, p): bytearray(defaults.air_buttons(p)) for p in range(5)})
        self.regs = {0x45: bytearray([2, 5]), 0x43: bytearray.fromhex(defaults.AIR_ADVANCED_HEX),
                     0x4f: bytearray(2), 0x44: bytearray(17)}
        self.ptr = {}
        self.resp = None
        self.sets = []
        self.fail_data = None  # n: der n-te Daten-Frame (ab 1) wird verworfen und nicht bestätigt

    def ioctl(self, fd, req, buf):
        nr = req & 0xff
        if nr == 0x06:      # SET
            self.sets.append(bytes(buf))
            self._set(buf)
        else:               # GET
            buf[:] = self.resp
        return 0

    def _fail(self):
        if self.fail_data is None:
            return False
        self.fail_data -= 1
        return self.fail_data == 0

    def _set(self, buf):
        tgt, cmd, op, n = buf[1:5]
        data = bytes(buf[5:5 + n])
        if op == 0x07:
            out = bytearray(30)
            out[:4] = bytes([0x06, tgt, cmd, 0x08])
            if cmd in (0x46, 0x47):
                idx, p = self.ptr[cmd]
                chunk = self.blocks[(cmd, p)][idx * AIR_CHUNK:(idx + 1) * AIR_CHUNK]
            else:
                chunk = self.regs[cmd]
            out[5:5 + len(chunk)] = chunk
            self.resp = out
            return
        ok = 1
        if cmd in (0x46, 0x47):
            if n == 2:
                self.ptr[cmd] = (data[0], data[1])
            elif self._fail():
                ok = 0
            else:
                idx, p = self.ptr[cmd]
                self.blocks[(cmd, p)][idx * AIR_CHUNK:idx * AIR_CHUNK + n] = data
        else:
            self.regs[cmd][:n] = data
        self.regs[0x44][0] = ok


def air(fake, pid=device.AIR_DONGLE, readonly=True):
    dev = KoneXPAir.__new__(KoneXPAir)
    dev.node, dev.fd, dev.backup_dir = '/dev/null', -1, None
    dev.pid, dev.target, dev.readonly, dev.profile_count = pid, int(pid != device.AIR_WIRED), readonly, 5
    return dev


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeAir()
        patches = [mock.patch.object(device.fcntl, 'ioctl', self.fake.ioctl),
                   mock.patch.object(device.time, 'sleep', lambda _s: None)]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_read_all(self):
        dev = air(self.fake)
        self.assertEqual(dev.get(0x05), bytes([0x05, 0x04, 2, 0x05]))
        for p in range(5):
            self.assertEqual(dev.read_settings(p), defaults.air_settings(p))
            self.assertEqual(dev.read_buttons(p), defaults.air_buttons(p))
        self.assertEqual(Advanced(dev.get(0x11)).debounce_ms, 10)
        self.assertEqual(dev.get(0x0f), bytes([0x0f, 0x06, 0, 0, 0, 0]))
        # Dongle: Ziel 1; Lesen sendet nur Köpfe [index, profil] als Schreib-Frames
        self.assertTrue(all(f[1] == 1 for f in self.fake.sets))
        self.assertTrue(all(f[4] == 2 for f in self.fake.sets if f[3] == 0x06))

    def test_wired_target(self):
        dev = air(self.fake, pid=device.AIR_WIRED)
        dev.read_settings(0)
        self.assertTrue(all(f[1] == 0 for f in self.fake.sets))

    def test_readonly_blocks_writes(self):
        dev = air(self.fake)
        s = Settings(dev.read_settings(1))
        s.set_dpi(0, 900)
        self.fake.sets.clear()
        with self.assertRaises(KoneXPError):
            dev.write(s.to_bytes())
        with self.assertRaises(KoneXPError):
            dev.set_active_profile(0)
        with self.assertRaises(KoneXPError):
            dev.command(0x45, bytes([0, 5]))
        self.assertFalse([f for f in self.fake.sets if f[4] > 2], 'keine Daten-Frames im Nur-Lesen-Modus')
        self.assertFalse([f for f in self.fake.sets if f[2] == 0x45])
        self.assertEqual(dev.read_settings(1), defaults.air_settings(1))  # Lesen geht weiter

    def test_write_and_verify(self):
        dev = air(self.fake, readonly=False)
        s = Settings(dev.read_settings(3))
        s.set_dpi(0, 900)
        s.set_led(6, 1, 2, 3)
        back = dev.write(s.to_bytes())
        self.assertEqual(back, s.to_bytes())
        self.assertEqual(bytes(self.fake.blocks[(0x46, 3)]), s.to_bytes())
        a = Advanced(dev.get(0x11))
        a.debounce_ms = 4
        dev.write(a.to_bytes())
        self.assertEqual(self.fake.regs[0x43][2:6], bytes([1, 4, 4, 0x0a]))
        dev.set_active_profile(4)
        self.assertEqual(dev.active_profile(), 4)
        with self.assertRaises(KoneXPError):
            dev.set_active_profile(5)

    def test_aborted_write_restores_backup(self):
        dev = air(self.fake, readonly=False)
        orig = dev.read_settings(3)
        s = Settings(orig)
        for i in range(7):
            s.set_led(i, 1, 2, 3)
        self.fake.fail_data = 3  # Stück 3 von 4 schlägt fehl, Stücke 1–2 sind schon geschrieben
        with self.assertRaises(KoneXPError) as cm:
            dev.write(s.to_bytes())
        self.assertIn('Backup zurückgeschrieben', str(cm.exception))
        self.assertEqual(bytes(self.fake.blocks[(0x46, 3)]), orig)

    def test_blocked_commands(self):
        dev = air(self.fake, readonly=False)
        for cmd in (0x01, 0x12, 0x31, 0x49, 0x4b):
            with self.assertRaises(KoneXPError):
                dev.command(cmd, b'\x01')
        with self.assertRaises(KoneXPError):
            dev.write(bytes([0x08]) + bytes(1042))

    def test_bad_answer(self):
        dev = air(self.fake)
        self.fake.blocks[(0x46, 0)][0] = 0
        with self.assertRaises(KoneXPError):
            dev.read_settings(0)


class CodecTest(unittest.TestCase):
    def test_settings_air(self):
        s = Settings(defaults.air_settings(2))
        self.assertTrue(s.air)
        self.assertEqual(s.led_count, 7)
        self.assertEqual([s.dpi(i) for i in range(5)], [400, 800, 1200, 1600, 3200])
        self.assertEqual((s.polling_hz, s.effect, s.speed, s.brightness), (1000, 10, 6, 255))
        self.assertEqual(s.led(0), (0xff, 0xff, 0, 0))
        self.assertEqual(s.profile_color, (0xf4, 0, 0))
        s.set_profile_color(1, 2, 3)
        self.assertEqual(s.raw[0x47:0x4c], bytes([1, 0x64, 1, 2, 3]))
        self.assertEqual(s.led_index(0x24 + 5 * 6 + 4), 6)
        self.assertIsNone(s.led_index(0x47))
        self.assertFalse(Settings(defaults.settings(0)).air)

    def test_buttons_air(self):
        b = Buttons(defaults.air_buttons(0))
        self.assertEqual(b.entry(13), (0, 0, 0x01, 0x0a))   # Easy-Shift wie Kone XP
        self.assertEqual(b.entry(14), (0, 0, 0x01, 0x08))

    def test_factory_checksums(self):
        # Checksummen aus der Werks-Datei des Swarm-Plugins 1.0019
        self.assertEqual([defaults.air_settings(p)[-2:].hex() for p in range(5)],
                         ['9218', 'e419', '2917', '8617', '1819'])
        self.assertEqual([defaults.air_buttons(p)[-2:].hex() for p in range(5)],
                         ['c202', 'c302', 'c402', 'c502', 'c602'])
        self.assertTrue(device.checksum_ok(bytes.fromhex(defaults.AIR_ADVANCED_HEX)))


class ModelTest(unittest.TestCase):
    def test_demo_air_readonly(self):
        be = DemoBackend(delay=0, air=True)
        c = Config(be.read_all())
        self.assertTrue(c.air and c.readonly)
        c.settings[0].set_led(0, 9, 9, 9)
        c.advanced.debounce_ms = 3
        fields = {ch.field for ch in c.changes()}
        self.assertIn('LED-Zone 1 Farbe', fields)
        self.assertIn('Debounce (ms)', fields)
        self.assertEqual([k for k, _ in c.write_plan()], [(R06, 0), (R11, None)])
        with self.assertRaises(KoneXPError):
            be.write(c.current((R06, 0)))

    def test_factory_and_backup_model(self):
        c = Config(DemoBackend(delay=0, air=True).read_all())
        c.load_factory(2)
        self.assertEqual(c.current((R06, 2)), defaults.air_settings(2))
        xp = Config(DemoBackend(delay=0).read_all())
        with self.assertRaises(ValueError):
            c.apply_backup(xp.backup_dict())


if __name__ == '__main__':
    unittest.main()
