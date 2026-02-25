import io
import re

from contextlib import redirect_stdout

from bibfixer.cli import curate_bibliography


def setup_simple_project(tmp_path, create_main: bool = True):
    """Create a minimal project directory and ``chdir`` into it.

    If *create_main* is ``False`` the ``main.tex`` file is not written, which
    allows tests to verify behaviour when the conventional file is missing.
    The function returns the path to ``main.tex`` (which may not exist).
    """
    tex = tmp_path / "main.tex"
    if create_main:
        tex.write_text("")
    # change working directory so helpers find files
    import os
    os.chdir(tmp_path)
    return tex


def test_remove_unused_entries(tmp_path, disable_bibfmt):
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
    tex.write_text(r"This is a citation \cite{A}")

    curate_bibliography([bib], create_backups=False)
    content = bib.read_text()
    assert "Unused" not in content
    assert "Used" in content


def test_standardize_keys(tmp_path, disable_bibfmt):
    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "refs.bib"
    bib.write_text("""@article{oldkey,
  author={Smith, John and Doe, Jane},
  year={2021},
  journal={Journal of the American Chemical Society},
  title={An Example Study},
}
""")
    tex.write_text(r"Citation here \cite{oldkey}.")

    curate_bibliography([bib], create_backups=False)
    content = bib.read_text()
    # expected pattern should start with Smith2021 and include journal initials
    assert re.search(r"Smith2021\w+An", content)
    # journal field should now be abbreviated thanks to the mapping;
    # bibfmt may strip spaces or punctuation, accept several variants of the
    # ACS abbreviation.
    assert re.search(r"journal\s*=\s*\{J\. ?Am\. ?Chem\. ?Soc\.?\}", content)
    # tex should use the generated key
    # the generated key is always followed by a comma when bibfmt
    # re-formats the entry so allow either comma or closing brace
    newkey_match = re.search(r"@article\{([^,}]+)", content)
    assert newkey_match is not None
    newkey = newkey_match.group(1)
    assert re.search(r"cite\{" + re.escape(newkey) + r"\}", tex.read_text())


def test_acs_abbreviation_varied_cases(tmp_path, disable_bibfmt):
    # ensure small differences in capitalization are handled by lookup
    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "refs.bib"
    for variant in [
        "journal of the american chemical society",
        "Journal Of The American Chemical Society",
    ]:
        bib.write_text("@article{K,\n  journal={" + variant + "},\n}\n")
        tex.write_text(r"\cite{K}")
        curate_bibliography([bib], create_backups=False)
        assert re.search(r"journal\s*=\s*\{J\. ?Am\. ?Chem\. ?Soc\.?\}", bib.read_text())


def test_standardize_skipped_without_main(tmp_path, disable_bibfmt):
    # no main.tex created by setup
    bib = tmp_path / "refs.bib"
    bib.write_text("""@article{oldkey,
  author={Smith, John},
  year={2020},
  title={Title},
}
""")
    # create some other tex file to mimic a project
    other = tmp_path / "chapter.tex"
    other.write_text(r"Citation \cite{oldkey}")
    import os
    os.chdir(tmp_path)

    # using imports moved to top

    buf = io.StringIO()
    with redirect_stdout(buf):
        curate_bibliography([bib], create_backups=False)
    output = buf.getvalue()
    # confirm log indicates skip
    assert "Skipping citation key standardization" in output
    # since entry may be removed as unused, ensure no new standardized key appears
    assert "Smith2020" not in bib.read_text()


def test_betterbib_suspicious_change_restores(tmp_path, monkeypatch, capsys):
    # simulate betterbib updating file to wrong article (bad URL/title)
    original = """@article{X,
  title={Original Title},
  doi={10.1000/xyz123},
}
"""
    bib = tmp_path / "test.bib"
    bib.write_text(original)

    # betterbib is a required dependency; we don't need to fake its
    # presence.  tests below will stub the subprocess call itself.

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
    from bibfixer.cli import update_with_betterbib
    update_with_betterbib(bib)

    captured = capsys.readouterr()
    assert "Suspicious metadata change" in captured.out
    # original file should be restored
    assert bib.read_text() == original

    # now simulate a non-zero returncode with empty stderr to ensure message
    def fake_run2(cmd, capture_output, text, timeout):
        class R:
            returncode = 1
            stderr = ""
            stdout = "bad stuff"
        return R()

    monkeypatch.setattr("subprocess.run", fake_run2)
    bib.write_text(original)
    update_with_betterbib(bib)
    captured2 = capsys.readouterr()
    assert "betterbib update had issues" in captured2.out
    assert "bad stuff" in captured2.out


