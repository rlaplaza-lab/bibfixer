import io
import os
import re
import sys

from contextlib import redirect_stdout

import iso4

from bibfixer.cli import (
    curate_bibliography,
    main,
    process_bib_file,
    update_with_metadata,
)
from bibfixer.fixes import _heuristic_abbrev


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
    os.chdir(tmp_path)
    return tex


def test_remove_unused_entries(tmp_path, disable_formatting):
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


def test_standardize_keys(tmp_path, disable_formatting):
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
    # formatter may strip spaces or punctuation, accept several variants of the
    # ACS abbreviation.
    assert re.search(r"journal\s*=\s*\{J\. ?Am\. ?Chem\. ?Soc\.?\}", content)
    # tex should use the generated key
    # the generated key is always followed by a comma when formatter
    # re-formats the entry so allow either comma or closing brace
    newkey_match = re.search(r"@article\{([^,}]+)", content)
    assert newkey_match is not None
    newkey = newkey_match.group(1)
    assert re.search(r"cite\{" + re.escape(newkey) + r"\}", tex.read_text())


def test_acs_abbreviation_varied_cases(tmp_path, disable_formatting):
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


def test_standardize_skipped_without_main(tmp_path, disable_formatting):
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


def test_metadata_suspicious_change_restores(tmp_path, monkeypatch, capsys):
    # simulate internal updater mutating file to wrong article (bad URL/title)
    original = """@article{X,
  title={Original Title},
  doi={10.1000/xyz123},
}
"""
    bib = tmp_path / "test.bib"
    bib.write_text(original)

    def fake_update(_bib_file):
        # write bad content to simulate download of wrong entry
        bib.write_text("""@article{X,
  title={Completely different paper},
  doi={10.1000/abc456},
  url={http://evil.com/bad.pdf},
}
""")
    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)

    update_with_metadata(bib)

    captured = capsys.readouterr()
    assert "Suspicious metadata change" in captured.out
    # original file should be restored
    assert bib.read_text() == original

    # now simulate an update error to ensure warning path is emitted
    def fake_update2(_bib_file):
        raise RuntimeError("bad stuff")

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update2)
    bib.write_text(original)
    update_with_metadata(bib)
    captured2 = capsys.readouterr()
    assert "metadata update failed" in captured2.out
    assert "bad stuff" in captured2.out


def test_metadata_update_error_restores_backup(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "test.bib"
    bib.write_text("@article{X, title={T}}\n")

    def fake_update(_bib_file):
        raise RuntimeError("boom")

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)
    update_with_metadata(bib)
    captured = capsys.readouterr()
    assert "metadata update failed: boom" in captured.out
    # original file should remain untouched (backup restored)
    assert bib.read_text().startswith("@article{X")


def test_process_skip_metadata_update(tmp_path, monkeypatch, capsys):
    # using the flag to disable metadata update should avoid update/abbrev
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    # iso4 is a required dependency and may attempt to load NLTK data when
    # abbreviating; ensure the routine is stubbed out so this test doesn't
    # trigger a wordnet lookup.
    monkeypatch.setattr(iso4, "abbreviate", lambda j: j)

    update_called = False
    abbreviate_called = False

    def fake_update(_bib_file):
        nonlocal update_called
        update_called = True

    def fake_abbrev(_bib_file):
        nonlocal abbreviate_called
        abbreviate_called = True

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)
    monkeypatch.setattr("bibfixer._internal.metadata.abbreviate_journals", fake_abbrev)

    process_bib_file(bib, create_backups=False, use_metadata_update=False)
    assert not update_called
    assert not abbreviate_called


def test_cli_skip_metadata_update(tmp_path, monkeypatch, capsys):
    # the command-line option should propagate and skip metadata steps
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    update_called = False

    def fake_update(_bib_file):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)

    orig = sys.argv
    sys.argv = ["bibfixer", "curate", "--yes", "--skip-metadata-update"]
    try:
        main()
    finally:
        sys.argv = orig
    captured = capsys.readouterr()
    assert "Skipping metadata update steps" in captured.out
    assert not update_called


