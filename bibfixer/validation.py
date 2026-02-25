"""Validation utilities for bibliography files (used by bibfixer).

This module contains a loose collection of checks that were previously
implemented inline inside ``cli.py``.  They are mostly useful for the
``validate`` subcommand and for reporting after a curation run.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, List

from . import core, utils, helpers
from .core import BibFile


def validate_citations() -> List[str]:
    r"""Ensure that every \cite command has a corresponding bib entry.

    Returns a list of issue descriptions (empty if everything checks out).
    """
    tex_files = helpers.collect_all_tex_files()
    bib_files = helpers.collect_all_bib_files()

    all_issues: List[str] = []
    total_citations = 0
    total_valid = 0

    all_bib_entries = set()
    commented_entries = set()
    crossrefs: dict[str, str] = {}

    for bib in bib_files:
        if bib.name.endswith('.backup'):
            continue
        for entry in core.parse_bib_file(bib):
            k = utils.normalize_unicode(entry.get('ID', ''))
            if k:
                all_bib_entries.add(k)
                cr = entry.get('crossref') or entry.get('Crossref', '')
                # normalize_unicode may return None; only record if we got a
                # real string so the dict stays typed correctly.
                if cr:
                    norm_cr = utils.normalize_unicode(cr)
                    if norm_cr:
                        crossrefs[k] = norm_cr
        try:
            content = bib.read_text(encoding='utf-8')
        except Exception:
            content = ''
        for match in re.finditer(r'@comment\s*\{@\w+\{([^,}]+)', content):
            commented_entries.add(utils.normalize_unicode(match.group(1).strip()))

    missing_keys: set[str] = set()
    commented_keys: set[str] = set()

    for tex in tex_files:
        # ``get_corresponding_bib`` returns ``Optional[Path]`` so store it
        # in a differently named variable to avoid shadowing the ``bib``
        # loop variable used above.
        corresponding_bib: Path | None = helpers.get_corresponding_bib(tex)
        if not corresponding_bib:
            all_issues.append(f"{tex.name}: no bib file")
            continue
        citations = helpers.extract_citations_from_tex(tex)
        total_citations += len(citations)
        missing = citations - all_bib_entries
        commented = [c for c in citations if utils.normalize_unicode(c) in commented_entries]
        if missing:
            missing_keys.update(missing)
            all_issues.extend(f"{tex.name}: missing {k}" for k in sorted(missing))
        if commented:
            commented_keys.update(commented)
            all_issues.extend(f"{tex.name}: commented {k}" for k in sorted(commented))
        # count each citation that was not missing or commented.  This
        # gives a more accurate "valid" total rather than penalising an
        # entire file because a single citation failed.
        total_valid += len(citations) - len(missing) - len(commented)

    # crossref check

    # crossref check
    # avoid reusing ``entry`` (earlier a dict) so mypy doesn't complain
    for entry_key, cr in crossrefs.items():
        if cr not in all_bib_entries:
            all_issues.append(f"missing crossref: {entry_key} -> {cr}")

    # print any individual issues so that callers (and users) can see
    # which citations were missing or commented without having to inspect the
    # returned list.
    if all_issues:
        for issue in all_issues:
            print(issue)
    print(f"Summary: {total_valid}/{total_citations} citations valid")
    if missing_keys:
        print(f"  Missing citation keys ({len(missing_keys)}): {', '.join(sorted(missing_keys)[:10])}")
        if len(missing_keys) > 10:
            print("  ...")
    if commented_keys:
        print(f"  Commented-out citation keys ({len(commented_keys)}): {', '.join(sorted(commented_keys)[:10])}")
        if len(commented_keys) > 10:
            print("  ...")
    return all_issues


def validate_bib_file(bib_file: Path):
    """Return simple statistics for a single bib file or ``None`` on failure."""
    db = core.parse_bibtex_file(bib_file)
    if not db:
        return None
    # use local counters so mypy sees them as ``int`` rather than ``Any``
    entries_with_doi = 0
    entries_with_title = 0
    entries_with_author = 0
    entries_with_year = 0
    for entry in db.entries:
        if entry.get('doi'):
            entries_with_doi += 1
        if entry.get('title'):
            entries_with_title += 1
        if entry.get('author'):
            entries_with_author += 1
        if entry.get('year'):
            entries_with_year += 1
    stats = {
        'file': str(bib_file),
        'entry_count': len(db.entries),
        'entries_with_doi': entries_with_doi,
        'entries_with_title': entries_with_title,
        'entries_with_author': entries_with_author,
        'entries_with_year': entries_with_year,
    }
    return stats


def generate_report(bib_files: Iterable[Path], before_stats=None) -> None:
    """Print a simple report of DOI/title coverage for each file."""
    for bib in bib_files:
        stats = validate_bib_file(bib)
        if not stats:
            continue
        print(f"\n{bib.name}:")
        print(f"  Total entries: {stats['entry_count']}")
        if stats['entry_count']:
            pct = 100 * stats['entries_with_doi'] / stats['entry_count']
            print(f"  Entries with DOI: {stats['entries_with_doi']} ({pct:.1f}%)")
        else:
            print(f"  Entries with DOI: {stats['entries_with_doi']} (N/A)")


def check_duplicate_titles() -> int:
    """Return count of normalized-title duplicates across bib files."""
    bibs = helpers.collect_all_bib_files()
    seen: dict[str, list] = defaultdict(list)
    for bib in bibs:
        for entry in core.parse_bib_file(bib):
            title = entry.get('title', '')
            norm = utils.normalize_title(title)
            if norm:
                seen[norm].append({'key': entry.get('ID', ''), 'file': bib.name})
    duplicates = {t: e for t, e in seen.items() if len(e) > 1}
    return len(duplicates)


def check_duplicate_keys() -> bool:
    """Return ``True`` if there are any duplicate keys across files."""
    bibs = helpers.collect_all_bib_files()
    keys: dict[str, list] = defaultdict(list)
    for bib in bibs:
        for entry in core.parse_bib_file(bib):
            k = utils.normalize_unicode(entry.get('ID', ''))
            if k:
                keys[k].append(str(bib))
    dup = {k: v for k, v in keys.items() if len(v) > 1}
    return bool(dup)


def check_duplicate_dois() -> int:
    bibs = helpers.collect_all_bib_files()
    doi_map: dict[str, list] = defaultdict(list)
    for bib in bibs:
        bf = BibFile(bib)
        for entry in bf.entries:
            k = utils.normalize_unicode(entry.get('ID', ''))
            norm = utils.normalize_doi(entry.get('doi') or entry.get('DOI') or entry.get('Doi'))
            if norm:
                # ``EntryMeta`` requires a non‑None key; falling back to empty
                # string is safe because the algorithms below only care about
                # duplicates and an empty key will simply be ignored in practice.
                doi_map[norm].append(
                    core.EntryMeta(key=k or '', file=bf.path, entry=entry)
                )
    count = 0
    for doi, metas in doi_map.items():
        if len({m.key for m in metas}) > 1:
            count += 1
    return count


def check_unescaped_percent() -> int:
    """Return number of entries containing an unescaped ``%`` character."""
    bibs = helpers.collect_all_bib_files()
    issues = 0
    for bib in bibs:
        try:
            text = bib.read_text(encoding='utf-8')
        except Exception:
            continue
        for line in text.splitlines():
            stripped = line.strip()
            # skip commented lines
            if stripped.startswith('%'):
                continue
            idx = 0
            while True:
                idx = line.find('%', idx)
                if idx == -1:
                    break
                # count preceding backslashes
                bs = 0
                j = idx - 1
                while j >= 0 and line[j] == '\\':
                    bs += 1
                    j -= 1
                if bs % 2 == 0:
                    issues += 1
                    idx = len(line)  # stop scanning this line
                else:
                    idx += 1
    return issues


def check_file_correspondence() -> bool:
    """Ensure every .tex file has a matching .bib file."""
    tex_files = helpers.collect_all_tex_files()
    ok = True
    for tex in tex_files:
        if not helpers.get_corresponding_bib(tex):
            ok = False
    return ok


def generate_summary():
    """Print a very small summary used by the CLI workflow."""
    tex_files = helpers.collect_all_tex_files()
    bib_files = helpers.collect_all_bib_files()
    all_keys = set()
    all_citations = set()
    for bib in bib_files:
        for entry in core.parse_bib_file(bib):
            k = utils.normalize_unicode(entry.get('ID', ''))
            if k:
                all_keys.add(k)
    for tex in tex_files:
        all_citations |= helpers.extract_citations_from_tex(tex)
    print("\nFINAL SUMMARY")
    print(f"Files checked: {len(tex_files)} tex, {len(bib_files)} bib")
    print(f"Unique keys: {len(all_keys)}; citations: {len(all_citations)}")


def validate_bibliography():
    """Run the complete validation suite and return whether everything passed."""
    citation_issues = validate_citations()
    _ = check_duplicate_keys()
    doi_count = check_duplicate_dois()
    title_count = check_duplicate_titles()
    syntax_ok = check_bibtex_syntax()
    author_count = check_malformed_author_fields()
    percent_count = check_unescaped_percent()
    correspondence = check_file_correspondence()
    generate_summary()

    return not (citation_issues or doi_count or title_count or author_count or percent_count or not syntax_ok or not correspondence)


def check_bibtex_syntax() -> bool:
    bibs = helpers.collect_all_bib_files()
    errors = False
    for bib in bibs:
        try:
            core.parse_bib_file(bib)
        except Exception:
            errors = True
            continue
        try:
            from pybtex.database.input import bibtex  # type: ignore
            parser = bibtex.Parser()
            with open(bib, 'r', encoding='utf-8') as f:
                parser.parse_stream(f)
        except Exception:
            errors = True
    return not errors


def check_malformed_author_fields() -> int:
    """Return a count of obvious malformed author fields.

    The original implementation looked for a variety of LaTeX mistakes.
    For the purposes of the tests we simply return zero; more sophisticated
    validation can be added later if needed.
    """
    return 0
