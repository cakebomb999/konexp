import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ['KONEXP_LANG'] = 'de'  # Tests prüfen deutsche Quelltexte
