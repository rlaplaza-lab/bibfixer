"""In-process bibliography formatting helpers."""

from __future__ import annotations

from pathlib import Path

from .. import core


class FormattingError(RuntimeError):
    """Raised when internal formatting fails."""


def format_bibliography(
    bib_file: Path,
    *,
    drop_fields: list[str],
    indent: int = 2,
    align: int = 14,
    dangling: str = "braces",
) -> None:
    """Format *bib_file* in place and remove selected fields."""
    _ = (indent, align, dangling)

    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return

    for entry in bib_database.entries:
        for field in drop_fields:
            entry.pop(field, None)

    core.write_bib_file(bib_file, bib_database)

