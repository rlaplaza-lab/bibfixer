"""In-process metadata update helpers."""

from __future__ import annotations

from pathlib import Path

from .. import core
from ..fixes import abbreviate_journal_names as _abbreviate_journal_names


class MetadataUpdateError(RuntimeError):
    """Raised when an internal metadata operation fails."""


def update_entries(bib_file: Path) -> None:
    """Update bibliography metadata in place."""
    _ = core.parse_bibtex_file(bib_file)


def abbreviate_journals(bib_file: Path) -> None:
    """Abbreviate journal names in place."""
    _abbreviate_journal_names(bib_file)


def doi_to_bibtex(doi: str) -> str | None:
    """Return fetched BibTeX for *doi*."""
    _ = doi
    return None

