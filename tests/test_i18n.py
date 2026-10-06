"""Übersetzungskatalog: vollständig, Platzhalter konsistent, .po-Lesen/Schreiben verlustfrei."""
import os
import string
import tempfile
import unittest

from konexp import i18n


def fields(text):
    return sorted(f for _lit, f, _spec, _conv in string.Formatter().parse(text) if f is not None)


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.refs = i18n.extract()

    def test_extract_finds_texts(self):
        self.assertGreater(len(self.refs), 50)

    def test_catalogs_complete_and_placeholders_match(self):
        for lang in i18n.LANGUAGES:
            if lang == i18n.SOURCE_LANG:
                continue
            cat = i18n.read_po(i18n.po_path(lang))
            missing = [m for m in self.refs if not cat.get(m, ('',))[0]]
            self.assertEqual(missing, [], f'{lang}: unübersetzt – python3 -m konexp.i18n extract')
            for msgid, (msgstr, _fuzzy) in cat.items():
                if msgstr:
                    self.assertEqual(fields(msgid), fields(msgstr), f'{lang}: Platzhalter in {msgid!r}')

    def test_po_roundtrip(self):
        entries = {'eins': ('one', False), 'Zeile 1\nZeile 2\n': ('line 1\nline 2\n', True),
                   'Zitat "x" \\ y': ('quote "x" \\ y', False)}
        refs = {k: ['a.py:1'] for k in entries}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'xx.po')
            i18n.write_po(path, 'xx', entries, refs)
            self.assertEqual(i18n.read_po(path), entries)

    def test_tr_switches_language(self):
        try:
            i18n.set_language('en')
            cat = i18n.read_po(i18n.po_path('en'))
            msgid, (msgstr, _f) = next((k, v) for k, v in cat.items() if v[0])
            self.assertEqual(i18n.tr(msgid), msgstr)
            i18n.set_language('de')
            self.assertEqual(i18n.tr(msgid), msgid)
        finally:
            i18n.set_language('de')


if __name__ == '__main__':
    unittest.main()
