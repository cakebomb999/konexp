"""Übersetzung: Quelltexte sind deutsch, Kataloge liegen als gettext-.po in konexp/locale/<lang>.po.

tr() übersetzt zur Laufzeit. Viele Texte sind Modulkonstanten (NAMES, FIELDS06, …), daher muss
set_language() vor dem Import der übrigen Module laufen; ein Sprachwechsel greift nach Neustart.

Sprache: set_language(arg) > $KONEXP_LANG > gespeicherte Einstellung > Englisch.

  python3 -m konexp.i18n extract   # tr('…')-Aufrufe sammeln, locale/*.po abgleichen
"""
import ast
import os
import sys

LOCALE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'locale')
SOURCE_LANG = 'de'
DEFAULT_LANG = 'en'
LANGUAGES = {'de': 'Deutsch', 'en': 'English'}

_catalog = {}
_lang = SOURCE_LANG


def _settings_file():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'konexp', 'language')


def saved_language():
    try:
        with open(_settings_file(), encoding='utf-8') as f:
            return f.read().strip() or None
    except OSError:
        return None


def save_language(lang):
    path = _settings_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(lang + '\n')


def set_language(lang=None):
    """Sprache wählen und Katalog laden. Gibt die tatsächlich gesetzte Sprache zurück."""
    global _lang, _catalog
    lang = lang or os.environ.get('KONEXP_LANG') or saved_language() or DEFAULT_LANG
    if lang not in LANGUAGES:
        lang = SOURCE_LANG
    _lang = lang
    _catalog = {} if lang == SOURCE_LANG else {k: v for k, (v, _f) in read_po(po_path(lang)).items() if v}
    return lang


def language():
    return _lang


def tr(text):
    return _catalog.get(text, text)


# --- .po lesen/schreiben (Teilmenge: msgid/msgstr, #, fuzzy, mehrzeilige Strings) ------------

def po_path(lang):
    return os.path.join(LOCALE_DIR, f'{lang}.po')


def _unquote(s):
    return ast.literal_eval(s)


def read_po(path):
    """{msgid: (msgstr, fuzzy)} – Header (leere msgid) ausgelassen."""
    out = {}
    try:
        with open(path, encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    msgid = msgstr = None
    fuzzy = False
    cur = None

    def flush():
        if msgid:
            out[msgid] = (msgstr or '', fuzzy)

    for line in lines + ['']:
        line = line.strip()
        if line.startswith('msgid '):
            flush()
            msgid, msgstr, cur = _unquote(line[6:]), None, 'id'
        elif line.startswith('msgstr '):
            msgstr, cur = _unquote(line[7:]), 'str'
        elif line.startswith('"') and cur:
            if cur == 'id':
                msgid += _unquote(line)
            else:
                msgstr += _unquote(line)
        elif not line:
            flush()
            msgid = msgstr = cur = None
            fuzzy = False
        elif line.startswith('#,') and 'fuzzy' in line:
            fuzzy = True
    return out


def _quote(s):
    s = s.replace('\\', '\\\\').replace('"', '\\"').replace('\t', '\\t')
    parts = s.split('\n')
    if len(parts) == 1:
        return f'"{s}"'
    chunks = [p + '\\n' for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    return '""\n' + '\n'.join(f'"{c}"' for c in chunks)


def write_po(path, lang, entries, refs):
    """entries: {msgid: (msgstr, fuzzy)}, refs: {msgid: ['datei:zeile', …]} (Reihenfolge = Ausgabe)."""
    out = ['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"',
           f'"Language: {lang}\\n"', '']
    for msgid, where in refs.items():
        msgstr, fuzzy = entries.get(msgid, ('', False))
        out.append('#: ' + ' '.join(where))
        if fuzzy:
            out.append('#, fuzzy')
        out += ['msgid ' + _quote(msgid), 'msgstr ' + _quote(msgstr), '']
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))


# --- Extraktion ---------------------------------------------------------------------------------

def extract(root=None):
    """{msgid: ['pfad:zeile', …]} aller tr('Literal')-Aufrufe unter konexp/."""
    root = root or os.path.dirname(os.path.abspath(__file__))
    base = os.path.dirname(root)
    found = {}
    for dirpath, _dirs, files in sorted(os.walk(root)):
        for fn in sorted(files):
            if not fn.endswith('.py'):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read(), path)
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'tr'
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.setdefault(node.args[0].value, []).append(
                        f'{os.path.relpath(path, base)}:{node.lineno}')
    return found


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if args[:1] != ['extract']:
        print(__doc__)
        return 2
    refs = extract()
    for lang in LANGUAGES:
        if lang == SOURCE_LANG:
            continue
        path = po_path(lang)
        old = read_po(path)
        write_po(path, lang, old, refs)
        missing = sum(1 for m in refs if not old.get(m, ('',))[0])
        dropped = len(set(old) - set(refs))
        print(f'{path}: {len(refs)} Texte, {missing} unübersetzt, {dropped} entfernt')
    return 0


set_language()

if __name__ == '__main__':
    sys.exit(main())
