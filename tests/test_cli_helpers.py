import sys
import pathlib

# ensure workspace root is on path so that the bibliography package can be imported
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from bibliography import cli
from bibliography.core import BibFile


def test_choose_best_entry_simple():
    e1 = {'ID': 'A', 'title': 'T', 'author': 'X'}
    e2 = {'ID': 'A', 'title': 'T'}
    best = cli.choose_best_entry([('f1', e1), ('f2', e2)])
    assert best is e1


def test_choose_best_key_scores():
    entries = [{'key': 'smith2020'}, {'key': 'X'}, {'key': 'a_bad_key'}]
    # lowercase smith2020 loses to single uppercase X according to scoring rules
    best = cli.choose_best_key(entries)
    assert best == 'X'
    # ensure keys with uppercase first letter score higher than lowercase
    assert cli.choose_best_key([{'key': 'lowercase'}, {'key': 'Uppercase'}]) == 'Uppercase'


def test_find_and_synchronize_duplicates(tmp_path):
    # create two bib files that share a key
    bib1 = tmp_path / 'one.bib'
    bib2 = tmp_path / 'two.bib'
    bib1.write_text("""@article{KeyA,
  title={Hello},
}
""")
    bib2.write_text("""@article{KeyA,
  title={World},
  author={Someone},
}
""")
    duplicates = cli.find_duplicates([bib1, bib2])
    assert 'KeyA' in duplicates
    # synchronize should prefer entry from bib2 (more fields)
    cli.synchronize_duplicates([bib1, bib2], duplicates)
    # after sync both files should have identical content
    assert bib1.read_text() == bib2.read_text()
    assert 'Someone' in bib1.read_text()


def test_fix_unescaped_percent(tmp_path):
    bib = tmp_path / 'test.bib'
    bib.write_text("""@article{K,
  title={100% sure},
}
""")
    bf = BibFile(bib)
    changed = cli.fix_unescaped_percent(bf)
    assert changed >= 1
    content = bib.read_text()
    assert r"100\% sure" in content
    # running again should not alter the file contents further
    before = bib.read_text()
    bf2 = BibFile(bib)
    cli.fix_unescaped_percent(bf2)  # may return >0 but should not change file
    assert bib.read_text() == before


def test_uncomment_bibtex_entries(tmp_path):
    bib = tmp_path / 'comment.bib'
    # simple commented entry introduced by bibfmt
    bib.write_text("""@comment{@article{X,
  title={Foo},
}}
""")
    fixed = cli.uncomment_bibtex_entries(bib)
    assert fixed == 1
    txt = bib.read_text()
    assert "@article{X" in txt and "@comment" not in txt


def test_fix_html_entities(tmp_path):
    bib = tmp_path / 'html.bib'
    bib.write_text("""@article{H,
  title={A &amp; B &lt; C &gt; D &quot;E&quot; &apos;F&apos; & G},
}
""")
    fixed = cli.fix_html_entities(bib)
    assert isinstance(fixed, int) and fixed > 0
    content = bib.read_text()
    # ensure html entities converted
    assert "\&" in content and "<" in content and '"' in content


def test_fix_problematic_unicode(tmp_path):
    bib = tmp_path / 'unicode.bib'
    # include a box drawing character and combining accent
    bib.write_text("""@article{U,
  title={Test ─ a\u0301b},
}
""")
    fixed = cli.fix_problematic_unicode(bib)
    assert fixed > 0
    content = bib.read_text()
    assert "--" in content or "\\'" in content


def test_fix_invalid_utf8_bytes(tmp_path):
    bib = tmp_path / 'bad.bib'
    # write bytes directly with pattern1: X\\\xcc\x88 -> X\" after fix
    with open(bib, 'wb') as f:
        f.write(b"Valid\\\\\xcc\x88Text")
    fixed = cli.fix_invalid_utf8_bytes(bib)
    assert fixed >= 1
    content = bib.read_text(errors='ignore')
    assert '\\"' in content  # replaced pattern


def test_choose_best_key_tiebreaker():
    # when keys are equally scored shorter should win
    entries = [{'key': 'Smith2020'}, {'key': 'Smith2020long'}]
    assert cli.choose_best_key(entries) == 'Smith2020'

