"""Normalization utilities extracted from the original script."""

from __future__ import annotations

import unicodedata
import re
from typing import Any, Mapping, Optional


_DOI_URL_PATTERN = re.compile(
    r"(?:https?://)?(?:dx\.)?doi\.org/([^\s?#}]+)",
    re.IGNORECASE,
)
_ARXIV_ABS_URL_PATTERN = re.compile(
    r"arxiv\.org/abs/([0-9]+\.[0-9]+(?:v\d+)?)",
    re.IGNORECASE,
)


def normalize_unicode(text: Optional[str]) -> Optional[str]:
    """Normalize Unicode strings for comparison.

    Returns ``None`` for falsy input to make caller logic simpler.
    """
    if not text:
        return None
    return unicodedata.normalize("NFC", str(text))


def normalize_citation_key(key: Optional[str]) -> Optional[str]:
    """Normalize citation keys for case-insensitive matching."""
    normalized = normalize_unicode(key)
    if not normalized:
        return None
    compact = normalized.strip()
    if not compact:
        return None
    return compact.casefold()


def normalize_doi(doi: Optional[str]) -> Optional[str]:
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


def extract_entry_doi(entry: Mapping[str, Any]) -> Optional[str]:
    """Return a normalized DOI from entry fields or resolvable identifier URLs."""
    for key in ("doi", "DOI", "Doi"):
        normalized = normalize_doi(entry.get(key))
        if normalized:
            return normalized
    for key in ("url", "URL", "Url"):
        url = entry.get(key)
        if not url:
            continue
        text = str(url).strip()
        match = _DOI_URL_PATTERN.search(text)
        if match:
            normalized = normalize_doi(match.group(1))
            if normalized:
                return normalized
        arxiv_match = _ARXIV_ABS_URL_PATTERN.search(text)
        if arxiv_match:
            normalized = normalize_doi(f"10.48550/arxiv.{arxiv_match.group(1)}")
            if normalized:
                return normalized
    archiveprefix = str(entry.get("archiveprefix") or entry.get("ArchivePrefix") or "").strip().lower()
    eprint = str(entry.get("eprint") or entry.get("Eprint") or "").strip()
    if archiveprefix == "arxiv" and eprint:
        normalized = normalize_doi(f"10.48550/arxiv.{eprint.lower()}")
        if normalized:
            return normalized
    return None


def normalize_url(url: Optional[str]) -> Optional[str]:
    """Basic URL cleaning: strip whitespace and lower-case scheme."""
    if not url:
        return None
    url = str(url).strip()
    # lower-case scheme only (e.g. "HTTP://" -> "http://")
    return re.sub(r"^[A-Za-z]+://", lambda m: m.group(0).lower(), url)


def normalize_keywords(keywords: Optional[str]) -> Optional[str]:
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




def transliterate_for_key(text: str) -> str:
    """Strip combining marks so accented characters become plain ASCII letters.

    Used when building citation keys from author names and titles so that
    e.g. ``Álvarez`` becomes ``Alvarez`` rather than ``lvarez``.
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFD", str(text))
    without_marks = "".join(
        char for char in normalized
        if unicodedata.category(char) != "Mn"
    )
    return unicodedata.normalize("NFC", without_marks)


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
