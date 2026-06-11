"""Tests for LaTeX/Overleaf safety fixes."""

import re

from bibfixer import cli
from bibfixer import helpers
from bibfixer.fixes import (
    fix_latex_unsafe_characters,
    fix_legacy_month_fields_text,
    fix_malformed_author_fields,
    fix_problematic_unicode,
    preprocess_bib_for_parsing,
)
from bibfixer import core


def test_fix_legacy_month_fields_text_unquoted(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        """@article{A,
  title={Example},
  year={2022},
  month=July,
}
"""
    )
    fixed = fix_legacy_month_fields_text(bib)
    assert fixed == 1
    text = bib.read_text()
    assert "month = {7}" in text
    db = core.parse_bibtex_file(bib)
    assert len(db.entries) == 1


def test_fix_malformed_author_unified_accent_syntax(tmp_path):
    bib = tmp_path / "accents.bib"
    bib.write_text("""@article{A,
  author={José and Müller, Hans},
}
""")
    fix_malformed_author_fields(bib)
    text = bib.read_text()
    assert r"{\'e}" in text
    assert r'{\"u}' in text


def test_fix_problematic_unicode_braced_accents(tmp_path):
    bib = tmp_path / "combining.bib"
    bib.write_text("""@article{U,
  title={ca\u0301f},
}
""")
    fix_problematic_unicode(bib)
    assert r"{\'a}" in bib.read_text()


def test_fix_latex_unsafe_nested_brace_ampersand(tmp_path):
    """Line-level & escaping handles nested braces within a single field line."""
    bib = tmp_path / "nested.bib"
    bib.write_text("""@article{A,
  title={Low-{T} studies & more},
}
""")
    fix_latex_unsafe_characters(bib)
    text = bib.read_text()
    assert "Low-{T}" in text
    assert r"\&" in text


def test_fix_latex_unsafe_characters(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        """@article{A,
  title={experiments & calculations — the “twin”},
  author={Andr\\es and Al\\an},
}
"""
    )
    fixed = fix_latex_unsafe_characters(bib)
    assert fixed > 0
    text = bib.read_text()
    assert r"\&" in text
    assert "—" not in text
    assert "\u201c" not in text
    assert r"Andr{\'e}s" in text
    assert r"Al{\'a}n" in text


def test_preprocess_enables_parsing(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        """@article{A,
  title={Test},
  month=May,
}
@article{B,
  title={Other & more},
  author={Jos\\e Smith},
}
"""
    )
    preprocess_bib_for_parsing(bib)
    db = core.parse_bibtex_file(bib)
    assert len(db.entries) == 2


def test_reconcile_bib_keys_with_tex_citations(tmp_path):
  import os

  os.chdir(tmp_path)
  bib = tmp_path / "references.bib"
  tex = tmp_path / "main.tex"
  bib.write_text(
      """@article{lvarezMoreno2014,
  title={ioChem},
}
"""
  )
  tex.write_text(r"\cite{lvarezmoreno2014}")

  mapping = helpers.reconcile_bib_keys_with_tex_citations([bib], [tex])
  assert mapping == {"lvarezMoreno2014": "lvarezmoreno2014"}
  assert "lvarezmoreno2014" in bib.read_text()


def test_remove_duplicate_keys_within_files(tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(
        """@article{Same,
  title={Short},
}
@article{Same,
  title={Longer title},
  author={Someone},
}
"""
    )
    removed = cli.remove_duplicate_keys_within_files([bib])
    assert removed == 1
    text = bib.read_text()
    assert text.count("@article{Same") == 1
    assert "Someone" in text


def test_compose_key_mappings_chains_transitive_renames():
    sanitize = {"https://doi.org/10.48550/arxiv.2505.08762": "https:doiorg1048550arxiv250508762"}
    standardize = {"https:doiorg1048550arxiv250508762": "Levine2025The"}
    composed = helpers.compose_key_mappings(sanitize, standardize)
    assert composed["https://doi.org/10.48550/arxiv.2505.08762"] == "Levine2025The"


def test_remove_unused_keeps_case_insensitive_match(tmp_path):
    import os

    os.chdir(tmp_path)
    bib = tmp_path / "refs.bib"
    tex = tmp_path / "main.tex"
    bib.write_text(
        """@article{MixedCase,
  title={Keep me},
}
@article{unused,
  title={Drop me},
}
"""
    )
    tex.write_text(r"\cite{mixedcase}")
    helpers.reconcile_bib_keys_with_tex_citations([bib], [tex])
    cli.remove_unused_entries([bib])
    text = bib.read_text()
    assert "Keep me" in text
    assert "Drop me" not in text
    assert re.search(r"@article\{mixedcase", text)
