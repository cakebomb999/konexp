"""Pfade für Laufzeitdaten (XDG) und optionale lokale Ressourcen."""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    base = os.environ.get('XDG_DATA_HOME') or os.path.expanduser('~/.local/share')
    return os.path.join(base, 'konexp')


BACKUP_DIR = os.path.join(data_dir(), 'backup')
UDEV_RULE = os.path.join(ROOT, 'udev', '70-kone-xp.rules')

# Optional: Grafiken aus einer lokal installierten ROCCAT-Swarm-Kopie (proprietär, nicht im Repo).
# Ohne sie zeichnet die GUI eine eigene Skizze.
RES_DIR = os.environ.get('KONEXP_SWARM_RES') or os.path.join(ROOT, 'extracted', 'plugin', 'res')
