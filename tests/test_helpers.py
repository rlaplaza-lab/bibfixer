from bibliography import helpers


def test_get_bib_entries(tmp_path):
    bib = tmp_path / "sample.bib"
    bib.write_text("""@article{Key1,
  title={Title},
}

@book{Key2,
  author={Someone},
}
""")
    entries = helpers.get_bib_entries(bib)
    assert entries == {"Key1", "Key2"}


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