def test_env_var_disables_metadata_update(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Some Journal}}\n")

    update_called = False

    def fake_update(_bib_file):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)

    monkeypatch.setenv("BIBFIXER_SKIP_METADATA", "1")
    orig = sys.argv
    sys.argv = ["bibfixer", "curate", "--yes"]
    try:
        main()
    finally:
        sys.argv = orig
    captured = capsys.readouterr()
    assert "Skipping metadata update steps" in captured.out
    assert not update_called


def test_metadata_skip_malformed_file(tmp_path, capsys):
    # if the bib file cannot be parsed we never invoke metadata update
    bib = tmp_path / "bad.bib"
    # missing equals sign in field will trigger a pybtex TokenRequired error
    bib.write_text("@article{A title={MissingEquals}}\n")

    update_with_metadata(bib)

    captured = capsys.readouterr()
    assert "looks unparsable" in captured.out.lower()
    assert "skipping metadata update" in captured.out.lower()
    # file should be left untouched (no backup removed either)
    assert bib.read_text().startswith("@article")


def test_abbreviate_journal_names_heuristic(tmp_path, disable_formatting, monkeypatch):
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
    tex.write_text(r"\cite{B}")
    monkeypatch.setattr(iso4, "abbreviate", lambda j: "Digit. Disc." if j == "Digital Discovery" else j)
    curate_bibliography([bib], create_backups=False)
    assert "Digit. Disc." in bib.read_text()


def test_abbreviation_command_invoked(tmp_path, monkeypatch):
    # internal abbreviation routine should run and modify the file
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Journal of the American Chemical Society}}\n")

    calls = []

    def fake_abbrev(_bib_file):
        calls.append("abbreviate")
        bib.write_text("@article{A, journal={J. Am. Chem. Soc.}}\n")

    monkeypatch.setattr("bibfixer._internal.metadata.abbreviate_journals", fake_abbrev)
    process_bib_file(bib, create_backups=False)

    assert calls
    # formatter may remove spaces between initials
    assert re.search(r"journal\s*=\s*\{J\. ?Am\. ?Chem\. ?Soc\.?\}", bib.read_text())


def test_heuristic_skip_already_abbreviated(monkeypatch):
    # patch iso4 so we don't trigger the NLTK lookup during tests
    monkeypatch.setattr(iso4, "abbreviate", lambda j: "J. Test." if j == "Journal of Testing" else j)

    # iso4 should be called and its result returned
    assert _heuristic_abbrev("Journal of Testing") == "J. Test."
    # if the journal already contains a period we treat it as done
    assert _heuristic_abbrev("J. Test.") == "J. Test."



def test_abbreviation_even_if_update_crashes(tmp_path, monkeypatch, capsys):
    # update step fails but abbreviation still executes
    bib = tmp_path / "refs.bib"
    bib.write_text("@article{A, journal={Journal of the American Chemical Society}}\n")

    calls = []
    def fake_update(_bib_file):
        raise RuntimeError("simulated crash")

    def fake_abbrev(_bib_file):
        calls.append("abbreviate")
        bib.write_text("@article{A, journal={J. Am. Chem. Soc.}}\n")

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)
    monkeypatch.setattr("bibfixer._internal.metadata.abbreviate_journals", fake_abbrev)
    process_bib_file(bib, create_backups=False)

    captured = capsys.readouterr()
    assert "metadata update failed" in captured.out
    assert calls
    assert "J." in bib.read_text()


