"""In-process metadata update helpers."""

from __future__ import annotations

import json
import tempfile
import time
import re
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from .. import core
from .. import utils
from ..fixes import abbreviate_journal_names as _abbreviate_journal_names
from ..validation import get_fields_to_enrich, is_missing_field


class MetadataUpdateError(RuntimeError):
    """Raised when an internal metadata operation fails."""


_CROSSREF_TIMEOUT_SECONDS = 15
_CROSSREF_ATTEMPTS = 3
_MISMATCH_FIELDS = ("title", "author", "year", "journal", "volume", "number", "pages")


def _parse_single_entry_bibtex(raw_bibtex: str) -> dict[str, Any] | None:
    """Parse one-entry BibTeX text and return the entry dict."""
    with tempfile.NamedTemporaryFile("w+", suffix=".bib", delete=False, encoding="utf-8") as tmp:
        tmp.write(raw_bibtex)
        tmp_path = Path(tmp.name)
    try:
        db = core.parse_bibtex_file(tmp_path)
    except Exception:
        return None
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass
    if not db or not db.entries:
        return None
    return db.entries[0]


def _normalized_text(value: Any) -> str | None:
    """Normalize values for mismatch comparisons."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = " ".join(text.split())
    return text.casefold()


def _cosmetic_normalized_text(value: Any) -> str | None:
    """Normalize values while ignoring punctuation-only differences."""
    normalized = _normalized_text(value)
    if not normalized:
        return normalized
    compact = re.sub(r"[^0-9a-z]+", "", normalized)
    return compact or None


def _is_meaningful_mismatch(before: Any, after: Any) -> bool:
    """Return whether a mismatch is larger than punctuation/case churn."""
    normalized_before = _normalized_text(before)
    normalized_after = _normalized_text(after)
    if not normalized_before or not normalized_after:
        return False
    if normalized_before == normalized_after:
        return False
    return _cosmetic_normalized_text(before) != _cosmetic_normalized_text(after)


def _pages_from_crossref_work(work: dict[str, Any]) -> str | None:
    """Extract a BibTeX-style pages value from a Crossref JSON work record."""
    page = work.get("page")
    if page is not None:
        text = str(page).strip()
        if text:
            return text
    article_number = work.get("article-number")
    if article_number is not None:
        text = str(article_number).strip()
        if text:
            return text
    return None


def _fetch_crossref_work(doi: str) -> dict[str, Any] | None:
    """Return the Crossref work record for *doi*, if available."""
    normalized = utils.normalize_doi(doi)
    if not normalized:
        return None
    encoded = urlparse.quote(normalized, safe="/")
    url = f"https://api.crossref.org/works/{encoded}"
    headers = {
        "Accept": "application/json",
        "User-Agent": "bibfixer/1.0 (https://github.com/)",
    }
    for attempt in range(_CROSSREF_ATTEMPTS):
        req = urlrequest.Request(url, headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=_CROSSREF_TIMEOUT_SECONDS) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
            message = payload.get("message")
            if isinstance(message, dict):
                return message
        except urlerror.HTTPError as exc:
            if 400 <= exc.code < 500:
                return None
        except (urlerror.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            pass
        if attempt < _CROSSREF_ATTEMPTS - 1:
            time.sleep(0.5 * (attempt + 1))
    return None


def _journal_from_crossref_work(work: dict[str, Any]) -> str | None:
    container = work.get("container-title")
    if isinstance(container, list) and container:
        text = str(container[0]).strip()
        if text:
            return text
    if isinstance(container, str) and container.strip():
        return container.strip()
    return None


def _volume_from_crossref_work(work: dict[str, Any]) -> str | None:
    volume = work.get("volume")
    if volume is not None:
        text = str(volume).strip()
        if text:
            return text
    return None


def _number_from_crossref_work(work: dict[str, Any]) -> str | None:
    issue = work.get("issue")
    if issue is not None:
        text = str(issue).strip()
        if text:
            return text
    return None


def _needs_supplement(entry: dict[str, Any] | None, field: str, supplemented: dict[str, Any]) -> bool:
    if entry is not None and not is_missing_field(entry.get(field)):
        return False
    return is_missing_field(supplemented.get(field))


def supplement_fetched_metadata(
    doi: str,
    fetched: dict[str, Any],
    *,
    entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fill gaps in Crossref BibTeX metadata using JSON work records."""
    supplemented = fetched.copy()
    work: dict[str, Any] | None = None

    def _crossref_work() -> dict[str, Any] | None:
        nonlocal work
        if work is None:
            work = _fetch_crossref_work(doi)
        return work

    if _needs_supplement(entry, "pages", supplemented):
        if is_missing_field(supplemented.get("pages")) and not is_missing_field(supplemented.get("page")):
            supplemented["pages"] = supplemented.get("page")
        if is_missing_field(supplemented.get("pages")):
            crossref_work = _crossref_work()
            if crossref_work:
                pages = _pages_from_crossref_work(crossref_work)
                if pages:
                    supplemented["pages"] = pages

    if _needs_supplement(entry, "journal", supplemented):
        crossref_work = _crossref_work()
        if crossref_work:
            journal = _journal_from_crossref_work(crossref_work)
            if journal:
                supplemented["journal"] = journal

    if _needs_supplement(entry, "volume", supplemented):
        crossref_work = _crossref_work()
        if crossref_work:
            volume = _volume_from_crossref_work(crossref_work)
            if volume:
                supplemented["volume"] = volume

    if _needs_supplement(entry, "number", supplemented):
        crossref_work = _crossref_work()
        if crossref_work:
            number = _number_from_crossref_work(crossref_work)
            if number:
                supplemented["number"] = number

    return supplemented


