import sys
import pathlib

# ensure workspace root is on path so that the bibliography package can be imported
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from bibliography.core import BibFile, _join_multiline_values


def test_bibfile_read_write(tmp_path):
    sample = """@article{key1,
  title={A Study},
  author={Doe, John},
}

@book{key2,
  title={Another},
  author={Smith, Jane},
}
"""
    path = tmp_path / "sample.bib"
    path.write_text(sample)

    bib = BibFile(path)
    assert len(bib.entries) == 2
    keys = {e.get("ID") for e in bib.entries}
    assert keys == {"key1", "key2"}

    # modify and write back
    bib.entries[0]["title"] = "Modified"
    bib.write()
    bib2 = BibFile(path)
    assert bib2.entries[0]["title"] == "Modified"


def test_multiline_value(tmp_path):
    sample = """@article{multi,
  title={First line
    second line},
  author={A, B},
}
"""
    path = tmp_path / "multi.bib"
    path.write_text(sample)

    bib = BibFile(path)
    entry = bib.entries[0]
    # bibtexparser may present the title as a list or a multiline string
    joined = _join_multiline_values(entry.get("title"))
    assert "First line" in joined
    assert "second line" in joined
    assert "\n" not in joined
