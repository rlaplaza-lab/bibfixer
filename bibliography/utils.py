"""Normalization utilities extracted from the original script."""

import unicodedata
import re


def normalize_unicode(text: str | None) -> str | None:
    """Normalize Unicode strings for comparison.

    Returns ``None`` for falsy input to make caller logic simpler.
    """
    if not text:
        return None
    return unicodedata.normalize("NFC", str(text))


def normalize_doi(doi: str | None) -> str | None:
    """Normalize DOI strings to a canonical lowercase form without prefix."""
    if not doi:
        return None
    doi = str(doi).strip().lower()
    if not doi:
        # whitespace-only input should be treated as empty
        return None
    if doi.startswith("doi:"):
        doi = doi[4:]
    if doi.startswith("http://dx.doi.org/"):
        # prefix length is 18 characters, not 19; avoid dropping the leading digit
        doi = doi[18:]
    if doi.startswith("https://doi.org/"):
        doi = doi[16:]
    return doi.strip()


def normalize_url(url: str | None) -> str | None:
    """Basic URL cleaning: strip whitespace and lower-case scheme."""
    if not url:
        return None
    url = str(url).strip()
    # lower-case scheme only (e.g. "HTTP://" -> "http://")
    return re.sub(r"^[A-Za-z]+://", lambda m: m.group(0).lower(), url)


def normalize_keywords(keywords: str | None) -> str | None:
    """Canonicalise a comma-separated keyword list.

    - split on commas
    - strip whitespace
    - lower-case each component
    - rejoin with a single comma
    """
    if not keywords:
        return None
    parts = [k.strip().lower() for k in keywords.split(",") if k.strip()]
    return ",".join(parts) if parts else None


def normalize_entry(entry: dict) -> dict:
    """Return a normalized copy of a BibTeX entry for comparison.

    The returned dictionary omits the ``ID`` field and lowercases keys.
    All values are cast to strings and stripped.
    """
    result: dict[str, str] = {}
    for key, value in entry.items():
        if key.upper() == "ID":
            continue
        result[key.lower()] = str(value).strip()
    return result


def entries_are_identical(entry1: dict, entry2: dict) -> bool:
    """Return ``True`` if two entries are identical apart from their key.

    This is a thin wrapper around :func:`normalize_entry`.
    """
    return normalize_entry(entry1) == normalize_entry(entry2)


def normalize_title(title: str) -> str:
    """Canonicalise a title for loose comparisons.

    Removes braces, collapses whitespace and punctuation, and lowercases the
    result.  This is used by both curation and validation routines.
    """
    title = re.sub(r'[{}]', '', str(title))
    # replace runs of hyphens or dashes with a single space
    title = re.sub(r'[-–—]+', ' ', title)
    # collapse any remaining whitespace
    title = re.sub(r'\s+', ' ', title)
    return title.strip().lower()
