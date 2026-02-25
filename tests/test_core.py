import re

from bibliography.core import (
    walk_fields,
    _join_multiline_values,
    field_transform,
    parse_bib_file,
    write_bib_file,
    BibFile,
)


class DummyBib:
    """Minimal object mimicking the required interface for walk_fields."""

    def __init__(self, entries):
        self.entries = entries


def test_walk_fields_yields_expected_tuples():
    # prepare a fake bibliography with two entries
    entries = [
        {"title": "First", "year": "2020"},
        {"author": "Smith", "pages": "1-10"},
    ]
    bib = DummyBib(entries)

    seen = []
    for entry, field, value in walk_fields(bib):
        seen.append((id(entry), field, value))

    # There should be exactly four field tuples, in the order of insertion
    assert len(seen) == 4
    assert seen[0][1:] == ("title", "First")
    assert seen[1][1:] == ("year", "2020")
    assert seen[2][1:] == ("author", "Smith")
    assert seen[3][1:] == ("pages", "1-10")

    # ensure that modifying the entry while iterating is possible
    bib = DummyBib([{"foo": "bar"}])
    for entry, field, value in walk_fields(bib):
        entry[field] = value.upper()
    assert bib.entries[0]["foo"] == "BAR"


def test_join_multiline_values():
    # list input should be concatenated with spaces
    assert _join_multiline_values(["a", "b", 123]) == "a b 123"

    # string with newline should flatten to single spaced string
    multi = "line1\nline2\n   line3"
    assert _join_multiline_values(multi) == "line1 line2 line3"

    # non-list, non-multiline returns unchanged
    assert _join_multiline_values(42) == 42
    assert _join_multiline_values("single line") == "single line"


def test_field_transform_decorator_and_io(tmp_path):
    sample = """@article{foo,
  title={hello},
  year={2020},
}
"""
    path = tmp_path / "foo.bib"
    path.write_text(sample)
    bib = BibFile(path)

    @field_transform
    def shout(value):
        if isinstance(value, str):
            return value.upper()
        return value

    changed = shout(bib)
    assert changed >= 1
    assert bib.entries[0]["title"] == "HELLO"

    # test convenience functions
    entries = parse_bib_file(path)
    assert isinstance(entries, list) and entries

    # modify database via write_bib_file
    db = bib.database
    db.entries[0]["title"] = "WORLD"
    write_bib_file(path, db)
    # re-read and verify
    bib2 = BibFile(path)
    assert bib2.entries[0]["title"] == "WORLD"


def test_field_transform_propagates_exceptions(tmp_path):
    # a transform that raises should not be swallowed by the decorator
    path = tmp_path / "err.bib"
    path.write_text("""@article{e,
  title={ok},
}
""")
    bib = BibFile(path)

    @field_transform
    def boom(value):
        raise RuntimeError("oops")

    try:
        boom(bib)
    except RuntimeError as exc:
        assert "oops" in str(exc)
    else:
        # if no exception was raised, that's a problem
        assert False, "field_transform should propagate exceptions"
