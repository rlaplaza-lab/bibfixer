import sys
import pathlib
import re

# ensure workspace root is on path so that the bibliography package can be imported
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from bibliography.cli import curate_bibliography


def setup_simple_project(tmp_path):
    """Helper to create a minimal project and chdir into it."""
    # create empty tex file if not already
    tex = tmp_path / "main.tex"
    tex.write_text("")
    # change working directory so helpers find files
    import os
    os.chdir(tmp_path)
    return tex


def test_remove_unused_entries(tmp_path, monkeypatch):
    # patch bibfmt invocation since it's run during curation
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stderr": ""})())

    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "refs.bib"
    bib.write_text("""@article{A,
  title={Used},
}

@article{B,
  title={Unused},
}
""")
    # cite only A in tex
    tex.write_text("This is a citation \cite{A}")

    curate_bibliography([bib], create_backups=False)
    content = bib.read_text()
    assert "Unused" not in content
    assert "Used" in content


def test_standardize_keys(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stderr": ""})())

    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "refs.bib"
    bib.write_text("""@article{oldkey,
  author={Smith, John and Doe, Jane},
  year={2021},
  journal={Journal of Testing},
  title={An Example Study},
}
""")
    tex.write_text("Citation here \cite{oldkey}.")

    curate_bibliography([bib], create_backups=False)
    content = bib.read_text()
    # expected pattern should start with Smith2021 and include journal initials
    assert re.search(r"Smith2021\w+An", content)
    # tex should use the generated key
    newkey_match = re.search(r"@article\{([^,]+)", content)
    assert newkey_match is not None
    newkey = newkey_match.group(1)
    assert re.search(r"cite\{" + re.escape(newkey) + r"\}", tex.read_text())


def test_betterbib_suspicious_change_restores(tmp_path, monkeypatch, capsys):
    # simulate betterbib updating file to wrong article (bad URL/title)
    original = """@article{X,
  title={Original Title},
  doi={10.1000/xyz123},
}
"""
    bib = tmp_path / "test.bib"
    bib.write_text(original)

    # fake subprocess.run to rewrite bib file with bad data
    def fake_run(cmd, capture_output, text, timeout):
        # write bad content to simulate download of wrong entry
        bib.write_text("""@article{X,
  title={Completely different paper},
  doi={10.1000/abc456},
  url={http://evil.com/bad.pdf},
}
""")
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)

    # call update_with_betterbib and capture warnings
    from bibliography.cli import update_with_betterbib
    update_with_betterbib(bib)

    captured = capsys.readouterr()
    assert "Suspicious metadata change" in captured.out
    # original file should be restored
    assert bib.read_text() == original


def test_duplicate_title_consolidation(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stderr": ""})())

    tex = setup_simple_project(tmp_path)
    bib1 = tmp_path / "one.bib"
    bib2 = tmp_path / "two.bib"
    bib1.write_text("""@article{KeyA,
  title={Same title},
  author={Author},
  year={2020},
}
""")
    bib2.write_text("""@article{KeyB,
  title={Same title},
}
""")
    # cite both keys
    tex.write_text("Citing both \cite{KeyA,KeyB} here.")

    curate_bibliography([bib1, bib2], create_backups=False)

    # after curation there should be a single entry for the title
    out1 = bib1.read_text()
    out2 = bib2.read_text()
    combined = out1 + out2
    # exactly one entry remains across both files
    keys = re.findall(r"@\w+\{([^,]+)", combined)
    assert len(keys) == 1
    newkey = keys[0]
    # ensure the original raw keys are no longer present
    assert "KeyA" not in combined and "KeyB" not in combined
    # tex file should mention only the consolidated key exactly once
    newtex = tex.read_text()
    assert newkey in newtex
    assert newtex.count(newkey) == 1
