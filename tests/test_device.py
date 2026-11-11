"""Kone XP (Kabel) ohne Maus: sicherer Schreibpfad KoneXP.write() gegen ein simuliertes Gerät."""
import os
import tempfile
import unittest
from unittest import mock

from konexp import defaults, device
from konexp.device import KoneXP, KoneXPError
from konexp.reports import Settings


class FakeXP:
    """Select über Report 0x04, Ack immer ok. mangle: das nächste SET 0x06 kommt verfälscht an."""

    def __init__(self):
        self.r06 = {p: bytearray(defaults.settings(p)) for p in range(5)}
        self.sel, self.mangle = 0, False
        self.r0f = bytearray([0x0f, 0x06, 0, 0, 0, 0])

    def ioctl(self, fd, req, buf):
        if req & 0xff == 0x06:      # SET
            if buf[0] == 0x04:
                self.sel = buf[1]
            elif buf[0] == 0x0f:
                self.r0f = bytearray(buf)
            else:
                self.r06[buf[2]] = bytearray(buf)
                if self.mangle:
                    self.r06[buf[2]][0x20] ^= 1
                    self.mangle = False
        else:                       # GET
            buf[:] = {0x04: bytes([0x04, device.ACK_OK, 0, 0]), 0x0f: self.r0f}.get(buf[0], self.r06[self.sel])
        return 0


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeXP()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (mock.patch.object(device.fcntl, 'ioctl', self.fake.ioctl),
                  mock.patch.object(device.time, 'sleep', lambda _s: None)):
            p.start()
            self.addCleanup(p.stop)
        self.dev = KoneXP.__new__(KoneXP)
        self.dev.node, self.dev.fd, self.dev.backup_dir = '/dev/null', -1, self.tmp.name

    def _changed(self, profile=1):
        s = Settings(self.dev.read_settings(profile))
        s.brightness = 100
        return s.to_bytes()

    def test_write_verifies_and_backs_up(self):
        before = bytes(self.fake.r06[1])
        data = self._changed()
        self.assertEqual(self.dev.write(data), data)
        self.assertEqual(bytes(self.fake.r06[1]), data)
        files = os.listdir(self.tmp.name)
        self.assertEqual(len(files), 1)
        with open(os.path.join(self.tmp.name, files[0]), 'rb') as f:
            self.assertEqual(f.read(), before)

    def test_verify_mismatch_restores_backup(self):
        before = bytes(self.fake.r06[1])
        self.fake.mangle = True
        with self.assertRaises(KoneXPError):
            self.dev.write(self._changed())
        self.assertEqual(bytes(self.fake.r06[1]), before)

    def test_backups_in_same_second_do_not_collide(self):
        with mock.patch.object(device.time, 'strftime', lambda _f: '20260101-000000'), \
                mock.patch.object(device.time, 'time_ns', iter([1_000_000, 2_000_000]).__next__):
            self.dev.write(self._changed(1))
            self.dev.write(self._changed(2))
        self.assertEqual(len(os.listdir(self.tmp.name)), 2)

    def test_calibrate(self):
        self.assertEqual(self.dev.calibrate(device.DCU_START), bytes.fromhex('0f0602ff0000'))
        self.assertEqual(self.dev.calibrate(device.DCU_ACCEPT), bytes.fromhex('0f0602010000'))
        with self.assertRaises(KoneXPError):
            self.dev.calibrate(0x02)
        self.assertEqual(bytes(self.fake.r06[2]), defaults.settings(2))  # Profil 2 nicht berührt

    def test_locked_report(self):
        with self.assertRaises(KoneXPError):
            self.dev.write(bytes(device.SIZES[0x09]).replace(b'\0', b'\x09', 1))


if __name__ == '__main__':
    unittest.main()
