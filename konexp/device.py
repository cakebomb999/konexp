"""HID-Transport für die ROCCAT Kone XP (Interface 3, Feature-Reports via hidraw).

Protokoll: docs/PROTOCOL.md.
Jeder Write läuft über `KoneXP.write()`: Sperrliste prüfen, Ack pollen, zurücklesen,
bei Abweichung Backup wiederherstellen.
"""
import fcntl
import glob
import os
import time

from .i18n import tr

VID, PID = 0x1E7D, 0x2C8B

# Report-ID -> Gesamtlänge inkl. ID (aus dem Report-Descriptor von Interface 3)
SIZES = {0x04: 4, 0x05: 4, 0x06: 174, 0x07: 125, 0x08: 1043, 0x09: 9, 0x0a: 4,
         0x0d: 122, 0x0e: 6, 0x0f: 6, 0x10: 16, 0x11: 20, 0x12: 64, 0x13: 10}

# Nur diese Reports dürfen geschrieben werden. 0x09 (Werksreset/FW-Info), 0x0a, 0x0d (AIMO-Frames),
# 0x10, 0x12, 0x13 nutzt Swarm nicht bzw. sind riskant.
WRITABLE = {0x04, 0x05, 0x06, 0x07, 0x08, 0x0e, 0x0f, 0x11}

# Reports mit u16-LE-Summe über alle Bytes außer den letzten zwei
CHECKSUMMED = {0x06, 0x07, 0x08, 0x11}

# Select-Requests für `04 <profil> <req> 00` vor einem GET
SEL_SETTINGS, SEL_BUTTONS = 0x80, 0x90

ACK_DELAY = 0.15      # Swarm wartet 150 ms vor jedem Ack-Poll
ACK_TRIES = 100
ACK_OK, ACK_ERR, ACK_BUSY = 0x01, 0x02, 0x03


class KoneXPError(Exception):
    pass


def _ioc(dir_, nr, size):
    return (dir_ << 30) | (size << 16) | (ord('H') << 8) | nr


def checksum(buf):
    return sum(buf[:-2]) & 0xffff


def with_checksum(buf):
    buf = bytearray(buf)
    buf[-2:] = checksum(buf).to_bytes(2, 'little')
    return bytes(buf)


def checksum_ok(buf):
    return checksum(buf) == int.from_bytes(buf[-2:], 'little')


def find_node():
    for d in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        ue = open(f'{d}/device/uevent').read()
        phys = next((l for l in ue.splitlines() if l.startswith('HID_PHYS=')), '')
        if f'{VID:08X}:{PID:08X}' in ue and phys.endswith('/input3'):
            return '/dev/' + os.path.basename(d)
    raise KoneXPError(tr('Kone XP (Interface 3) nicht gefunden'))


class KoneXP:
    def __init__(self, node=None, backup_dir=None):
        self.node = node or find_node()
        try:
            self.fd = os.open(self.node, os.O_RDWR)
        except PermissionError as e:
            raise KoneXPError(tr('Kein Zugriff auf {node} – udev-Regel installiert? ({err})').format(
                node=self.node, err=e))
        self.backup_dir = backup_dir

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- Rohzugriff -------------------------------------------------------

    def get(self, rid):
        n = SIZES[rid]
        buf = bytearray(n)
        buf[0] = rid
        fcntl.ioctl(self.fd, _ioc(3, 0x07, n), buf)  # HIDIOCGFEATURE
        return bytes(buf)

    def _set(self, data):
        if data[0] not in WRITABLE:
            raise KoneXPError(tr('Report 0x{rid:02x} ist gesperrt').format(rid=data[0]))
        if len(data) != SIZES[data[0]]:
            raise KoneXPError(tr('Report 0x{rid:02x}: Länge {got} != {want}').format(
                rid=data[0], got=len(data), want=SIZES[data[0]]))
        buf = bytearray(data)
        fcntl.ioctl(self.fd, _ioc(3, 0x06, len(buf)), buf)  # HIDIOCSFEATURE
        self._wait_ack()

    def _wait_ack(self):
        for _ in range(ACK_TRIES):
            time.sleep(ACK_DELAY)
            status = self.get(0x04)[1]
            if status == ACK_OK:
                return
            if status == ACK_ERR:
                raise KoneXPError(tr('Gerät meldet Fehler (Ack 0x02)'))
            if status != ACK_BUSY:
                return  # unbekannter Status: wie Swarm nicht weiter warten
        raise KoneXPError(tr('Timeout: Gerät bleibt busy'))

    def select(self, profile, req):
        self._set(bytes([0x04, profile, req, 0x00]))

    # --- Lesen ------------------------------------------------------------

    def active_profile(self):
        return self.get(0x05)[2]

    def read_settings(self, profile):
        self.select(profile, SEL_SETTINGS)
        return self.get(0x06)

    def read_buttons(self, profile):
        self.select(profile, SEL_BUTTONS)
        return self.get(0x07)

    def read_macro(self, profile, slot):
        self.select(profile, slot)
        return self.get(0x08)

    def read_back(self, data):
        """Liest den Report zurück, der `data` entspricht (gleiches Profil/Slot)."""
        rid = data[0]
        if rid == 0x06:
            return self.read_settings(data[2])
        if rid == 0x07:
            return self.read_buttons(data[2])
        if rid == 0x08:
            return self.read_macro(data[3], data[4])
        return self.get(rid)

    # --- Schreiben --------------------------------------------------------

    def _backup(self, data):
        if not self.backup_dir:
            return
        os.makedirs(self.backup_dir, exist_ok=True)
        name = f'{time.strftime("%Y%m%d-%H%M%S")}-r{data[0]:02x}-before.bin'
        with open(os.path.join(self.backup_dir, name), 'wb') as f:
            f.write(data)

    def write(self, data, verify=True):
        """Schreibt einen Report sicher: Backup, SET+Ack, Rücklesen, ggf. Restore.

        `data` wird bei Checksummen-Reports automatisch neu summiert.
        Gibt die zurückgelesenen Bytes zurück.
        """
        rid = data[0]
        if rid in CHECKSUMMED:
            data = with_checksum(data)
        before = self.read_back(data) if verify else None
        if before is not None:
            self._backup(before)
        self._set(data)
        if not verify:
            return None
        after = self.read_back(data)
        if after != data:
            if before is not None:
                self._set(before)
            raise KoneXPError(tr('Verify fehlgeschlagen für 0x{rid:02x}, Backup zurückgeschrieben').format(rid=rid))
        return after

    def set_active_profile(self, profile):
        if not 0 <= profile <= 4:
            raise KoneXPError(tr('Profil 0..4'))
        self._set(bytes([0x05, 0x04, profile, 0x05]))
        if self.active_profile() != profile:
            raise KoneXPError(tr('Profilwechsel nicht übernommen'))
