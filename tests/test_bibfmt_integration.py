from bibfixer.cli import format_with_bibfmt


def test_format_with_bibfmt_removes_fields(tmp_path):
    # create a bib file containing a field that should be dropped
    bib_path = tmp_path / "sample.bib"
    bib_path.write_text("""@article{key,
  title={Test},
  file={/some/path},
}
""")
    # ensure field present initially
    assert "file={/some/path}" in bib_path.read_text()

    format_with_bibfmt(bib_path)

    content = bib_path.read_text()
    # bibfmt should remove the 'file' field and keep title
    assert "file=" not in content
    assert "title" in content and "Test" in content


def test_curate_uses_bibfmt(tmp_path, monkeypatch):
    # ensure bibfmt is invoked during curation by patching subprocess.run
    calls = []

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd)
        class Result:
            returncode = 0
            stderr = ""
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)

    bib_file = tmp_path / "foo.bib"
    bib_file.write_text("""@article{key,
  title={Example},
}
""")

    # import the function that processes a single file
    from bibfixer.cli import process_bib_file

    process_bib_file(bib_file, create_backups=False)
    # one of the calls should include 'bibfmt'
    assert any('bibfmt' in c[0] for c in calls)


def test_format_with_bibfmt_warns_on_meta_change(tmp_path, monkeypatch, capsys):
    # create file and simulate bibfmt modifying metadata
    bib_path = tmp_path / "sample.bib"
    bib_path.write_text("""@article{key,
  title={Old Title},
  doi={10.1000/old},
}
""")

    # monkeypatch subprocess.run to actually rewrite file with changed entry
    def fake_run(cmd, capture_output, text, timeout):
        bib_path.write_text("""@article{key,
  title={New Title Completely Different},
  doi={10.1000/new},
}
""")
        class Result:
            returncode = 0
            stderr = ""
        return Result()

    monkeypatch.setattr("subprocess.run", fake_run)
    format_with_bibfmt(bib_path)
    out = capsys.readouterr().out
    assert "Warning: bibfmt appears to have altered title" in out
    assert "Warning: bibfmt changed DOI" in out
