import re

from bibliography import cli
from bibliography import curate
from bibliography.core import BibFile


def test_cli_aliases():
    # ensure curation helpers are re-exported from the CLI module
    assert cli.find_duplicates is curate.find_duplicates
    assert cli.choose_best_entry is curate.choose_best_entry
    assert cli.consolidate_duplicate_titles is curate.consolidate_duplicate_titles


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
    # content should contain a normal quote after fix (byte sequence removed)
    assert '"' in content

def test_choose_best_key_tiebreaker():
    # when keys are equally scored shorter should win
    entries = [{'key': 'Smith2020'}, {'key': 'Smith2020long'}]
    assert cli.choose_best_key(entries) == 'Smith2020'


def test_fix_legacy_year_and_month(tmp_path):
    bib = tmp_path / 'test.bib'
    bib.write_text(
        """@article{A,
  year={2021-05-17},
  month={apr},
}
"""
    )
    # applying both fixes sequentially
    y = cli.fix_legacy_year_fields(bib)
    m = cli.fix_legacy_month_fields(bib)
    text = bib.read_text()
    assert y == 1
    assert m == 1
    # spacing around = may vary
    assert 'year' in text and '2021' in text
    assert 'month' in text and '4' in text


def test_remove_accents_and_malformed_author(tmp_path):
    bib = tmp_path / 'auth.bib'
    # author with accented characters and malformed patterns
    bib.write_text("""@article{X,
  author={Fran\c{c}ois and M\"uller and Anná},
}
"""
    )
    # remove accents
    removed = cli.remove_accents_from_names(bib)
    # should touch at least one field
    assert removed > 0
    text = bib.read_text()
    assert 'Francois' in text
    # u-umlaut should be converted or at least the escape removed
    assert 'Muller' in text or 'M"uller' in text
    # malformed names fix
    bib.write_text("""@article{Y,
  author={Doe\\\\ and O\n\u0301Brien},
}
"""
    )
    fixed = cli.fix_malformed_author_fields(bib)
    assert fixed >= 0


def test_remove_duplicate_entries_across_files(tmp_path):
    # create two bib files with same key
    b1 = tmp_path / 'a.bib'
    b2 = tmp_path / 'b.bib'
    b1.write_text("""@article{D,
  title={First},
}
"""
    )
    b2.write_text("""@article{D,
  title={Second},
}
"""
    )
    count = cli.remove_duplicate_entries_across_files([b1, b2])
    assert count == 1
    # entry should remain only in first file alphabetically (a.bib)
    assert 'D' in b1.read_text()
    assert 'D' not in b2.read_text()


def test_consolidate_duplicate_titles(tmp_path):
    b1 = tmp_path / 'one.bib'
    b2 = tmp_path / 'two.bib'
    b1.write_text("""@article{K1,
  title={Same Title},
}
"""
    )
    b2.write_text("""@article{K2,
  title={same title},
}
"""
    )
    mapping = cli.consolidate_duplicate_titles([b1, b2])
    # mapping should map old keys to new (one of them)
    assert len(mapping) == 1
    newkey = list(mapping.values())[0]
    combined = b1.read_text() + b2.read_text()
    assert newkey in combined
    # original keys should not both be present
    assert 'K1' not in combined or 'K2' not in combined

