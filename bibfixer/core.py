"""Core data structures and helpers for the bibfixer script.

This module contains the :class:`BibFile` abstraction around a path and a
parsed BibTeX database, utilities for walking and transforming the fields of
entries, and a few constants used across the project.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

# bibtexparser (1.x) relies on pyparsing, which has undergone an API change in
# version 3.0; names such as ``DelimitedList`` and ``add_parse_action`` were
# renamed.  Rather than pinning to an old pyparsing release we apply a small
# compatibility shim so that the library can work with both old and new
# versions of pyparsing without modification.  This avoids forcing users to
# downgrade pyparsing and conflict with other packages in their environment.
try:
    import pyparsing as _pp  # type: ignore[import]
    if not hasattr(_pp, "DelimitedList") and hasattr(_pp, "delimitedList"):
        # mypy doesn't know about the dynamic attribute; it's safe at runtime
        _pp.DelimitedList = _pp.delimitedList  # type: ignore[attr-defined,misc]

    # ``add_parse_action`` was renamed to ``addParseAction``; ensure both exist
    for _cls in (_pp.ParserElement, getattr(_pp, "Word", None), getattr(_pp, "Regex", None), getattr(_pp, "WordRegex", None)):
        if _cls is not None and hasattr(_cls, "addParseAction") and not hasattr(_cls, "add_parse_action"):
            # the stub for ParserElement doesn't define these attributes, so
            # ignore type checking here as well
            _cls.add_parse_action = _cls.addParseAction  # type: ignore[attr-defined,assignment]
except ImportError:
    pass

import bibtexparser  # type: ignore[import]
from bibtexparser.bparser import BibTexParser  # type: ignore[import]
from bibtexparser.bwriter import BibTexWriter  # type: ignore[import]
from bibtexparser.customization import convert_to_unicode  # type: ignore[import]

# constant list that was previously defined in the monolithic script
FIELDS_TO_REMOVE = [
    "file",
    "urldate",
    "langid",
    "keywords",
    "abstract",
    "Bdsk-Url-1",
    "Bdsk-Url-2",
    "note",
    "annote",
    "comment",
    "timestamp",
    "date-added",
    "date-modified",
]


@dataclass
class EntryMeta:
    """Metadata for a single BibTeX entry.

    ``key`` is the citation key, ``file`` is the :class:`pathlib.Path` of the
    originating .bib file, and ``entry`` is the raw dictionary produced by
    ``bibtexparser``.
    """

    key: str
    file: Path
    entry: dict[str, Any]


class BibFile:
    """Lightweight wrapper around a BibTeX file and its parsed database.

    Instances behave like a container of entries and provide convenience
    methods for reading from and writing back to disk.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.database = None  # type: bibtexparser.bibdatabase.BibDatabase | None
        self.read()

    def read(self) -> None:
        parser = BibTexParser()
        parser.customization = convert_to_unicode
        parser.ignore_nonstandard_types = False
        parser.homogenise_fields = False

        try:
            with self.path.open("r", encoding="utf-8") as f:
                self.database = bibtexparser.load(f, parser=parser)
        except Exception as exc:
            raise RuntimeError(f"Error parsing {self.path}: {exc}")

    def write(self) -> None:
        if self.database is None:
            raise RuntimeError("database not loaded")
        writer = BibTexWriter()
        writer.indent = "  "
        writer.display_order = (
            "title",
            "author",
            "journal",
            "year",
            "volume",
            "number",
            "pages",
            "doi",
            "url",
            "publisher",
        )
        try:
            with self.path.open("w", encoding="utf-8") as f:
                bibtexparser.dump(self.database, f, writer=writer)
        except Exception as exc:
            raise RuntimeError(f"Error writing {self.path}: {exc}")

    @property
    def entries(self) -> list[dict[str, Any]]:
        return self.database.entries if self.database else []


# helpers for field-level iteration and transformation


def walk_fields(bibfile: BibFile) -> Iterator[tuple[dict[str, Any], str, Any]]:
    """Yield ``(entry, field, value)`` for every field in every entry.

    The iteration uses ``list(entry.items())`` to allow callers to modify the
    ``entry`` while iterating.
    """
    for entry in bibfile.entries:
        for field, value in list(entry.items()):
            yield entry, field, value


FieldTransform = Callable[[Any], Any]


def field_transform(func: FieldTransform) -> Callable[[BibFile], int]:
    """Decorator that applies ``func`` to every value in a :class:`BibFile`.

    ``func`` should accept a single argument (the current field value) and
    return a replacement value.  If the return value is ``None`` or is equal to
    the original value, no modification is made.  The decorated function will
    receive a :class:`BibFile` and return the number of fields that were
    changed.
    """

    def wrapper(bibfile: BibFile) -> int:
        changed = 0
        for entry, field, value in walk_fields(bibfile):
            new_value = func(value)
            if new_value is not None and new_value != value:
                entry[field] = new_value
                changed += 1
        return changed

    return wrapper




# convenience re‑exports, mirroring legacy behaviour

def parse_bib_file(path: Path | str) -> list[dict[str, Any]]:
    """Parse a file and return :data:`entries` (legacy compatibility)."""
    bf = BibFile(path)
    return bf.entries


def parse_bibtex_file(path: Path | str) -> bibtexparser.bibdatabase.BibDatabase:
    """Parse a file and return the full :class:`BibDatabase` object."""
    bf = BibFile(path)
    return bf.database


def write_bib_file(path: Path | str, bib_database: bibtexparser.bibdatabase.BibDatabase) -> None:
    """Write a :class:`BibDatabase` back to disk.  Used by the legacy script."""
    bf = BibFile(path)
    bf.database = bib_database
    bf.write()
