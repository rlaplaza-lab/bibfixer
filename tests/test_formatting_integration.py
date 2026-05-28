from bibfixer.cli import format_bibliography_file


def test_format_bibliography_file_removes_fields(tmp_path):
    bib_path = tmp_path / "sample.bib"
    bib_path.write_text("""@article{key,
  title={Test},
  file={/some/path},
}
""")
    assert "file={/some/path}" in bib_path.read_text()

    format_bibliography_file(bib_path)

    content = bib_path.read_text()
    assert "file=" not in content
    assert "title" in content and "Test" in content


def test_curate_uses_formatter(tmp_path, monkeypatch):
    calls = []

    def fake_format(*args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr("bibfixer._internal.formatter.format_bibliography", fake_format)

    bib_file = tmp_path / "foo.bib"
    bib_file.write_text("""@article{key,
  title={Example},
}
""")

    from bibfixer.cli import process_bib_file

    process_bib_file(bib_file, create_backups=False)
    assert calls


def test_format_bibliography_file_warns_on_meta_change(tmp_path, monkeypatch, capsys):
    bib_path = tmp_path / "sample.bib"
    bib_path.write_text("""@article{key,
  title={Old Title},
  doi={10.1000/old},
}
""")

    def fake_format(*args, **kwargs):
        bib_path.write_text("""@article{key,
  title={New Title Completely Different},
  doi={10.1000/new},
}
""")

    monkeypatch.setattr("bibfixer._internal.formatter.format_bibliography", fake_format)
    format_bibliography_file(bib_path)
    out = capsys.readouterr().out
    assert "Warning: formatter appears to have altered title" in out
    assert "Warning: formatter changed DOI" in out


def test_format_bibliography_file_no_meta_warning(tmp_path, monkeypatch, capsys):
    bib_path = tmp_path / "sample.bib"
    bib_path.write_text("""@article{key,
  title={Same},
  doi={10.1000/xyz},
}
""")

    def fake_format(*args, **kwargs):
        bib_path.write_text("""@article{key,
 title={Same},
 doi={10.1000/xyz},
}
""")

    monkeypatch.setattr("bibfixer._internal.formatter.format_bibliography", fake_format)
    format_bibliography_file(bib_path)
    out = capsys.readouterr().out
    assert "altered title" not in out
    assert "changed DOI" not in out

