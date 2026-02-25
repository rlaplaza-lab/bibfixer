from bibfixer import validation


def test_check_file_correspondence(tmp_path, monkeypatch):
    # check only considers main.tex (legacy behaviour)
    tex = tmp_path / "main.tex"
    tex.write_text("dummy")
    bib = tmp_path / "main.bib"
    bib.write_text("@article{A,title={T}}")
    monkeypatch.chdir(tmp_path)
    ok = validation.check_file_correspondence()
    assert ok
    # missing case: remove bib file
    bib.unlink()
    assert not validation.check_file_correspondence()


def test_check_unescaped_percent(tmp_path, monkeypatch):
    bib = tmp_path / "p.bib"
    # one entry with unescaped % plus other normal
    bib.write_text("""@article{X,
  title={100% sure},
}
""")
    monkeypatch.chdir(tmp_path)
    assert validation.check_unescaped_percent() >= 1
    bib.write_text("""@article{X,
  title={100\\% sure},
}
""")
    assert validation.check_unescaped_percent() == 0


def test_duplicate_key_and_doi(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b1 = tmp_path / "one.bib"
    b2 = tmp_path / "two.bib"
    b1.write_text("""@article{A,doi={10.1000/xyz}}
""")
    b2.write_text("""@article{A,doi={10.1000/xyz}}
""")
    # there is duplicate key across files
    assert validation.check_duplicate_keys()
    # duplicate doi with same key counts as one issue
    assert validation.check_duplicate_dois() == 0
    # change key in second entry (duplicate key no longer exists)
    b2.write_text("""@article{B,doi={10.1000/xyz}}
""")
    assert not validation.check_duplicate_keys()
    assert validation.check_duplicate_dois() == 1


def test_check_duplicate_titles(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    b1 = tmp_path / "one.bib"
    b2 = tmp_path / "two.bib"
    b1.write_text("""@article{A,title={Same}}
""")
    b2.write_text("""@article{B,title={same}}
""")
    assert validation.check_duplicate_titles() == 1


def test_validate_bibliography_and_citations(tmp_path, monkeypatch):
    tex = tmp_path / "main.tex"
    tex.write_text(r"cite \cite{A}")
    bib = tmp_path / "main.bib"
    bib.write_text("""@article{A,title={T}}
""")
    monkeypatch.chdir(tmp_path)
    assert validation.validate_bibliography()
    # missing citation
    tex.write_text(r"cite \cite{B}")
    assert not validation.validate_bibliography()