def test_betterbib_negative_return_signal(tmp_path, monkeypatch, capsys):
    # simulate a crash (signal) from the betterbib subprocess
    bib = tmp_path / "test.bib"
    bib.write_text("@article{X, title={T}}\n")

    # the package should already be importable; nothing to patch here.

    def fake_run(cmd, capture_output, text, timeout):
        class R:
            returncode = -11
            stderr = ""
            stdout = ""
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    from bibfixer.cli import update_with_betterbib
    update_with_betterbib(bib)
    captured = capsys.readouterr()
    assert "crashed with signal 11" in captured.out
    assert "betterbib update had issues" in captured.out
    # original file should remain untouched (backup restored)
    assert bib.read_text().startswith("@article{X")


def test_process_skip_betterbib(tmp_path, monkeypatch, capsys):
    # using the flag to disable betterbib should avoid subprocess calls
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    # iso4 is a required dependency and may attempt to load NLTK data when
    # abbreviating; ensure the routine is stubbed out so this test doesn't
    # trigger a wordnet lookup.
    try:
        import iso4
    except ImportError:  # shouldn't happen in a correctly configured env
        pass
    else:
        monkeypatch.setattr(iso4, "abbreviate", lambda j: j)

    called = False
    def fake_run(cmd, *args, **kwargs):
        nonlocal called
        # only complain if betterbib is being invoked
        if isinstance(cmd, (list, tuple)) and cmd and "betterbib" in cmd[0]:
            called = True
            raise AssertionError("betterbib should not be executed")
        # fall back to a dummy successful result for other tools
        class R:
            returncode = 0
            stderr = ""
            stdout = ""
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    from bibfixer.cli import process_bib_file
    process_bib_file(bib, create_backups=False, use_betterbib=False)
    assert not called


def test_cli_no_betterbib(tmp_path, monkeypatch, capsys):
    # the command-line option should propagate and skip the external tool
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    calls = []
    class R:
        def __init__(self):
            self.returncode = 0
            self.stderr = ""
            self.stdout = ""
    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd.copy())
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    import sys
    orig = sys.argv
    sys.argv = ["bibfixer", "curate", "--yes", "--no-betterbib"]
    try:
        from bibfixer.cli import main
        main()
    finally:
        sys.argv = orig
    captured = capsys.readouterr()
    assert "Skipping betterbib steps" in captured.out
    # multiple subprocess calls (bibfmt etc.) are expected; make sure none of
    # them invoke the external helper.
    assert all(
        not (isinstance(cmd, (list, tuple)) and cmd and "betterbib" in cmd[0])
        for cmd in calls
    )


def test_env_var_disables_betterbib(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    calls = []
    class R:
        def __init__(self):
            self.returncode = 0
            self.stderr = ""
            self.stdout = ""
    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd.copy())
        return R()
    monkeypatch.setattr("subprocess.run", fake_run)

    monkeypatch.setenv("BIBFIXER_NO_BETTERBIB", "1")
    from bibfixer.cli import main
    import sys
    orig = sys.argv
    sys.argv = ["bibfixer", "curate", "--yes"]
    try:
        main()
    finally:
        sys.argv = orig
    captured = capsys.readouterr()
    assert "Skipping betterbib steps" in captured.out
    assert all(
        not (isinstance(cmd, (list, tuple)) and cmd and "betterbib" in cmd[0])
        for cmd in calls
    )


def test_betterbib_skip_malformed_file(tmp_path, capsys):
    # if the bib file cannot be parsed we never invoke external betterbib
    bib = tmp_path / "bad.bib"
    # missing equals sign in field will trigger a pybtex TokenRequired error
    bib.write_text("@article{A title={MissingEquals}}\n")

    from bibfixer.cli import update_with_betterbib
    update_with_betterbib(bib)

    captured = capsys.readouterr()
    assert "looks unparsable" in captured.out.lower()
    assert "skipping betterbib update" in captured.out.lower()
    # file should be left untouched (no backup removed either)
    assert bib.read_text().startswith("@article")


