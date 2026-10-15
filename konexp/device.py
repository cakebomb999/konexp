"""HID-Transport für die ROCCAT Kone XP (Interface 3) und Kone XP Air (Interface 2), Feature-Reports via hidraw.

Protokoll: docs/PROTOCOL.md, docs/PROTOCOL-XP-AIR.md.
Jeder Write läuft über `KoneXP.write()`: Sperrliste prüfen, Ack pollen, zurücklesen,
bei Abweichung Backup wiederherstellen. `KoneXPAir` bildet dieselbe Schnittstelle auf die
Kommandos der Air ab (gleiche Datenblöcke, andere Hülle).
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

# --- Kone XP Air (docs/PROTOCOL-XP-AIR.md) ---------------------------------
# 0x2CB2 Maus per Kabel, 0x2CB6 2,4-GHz-Dongle. Dock (0x2CB8) spricht ein anderes Protokoll.
AIR_WIRED, AIR_DONGLE = 0x2CB2, 0x2CB6
AIR_PIDS = (AIR_WIRED, AIR_DONGLE)
AIR_USAGE_PAGE = bytes([0x06, 0x03, 0xff])   # Report-Descriptor-Item Usage Page 0xFF03
AIR_FRAME, AIR_CHUNK = 30, 25                # Feature-Report 0x06: [06 ziel cmd op len daten…]
AIR_OP_WRITE, AIR_OP_READ = 0x06, 0x07
AIR_WRITE_DELAY, AIR_READ_DELAY = 0.08, 0.09  # wie Swarm
# Report-ID der Kone XP -> (Kommando, Blocklänge). Die Air speichert dieselben Report-Formate.
AIR_BLOCKS = {0x06: (0x46, 78), 0x07: (0x47, 125)}
AIR_DEBOUNCE_SIZE = 19
# Nur diese Kommandos sendet konexp überhaupt. Nicht dabei, weil riskant: 0x49 (u. a. Werksreset),
# 0x01 (Pairing), 0x12 (Bootloader), 0x31–0x34 (Firmware-Update), 0x4b (Geräte-IDs).
AIR_READABLE = {0x13, 0x25, 0x35, 0x43, 0x44, 0x45, 0x46, 0x47, 0x4f}
AIR_WRITABLE = {0x43, 0x45, 0x46, 0x47}
AIR_SOFTWARE = 0x4e  # „Software aktiv“: Swarm sendet [01 00 00 ff] beim Öffnen, [00 00 00 ff] beim Schließen
# Schreiben ist für die Air noch nicht an echter Hardware bestätigt. Freischalten: KONEXP_AIR_WRITE=1
AIR_WRITE = os.environ.get('KONEXP_AIR_WRITE') == '1'


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


def _pid(sysdir):
    ue = open(f'{sysdir}/device/uevent').read()
    return next((p for p in (PID, *AIR_PIDS) if f'{VID:08X}:{p:08X}' in ue), None), ue


def find_node():
    """(node, pid) des Konfigurations-Interfaces: Kone XP Interface 3, Kone XP Air Usage Page 0xFF03."""
    seen, air = [], []
    for d in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        pid, ue = _pid(d)
        if pid is None:
            continue
        phys = next((l for l in ue.splitlines() if l.startswith('HID_PHYS=')), '')
        name = os.path.basename(d)
        if pid == PID and phys.endswith('/input3'):
            return '/dev/' + name, pid
        if pid in AIR_PIDS and AIR_USAGE_PAGE in open(f'{d}/device/report_descriptor', 'rb').read():
            air.append(('/dev/' + name, pid))
            continue
        seen.append(f'{name} ({phys[9:] or "?"})')
    if air:  # Kabel vor Dongle: Kabel spricht die Maus direkt an
        return min(air, key=lambda a: a[1] != AIR_WIRED)
    if seen:
        raise KoneXPError(tr('Maus gefunden, aber nicht das Konfigurations-Interface: {nodes}').format(
            nodes=', '.join(seen)))
    raise KoneXPError(tr('Kone XP / Kone XP Air (USB 1e7d:2c8b, 2cb2, 2cb6) nicht gefunden – angeschlossen? '
                         'Prüfen mit: lsusb'))


def open_device(node=None, backup_dir=None):
    """Passende Geräteklasse für den Knoten (automatisch gesucht, wenn None)."""
    if node is None:
        node, pid = find_node()
    else:
        pid = _pid(f'/sys/class/hidraw/{os.path.basename(node)}')[0]
    if pid in AIR_PIDS:
        return KoneXPAir(node, backup_dir, pid)
    return KoneXP(node, backup_dir)


class KoneXP:
    NAME = 'Kone XP'
    pid = PID
    readonly = False

    def __init__(self, node=None, backup_dir=None):
        self.node = node or find_node()[0]
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

    def _check(self, data):
        """Darf `data` geschrieben werden? Nur Prüfung, kein Gerätezugriff."""
        if data[0] not in WRITABLE:
            raise KoneXPError(tr('Report 0x{rid:02x} ist gesperrt').format(rid=data[0]))
        if len(data) != SIZES[data[0]]:
            raise KoneXPError(tr('Report 0x{rid:02x}: Länge {got} != {want}').format(
                rid=data[0], got=len(data), want=SIZES[data[0]]))

    def _set(self, data):
        self._check(data)
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
        self._check(data)
        before = self.read_back(data) if verify else None
        if before is not None:
            self._backup(before)
        try:
            self._set(data)
        except (OSError, KoneXPError) as e:
            # Abbruch mitten im Schreiben (Air: Block in mehreren Stücken) -> Backup zurück, falls möglich
            if before is None:
                raise
            try:
                self._set(before)
            except (OSError, KoneXPError):
                raise KoneXPError(tr('Schreiben von 0x{rid:02x} abgebrochen ({err}); Backup ließ sich nicht '
                                     'zurückschreiben, Datei liegt in {path}').format(
                                         rid=rid, err=e, path=self.backup_dir)) from e
            raise KoneXPError(tr('Schreiben von 0x{rid:02x} abgebrochen ({err}), Backup zurückgeschrieben').format(
                rid=rid, err=e)) from e
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


class KoneXPAir(KoneXP):
    """Kone XP Air per Kabel oder Dongle. Gleiche Schnittstelle wie KoneXP:
    0x06/0x07 sind die Blöcke 0x46/0x47, 0x11 ist Debounce 0x43, 0x05 und 0x0f werden aus 0x45/0x4f gebildet."""
    NAME = 'Kone XP Air'

    def __init__(self, node=None, backup_dir=None, pid=AIR_WIRED):
        super().__init__(node, backup_dir)
        self.pid = pid
        self.target = int(pid != AIR_WIRED)  # 1 = über den Dongle an die Maus
        self.readonly = not AIR_WRITE
        self.profile_count = 5
        self.init_log = {}  # Antworten beim Öffnen, für dump
        if pid == AIR_DONGLE:
            self.init_log['link'] = self.link()
        self.init_log['software'] = self._software(1)

    def close(self):
        self._software(0)
        super().close()

    def _software(self, on):
        """Wie Swarm: „Software aktiv“ setzen. Fehler nur notieren, Swarm bricht hier auch nicht ab."""
        try:
            self._send(AIR_SOFTWARE, bytes([on, 0, 0, 0xff]))
            return 'ok'
        except (OSError, KoneXPError) as e:
            return f'ERROR {e}'

    def link(self):
        """Wie Swarm beim Öffnen des Dongles: Op 04, dann Op 05 (Ziel 0, Kommando 0), je pollen bis Status ≠ 0.
        Status 08 und Byte 13 == 1 heißt Maus verbunden. Gibt die Antwort-Frames zurück."""
        frames = []
        for op in (0x04, 0x05):
            buf = self._frame(0, op, target=0)
            fcntl.ioctl(self.fd, _ioc(3, 0x06, AIR_FRAME), buf)
            for _ in range(20):  # ponytail: festes Limit 20×50 ms, Swarm pollt Schritt 1 ohne Limit
                time.sleep(0.05)
                fcntl.ioctl(self.fd, _ioc(3, 0x07, AIR_FRAME), buf)
                if buf[3]:
                    break
            frames.append(bytes(buf).hex())
            if buf[3] != 0x08:
                break
        self.linked = len(frames) == 2 and buf[3] == 0x08 and buf[13] == 1
        return frames

    def _frame(self, cmd, op, data=b'', target=None):
        buf = bytearray(AIR_FRAME)
        buf[:5] = bytes([0x06, self.target if target is None else target, cmd, op, len(data)])
        buf[5:5 + len(data)] = data
        return buf

    def command(self, cmd, data, ack=True):
        """Schreib-Frame senden (nur wenn Schreiben freigeschaltet ist)."""
        self._check_writable()
        self._send(cmd, data, ack)

    def _send(self, cmd, data, ack=True):
        """Schreib-Frame ohne Nur-Lesen-Prüfung. Mit ack: Status 0x44 lesen, Byte 0 == 1 heißt angenommen."""
        if cmd not in AIR_WRITABLE | {AIR_SOFTWARE}:
            raise KoneXPError(tr('Kommando 0x{cmd:02x} ist gesperrt').format(cmd=cmd))
        fcntl.ioctl(self.fd, _ioc(3, 0x06, AIR_FRAME), self._frame(cmd, AIR_OP_WRITE, data))
        time.sleep(AIR_WRITE_DELAY)
        if ack and self.query(0x44, 17)[0] != 1:
            raise KoneXPError(tr('Gerät bestätigt Kommando 0x{cmd:02x} nicht').format(cmd=cmd))

    def query(self, cmd, n, target=None, frame=False):
        """Lese-Frame senden, Antwort holen, n Datenbytes ab Byte 5 (frame=True: ganze Antwort, Diagnose)."""
        if cmd not in AIR_READABLE:
            raise KoneXPError(tr('Kommando 0x{cmd:02x} ist gesperrt').format(cmd=cmd))
        buf = self._frame(cmd, AIR_OP_READ, target=target)
        time.sleep(AIR_READ_DELAY)
        fcntl.ioctl(self.fd, _ioc(3, 0x06, AIR_FRAME), buf)
        time.sleep(AIR_READ_DELAY)
        fcntl.ioctl(self.fd, _ioc(3, 0x07, AIR_FRAME), buf)
        if frame:
            return bytes(buf)
        if buf[3] not in (0x00, 0x08):  # 00 beschäftigt (Swarm ignoriert das beim Lesen), 08 ok
            raise KoneXPError(tr('Maus antwortet nicht auf 0x{cmd:02x} (Status 0x{st:02x}) – eingeschaltet und '
                                 'mit dem Dongle verbunden?').format(cmd=cmd, st=buf[3]))
        return bytes(buf[5:5 + n])

    def read_block(self, cmd, sub, size):
        """Block in 25-B-Stücken: je Stück Kopf [index, sub] schreiben (ändert nichts), dann lesen."""
        out = b''
        for idx in range(-(-size // AIR_CHUNK)):
            self._send(cmd, bytes([idx, sub]), ack=False)  # Kopf wählt nur das Stück aus
            out += self.query(cmd, min(AIR_CHUNK, size - len(out)))
        return out

    def write_block(self, cmd, sub, data):
        for idx in range(-(-len(data) // AIR_CHUNK)):
            self.command(cmd, bytes([idx, sub]))
            self.command(cmd, data[idx * AIR_CHUNK:(idx + 1) * AIR_CHUNK])

    def _block(self, rid, profile):
        cmd, size = AIR_BLOCKS[rid]
        data = self.read_block(cmd, profile, size)
        if data[:2] != bytes([rid, size]):  # Blöcke beginnen mit [Report-ID, Länge]
            raise KoneXPError(tr('Ungültige Antwort auf 0x{cmd:02x} – Maus eingeschaltet und mit dem Dongle '
                                 'verbunden?').format(cmd=cmd))
        return data

    def get(self, rid):
        if rid == 0x05:  # Form der Kone XP: [05 04 profil 05]
            return bytes([0x05, 0x04, self.active_profile(), 0x05])
        if rid == 0x11:
            return self.query(0x43, AIR_DEBOUNCE_SIZE)
        if rid == 0x0f:  # DCU 0x4f [modus, x] in der Form der Kone XP: [0f 06 modus x 00 00]
            return bytes([0x0f, 0x06, *self.query(0x4f, 2), 0, 0])
        raise KoneXPError(tr('Report 0x{rid:02x} gibt es bei der Kone XP Air nicht').format(rid=rid))

    def select(self, profile, req):
        pass  # kein Select-Zustand; jeder Blockzugriff adressiert sein Profil selbst

    def active_profile(self):
        active, self.profile_count = self.query(0x45, 2)
        return active

    def read_settings(self, profile):
        return self._block(0x06, profile)

    def read_buttons(self, profile):
        return self._block(0x07, profile)

    def read_macro(self, profile, slot):
        raise KoneXPError(tr('Makros der Kone XP Air werden noch nicht unterstützt'))

    def read_back(self, data):
        if data[0] in AIR_BLOCKS:
            return self._block(data[0], data[2])
        return self.get(data[0])

    def _check_writable(self):
        if self.readonly:
            raise KoneXPError(tr('Kone XP Air: nur Lesen. Schreiben ist an echter Hardware noch nicht bestätigt '
                                 '(freischalten mit KONEXP_AIR_WRITE=1).'))

    def _check(self, data):
        self._check_writable()
        rid = data[0]
        if not (rid in AIR_BLOCKS and len(data) == AIR_BLOCKS[rid][1]
                or rid == 0x11 and len(data) == AIR_DEBOUNCE_SIZE):
            raise KoneXPError(tr('Report 0x{rid:02x} ist gesperrt').format(rid=rid))

    def _set(self, data):
        self._check(data)
        if data[0] in AIR_BLOCKS:
            self.write_block(AIR_BLOCKS[data[0]][0], data[2], data)
        else:
            self.command(0x43, data)

    def set_active_profile(self, profile):
        self._check_writable()
        count = self.profile_count
        if not 0 <= profile < count:
            raise KoneXPError(tr('Profil 0..{n}').format(n=count - 1))
        self.command(0x45, bytes([profile, count]))
        if self.active_profile() != profile:
            raise KoneXPError(tr('Profilwechsel nicht übernommen'))

    def firmware(self):
        """Firmware-Versionen als Zahl wie in den Swarm-Dateinamen (Maus 51 = 0.051, Dongle 107 = 1.07)."""
        b = self.query(0x35, 13)
        out = {'mouse': ((b[1] * 10 + b[3]) * 10 + b[2]) * 10 + b[5]}
        if self.pid == AIR_DONGLE:
            a, c = self.query(0x13, 2, target=0)
            out['dongle'] = a * 100 + c
        return out
