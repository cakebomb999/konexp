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
        for p in (mock.patch.object(device, '_feature', self.fake.ioctl),
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


class WindowsTransportTest(unittest.TestCase):
    """Windows-Pfad (hidapi) mit Fake-hid: Suche über Usage Page, Feature-Reports mit Report-ID."""

    class Dev:
        def __init__(self):
            self.sent, self.path = [], None

        def open_path(self, path):
            self.path = path

        def send_feature_report(self, data):
            self.sent.append(data)
            return len(data)

        def get_feature_report(self, rid, n):
            return [rid, device.ACK_OK, 0, 0][:n]

        def close(self):
            pass

    def setUp(self):
        devs = [{'path': b'p-mouse', 'product_id': device.PID, 'usage_page': 0x0001},
                {'path': b'p-cfg', 'product_id': device.PID, 'usage_page': device.XP_PAGE},
                {'path': b'p-air', 'product_id': device.AIR_DONGLE, 'usage_page': device.AIR_PAGE}]
        self.hid = mock.Mock(enumerate=lambda vid: devs if vid == device.VID else [], device=self.Dev)
        for p in (mock.patch.object(device, 'WINDOWS', True), mock.patch.object(device, 'hid', self.hid, create=True),
                  mock.patch.object(device.time, 'sleep', lambda _s: None)):
            p.start()
            self.addCleanup(p.stop)

    def test_find_prefers_config_collection(self):
        self.assertEqual(device.find_node(), ('p-cfg', device.PID))

    def test_swarm_warning(self):
        out = '"svchost.exe","1","Services","0","1 K"\n"ROCCAT_Swarm.exe","2","Console","1","9 K"\n'
        with mock.patch.object(device.subprocess, 'run', return_value=mock.Mock(stdout=out)):
            self.assertIn('ROCCAT_Swarm.exe', device.swarm_warning())
        with mock.patch.object(device.subprocess, 'run', return_value=mock.Mock(stdout=out.split('\n')[0])):
            self.assertEqual(device.swarm_warning(), '')

    def test_open_by_path_and_feature_roundtrip(self):
        dev = device.open_device('p-air')
        self.assertIsInstance(dev.fd, self.Dev)
        self.assertEqual(dev.fd.path, b'p-air')
        buf = bytearray([0x04, 0, 0, 0])
        device._feature(dev.fd, 0x07, buf)
        self.assertEqual(buf, bytearray([0x04, device.ACK_OK, 0, 0]))


if __name__ == '__main__':
    unittest.main()