def _apply_crossref_metadata(entry: dict[str, Any], fetched: dict[str, Any], doi: str) -> dict[str, Any]:
    """Merge Crossref metadata into *entry*, filling gaps and refreshing core fields."""
    original_key = entry.get("ID", "")
    merged = entry.copy()

    for field in _MISMATCH_FIELDS:
        fetched_value = fetched.get(field)
        if is_missing_field(fetched_value):
            continue
        before = _normalized_text(entry.get(field))
        after = _normalized_text(fetched_value)
        if before and after and before != after:
            key_or_doi = original_key or doi
            if _is_meaningful_mismatch(entry.get(field), fetched_value):
                print(
                    f"  Warning: DOI metadata meaningful mismatch for {key_or_doi} "
                    f"field '{field}': existing differs from Crossref"
                )
            else:
                print(
                    f"  Notice: DOI metadata cosmetic mismatch for {key_or_doi} "
                    f"field '{field}': punctuation/capitalization differs"
                )
        merged[field] = fetched_value

    for field in sorted(get_fields_to_enrich(entry)):
        if field in _MISMATCH_FIELDS:
            continue
        if is_missing_field(merged.get(field)) and not is_missing_field(fetched.get(field)):
            merged[field] = fetched.get(field)

    merged["ID"] = original_key or fetched.get("ID", "")
    if is_missing_field(merged.get("doi")):
        merged["doi"] = doi
    return merged


def update_entries(bib_file: Path) -> None:
    """Refresh DOI-backed entries in place using Crossref BibTeX."""
    db = core.parse_bibtex_file(bib_file)
    if not db:
        return

    changed = 0
    for idx, entry in enumerate(db.entries):
        doi = utils.extract_entry_doi(entry)
        if not doi:
            continue
        fetched_raw = doi_to_bibtex(doi)
        if not fetched_raw:
            continue
        fetched = _parse_single_entry_bibtex(fetched_raw)
        if not fetched:
            continue

        fetched = supplement_fetched_metadata(doi, fetched, entry=entry)
        merged = _apply_crossref_metadata(entry, fetched, doi)
        if merged != entry:
            db.entries[idx] = merged
            changed += 1

    if changed:
        core.write_bib_file(bib_file, db)


def abbreviate_journals(bib_file: Path) -> None:
    """Abbreviate journal names in place."""
    _abbreviate_journal_names(bib_file)


def doi_to_bibtex(doi: str) -> str | None:
    """Return BibTeX fetched from Crossref content negotiation."""
    normalized = utils.normalize_doi(doi)
    if not normalized:
        return None

    encoded = urlparse.quote(normalized, safe="/")
    url = f"https://doi.org/{encoded}"
    headers = {
        "Accept": "application/x-bibtex; charset=utf-8",
        "User-Agent": "bibfixer/1.0 (https://github.com/)",
    }

    for attempt in range(_CROSSREF_ATTEMPTS):
        req = urlrequest.Request(url, headers=headers)
        try:
            with urlrequest.urlopen(req, timeout=_CROSSREF_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8", errors="replace").strip()
            if body:
                return body
        except urlerror.HTTPError as exc:
            # 4xx means DOI missing or unavailable: don't keep retrying.
            if 400 <= exc.code < 500:
                return None
        except (urlerror.URLError, TimeoutError):
            pass

        if attempt < _CROSSREF_ATTEMPTS - 1:
            time.sleep(0.5 * (attempt + 1))

    return None

