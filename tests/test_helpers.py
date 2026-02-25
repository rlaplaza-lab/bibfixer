import re

from bibfixer import helpers


def test_get_corresponding_bib(tmp_path, monkeypatch):
    # create structure with main.tex and references.bib
    tex = tmp_path / "main.tex"
    tex.write_text("dummy")
    bib = tmp_path / "references.bib"
    bib.write_text("")
    monkeypatch.chdir(tmp_path)
    # helper returns a resolved path
    assert helpers.get_corresponding_bib(tex) == bib.resolve()

    # case with matching name
    other_tex = tmp_path / "chapter1.tex"
    other_tex.write_text("")
    other_bib = tmp_path / "chapter1.bib"
    other_bib.write_text("")
    assert helpers.get_corresponding_bib(other_tex) == other_bib

    # no bib available
    no_tex = tmp_path / "unknown.tex"
    no_tex.write_text("")
    assert helpers.get_corresponding_bib(no_tex) is None


def test_collect_all_files(tmp_path, monkeypatch):
    # create section and root files
    (tmp_path / "sections").mkdir()
    fstex = tmp_path / "sections" / "sec.tex"
    fstex.write_text("")
    fsbib = tmp_path / "sections" / "sec.bib"
    fsbib.write_text("")
    roottex = tmp_path / "main.tex"
    roottex.write_text("")
    rootbib = tmp_path / "references.bib"
    rootbib.write_text("")
    monkeypatch.chdir(tmp_path)
    tex_files = helpers.collect_all_tex_files()
    assert set(p.name for p in tex_files) == {"sec.tex", "main.tex"}
    bib_files = helpers.collect_all_bib_files()
    assert set(p.name for p in bib_files) == {"sec.bib", "references.bib"}


def test_extract_and_update_citations(tmp_path):
    tex = tmp_path / "foo.tex"
    tex.write_text(r"""This is a citation \cite{A,B} and another \citet{C}.""")
    keys = helpers.extract_citations_from_tex(tex)
    assert keys == {"A", "B", "C"}

    mapping = {"A": "A1", "C": "C1"}
    helpers.update_tex_citations([tex], mapping)
    new = tex.read_text()
    assert "A1" in new and "C1" in new
    assert "cite{A,B}" not in new


def test_update_tex_deduplicates(tmp_path):
    tex = tmp_path / "foo.tex"
    tex.write_text(r"This cites \cite{X,Y,Z}.")
    # map X and Y to same new key
    mapping = {"X": "K", "Y": "K"}
    helpers.update_tex_citations([tex], mapping)
    content = tex.read_text()
    # two original keys map to K; duplicates should be collapsed but Z should
    # remain
    assert content.strip().endswith("cite{K, Z}.")


def test_sanitize_citation_keys(tmp_path):
    bib = tmp_path / "test.bib"
    bib.write_text("""@article{Bad!Key,
  title={foo},
}
@article{good_key,
  title={bar},
}
""")
    mapping = helpers.sanitize_citation_keys(bib)
    # the bad key should be sanitized to remove the exclamation mark
    assert mapping == {"Bad!Key": "BadKey"}
    assert "BadKey" in bib.read_text()


def test_sanitize_no_changes(tmp_path):
    bib = tmp_path / "empty.bib"
    bib.write_text("")
    mapping = helpers.sanitize_citation_keys(bib)
    assert mapping == {}


def test_generate_and_standardize_keys(tmp_path):
    # two entries that would initially map to same canonical key
    bib = tmp_path / "dup.bib"
    bib.write_text("""@article{first,
  author={Smith, John and Doe, Jane},
  year={2021},
  journal={Journal of Testing},
  title={An Example Study},
}
@article{second,
  author={Smith, John and Doe, Jane},
  year={2021},
  journal={Journal of Testing},
  title={Another Example},
}
""")
    mapping = helpers.standardize_citation_keys(bib)
    # there should be two entries standardized; keys should differ by a suffix on second
    assert len(mapping) == 2
    assert all(k.startswith("Smith2021J") for k in mapping.values())
    content = bib.read_text()
    # ensure two different keys exist in file
    keys = set(m.group(1) for m in re.finditer(r"@\w+\{([^,]+)", content))
    assert len(keys) == 2


def test_generate_citation_key_various():
    # test _generate_citation_key output directly
    entry = {
        "author": "Doe, Jane and Roe, Richard",
        "year": "2020",
        "journal": "Science Advances",
        "title": "Quantum Mechanics"
    }
    key = helpers._generate_citation_key(entry)
    assert key.startswith("Doe2020SAQuantum")
    # numeric start gives empty key when no alphabetic content is found
    entry2 = {"author": "1234","year":"","journal":"","title":""}
    assert helpers._generate_citation_key(entry2) == ""


def test_citation_patterns_constant():
    # ensure the public constant is defined and matches expected regexes
    assert hasattr(helpers, 'CITATION_PATTERNS')
    pats = helpers.CITATION_PATTERNS
    assert isinstance(pats, list) and pats
    # a simple string containing each kind of citation should be parsed
    sample = r"\cite{A}\citep{B}, \citet{C} \citeauthor{D} \citeyear{E}"
    # manually apply patterns to extract keys
    found = set()
    for pattern in pats:
        for match in re.findall(pattern, sample):
            found.update(k.strip() for k in match.split(','))
    assert found == {"A", "B", "C", "D", "E"}