def test_update_falls_back_to_doi_to_bibtex_for_stubs(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "references.bib"
    bib.write_text("""@article{StubKey,
  doi={10.1038/nature12373},
}
""")

    def fake_doi_to_bibtex(doi):
        if doi == "10.1038/nature12373":
            return """@article{anyKey,
  title={Nanometre-scale thermometry in a living cell},
  author={Kucsko, G.},
  year={2013},
  doi={10.1038/nature12373},
}
"""
        return None

    monkeypatch.setattr("bibfixer._internal.metadata.doi_to_bibtex", fake_doi_to_bibtex)

    update_with_metadata(bib)

    captured = capsys.readouterr()
    out = bib.read_text()
    assert "Filled 1 DOI stub entry" in captured.out
    assert "Nanometre-scale thermometry in a living cell" in out
    assert "@article{StubKey" in out


def test_update_failure_still_falls_back_to_doi_to_bibtex(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "references.bib"
    bib.write_text("""@article{StubKey,
  doi={10.1038/nature12373},
}
""")

    def fake_update(_bib_file):
        raise RuntimeError("simulated update failure")

    def fake_doi_to_bibtex(doi):
        if doi == "10.1038/nature12373":
            return """@article{anyKey,
  title={Fetched Title},
  author={Doe, Jane},
  year={2024},
  doi={10.1038/nature12373},
}
"""
        return None

    monkeypatch.setattr("bibfixer._internal.metadata.update_entries", fake_update)
    monkeypatch.setattr("bibfixer._internal.metadata.doi_to_bibtex", fake_doi_to_bibtex)

    update_with_metadata(bib)

    captured = capsys.readouterr()
    out = bib.read_text()
    assert "metadata update failed" in captured.out
    assert "Filled 1 DOI stub entry" in captured.out
    assert "Fetched Title" in out
    assert "@article{StubKey" in out


def test_update_enriches_partial_entries_missing_pages(tmp_path, monkeypatch, capsys):
    bib = tmp_path / "local.bib"
    bib.write_text("""@article{HasMetaButNoPages,
  title={Already Here},
  author={Doe, Jane},
  journal={J. Test.},
  year={2024},
  pages={},
  doi={10.1038/nature12373},
}
""")

    def fake_doi_to_bibtex(doi):
        if doi == "10.1038/nature12373":
            return """@article{Fetched,
  title={Fetched Title},
  author={Fetched, Author},
  journal={Fetched Journal},
  year={2024},
  pages={54--58},
  doi={10.1038/nature12373},
}
"""
        return None

    monkeypatch.setattr("bibfixer._internal.metadata.doi_to_bibtex", fake_doi_to_bibtex)

    update_with_metadata(bib)

    captured = capsys.readouterr()
    out = bib.read_text()
    assert "Enriched 1 DOI entry with missing fields" in captured.out
    assert "pages = {54--58}" in out
    # Existing non-missing fields should be preserved.
    assert "title = {Already Here}" in out


def test_backup_and_duplicate_consolidation(tmp_path, disable_formatting):
    tex = setup_simple_project(tmp_path)
    bib = tmp_path / "local.bib"
    bib.write_text("""@article{AlphaKey,
  title={Shared Discovery},
  author={Doe, Jane},
  year={2022},
  doi={10.1000/shared},
}
@article{Beta_Key,
  title={Shared Discovery},
  author={},
  year={},
  doi={10.1000/shared},
}
@article{GammaKey,
  title={Independent Work},
  author={Roe, Richard},
  year={2020},
}
""")
    tex.write_text(r"\cite{AlphaKey,Beta_Key,GammaKey}")

    curate_bibliography([bib], create_backups=True, use_metadata_update=False)

    backup = tmp_path / "local.bib.backup"
    assert backup.exists()
    assert "@article{Beta_Key" in backup.read_text()

    updated = bib.read_text()
    # Duplicate DOI/title entries should consolidate to a single surviving key.
    assert updated.count("10.1000/shared") == 1
    assert "Beta_Key" not in updated
    # TeX citations should be rewritten to the surviving key and deduplicated.
    tex_content = tex.read_text()
    assert "Beta_Key" not in tex_content
    cite_match = re.search(r"\\cite\{([^}]+)\}", tex_content)
    assert cite_match is not None
    cite_keys = [k.strip() for k in cite_match.group(1).split(",")]
    assert len(cite_keys) == len(set(cite_keys))


def test_duplicate_title_consolidation(tmp_path, disable_formatting):
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