def test_abbreviate_journal_names_heuristic(tmp_path, disable_bibfmt, monkeypatch):
    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "refs.bib"
    # choose a journal not present in the tiny built-in mapping
    bib.write_text("""@article{A,
  journal={Some Very Long Journal Name},
  title={Test},
}
""")
    tex.write_text(r"\cite{A}")

    # patch iso4.abbreviate so the test is deterministic and doesn't
    # require NLTK data.
    import iso4
    monkeypatch.setattr(iso4, "abbreviate", lambda j: "S. V. L. J. N." if j == "Some Very Long Journal Name" else j)

    curate_bibliography([bib], create_backups=False)
    content = bib.read_text()
    # the patched abbreviation should appear
    assert "S. V. L. J. N." in content
    # the entry itself should still be present (key not important here)
    assert "@article" in content

    # also confirm a more realistic journal name is passed through the
    # helper correctly when iso4 returns something non-trivial.  update the
    # tex file so the new entry is cited and not removed as unused.
    bib.write_text("@article{B, journal={Digital Discovery}, title={Foo}}\n")
    tex.write_text(r"\\cite{B}")
    monkeypatch.setattr(iso4, "abbreviate", lambda j: "Digit. Disc." if j == "Digital Discovery" else j)
    curate_bibliography([bib], create_backups=False)
    assert "Digit. Disc." in bib.read_text()


def test_betterbib_abbreviation_command_invoked(tmp_path, monkeypatch):
    # the new subcommand should be invoked and should modify the file
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Journal of the American Chemical Society}}\n")

    # package available by default in our test environment.

    calls = []
    class R:
        def __init__(self):
            self.returncode = 0
            self.stderr = ""
            self.stdout = ""

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd.copy())
        if 'abbreviate-journal-names' in cmd:
            bib.write_text("@article{A, journal={J. Am. Chem. Soc.}}\n")
        return R()

    monkeypatch.setattr("subprocess.run", fake_run)
    from bibfixer.cli import process_bib_file
    process_bib_file(bib, create_backups=False)

    assert any('abbreviate-journal-names' in c for c in calls)
    # bibfmt may remove spaces between initials
    assert re.search(r"journal\s*=\s*\{J\. ?Am\. ?Chem\. ?Soc\.?\}", bib.read_text())


def test_heuristic_skip_already_abbreviated(monkeypatch):
    from bibfixer.fixes import _heuristic_abbrev
    # patch iso4 so we don't trigger the NLTK lookup during tests
    import iso4
    monkeypatch.setattr(iso4, "abbreviate", lambda j: "J. Test." if j == "Journal of Testing" else j)

    # iso4 should be called and its result returned
    assert _heuristic_abbrev("Journal of Testing") == "J. Test."
    # if the journal already contains a period we treat it as done
    assert _heuristic_abbrev("J. Test.") == "J. Test."



def test_betterbib_abbrev_even_if_update_crashes(tmp_path, monkeypatch, capsys):
    # update step fails but abbreviation still executes
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Journal of the American Chemical Society}}\n")

    # betterbib is always importable; we only need to watch subprocess calls.

    calls = []
    class R:
        def __init__(self, returncode):
            self.returncode = returncode
            self.stderr = ""
            self.stdout = ""

    def fake_run(cmd, capture_output, text, timeout):
        calls.append(cmd.copy())
        if 'update' in cmd:
            return R(-11)
        if 'abbreviate-journal-names' in cmd:
            bib.write_text("@article{A, journal={J. Am. Chem. Soc.}}\n")
            return R(0)
        return R(0)

    monkeypatch.setattr("subprocess.run", fake_run)
    from bibfixer.cli import process_bib_file
    process_bib_file(bib, create_backups=False)

    captured = capsys.readouterr()
    assert "crashed with signal 11" in captured.out
    assert any('abbreviate-journal-names' in c for c in calls)
    assert "J." in bib.read_text()


def test_duplicate_title_consolidation(tmp_path, disable_bibfmt):
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
    tex.write_text(r"Citing both \cite{KeyA,KeyB} here.")

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
