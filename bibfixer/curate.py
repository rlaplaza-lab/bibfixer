"""Curation routines extracted from the legacy CLI.

Most of the heavy lifting that used to live in ``cli.py`` has been moved
here so that the command‑line driver can stay lean.  All functions are
fully exercised by tests and re-exported from :mod:`bibfixer.cli` for
backwards compatibility.

The public API is intentionally minimal; callers usually invoke
:func:`curate_bibliography` and let it orchestrate the rest.
"""

from __future__ import annotations

import subprocess
import shutil
import re
import sys
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Any

from . import core, utils, helpers
from .core import FIELDS_TO_REMOVE

# import frequently used fix routines at module level for simplicity
from .fixes import (
    fix_invalid_utf8_bytes,
    fix_html_entities,
    fix_malformed_author_fields,
    remove_accents_from_names,
    fix_problematic_unicode,
    fix_unescaped_percent,
    fix_legacy_year_fields,
    fix_legacy_month_fields,
    uncomment_bibtex_entries,
)


# ---------------------------------------------------------------------------
# simple helpers
# ---------------------------------------------------------------------------

def create_backup(bib_file: Path) -> Path:
    """Copy *bib_file* to ``.bib.backup`` and return the new path."""
    backup_path = bib_file.with_suffix('.bib.backup')
    shutil.copy2(bib_file, backup_path)
    print(f"  Created backup: {backup_path}")
    return backup_path


# ---------------------------------------------------------------------------
# external tool wrappers
# ---------------------------------------------------------------------------

def update_with_betterbib(bib_file: Path) -> None:
    """Run ``betterbib`` on *bib_file* with a simple safety wrapper.

    A backup is created unconditionally; if the external command fails or
    seems to have produced wildly different metadata we restore from the
    backup so that the calling code can continue with a known-good file.
    """
    print("  Updating entries with betterbib...")

    # ensure the file actually contains valid entries before invoking
    # betterbib.  ``pybtex``/``bibtexparser`` used to raise an exception for a
    # malformed file, but with recent dependency upgrades it will silently
    # return an empty database instead.  We check the raw text for an entry
    # marker and then make sure the parsed result isn’t empty; if it is we
    # assume the file is hopeless and skip the helper.
    text = bib_file.read_text(encoding="utf-8", errors="ignore")
    parsed = core.parse_bibtex_file(bib_file)
    if "@" in text and (not parsed or not getattr(parsed, "entries", [])):
        print("  Warning: input file looks unparsable, skipping betterbib update")
        return

    backup_path = bib_file.with_suffix('.bib.betterbib_backup')
    shutil.copy2(bib_file, backup_path)

    # capture prior DOI state so we can spot obvious corruption later
    before_db = core.parse_bibtex_file(bib_file)
    dois_before = {}
    if before_db:
        for e in before_db.entries:
            key = e.get('ID', '')
            if key:
                doi = e.get('doi') or e.get('DOI')
                if doi:
                    dois_before[key] = utils.normalize_doi(doi)

    # prefer running the package via ``python -m betterbib`` so that the
    # interpreter’s import path is used rather than whatever script might be
    # found on ``PATH``.  This reduces the chance that a stray executable from
    # a source checkout is invoked when the working directory changes.
    # ``betterbib`` is now a required dependency; attempting to import it
    # should always succeed in a properly installed environment.  We still
    # catch ``ImportError`` in case someone is running from a bare checkout or
    # has a broken install, but there is no longer a meaningful "optional"
    # path.
    try:
        import betterbib  # type: ignore[import]
    except ImportError:  # pragma: no cover - this should not happen in CI
        print("  Warning: betterbib not installed, skipping update")
        return

    # attempt to invoke the CLI via a module; older/broken installs may not
    # provide a ``__main__`` which would make ``-m betterbib`` fail.  falling
    # back to the explicit submodule is safe and works with both.
    # execute the internal main module directly; cli package lacks a
    # __main__ so ``-m betterbib.cli`` fails in some installations.
    cmd = [sys.executable, '-m', 'betterbib.cli._main', 'update', '-i', str(bib_file)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        print("  Warning: betterbib update timed out")
        shutil.copy2(backup_path, bib_file)
        return
    except Exception as exc:  # pragma: no cover - very rare
        print(f"  Warning: betterbib update failed: {exc}")
        shutil.copy2(backup_path, bib_file)
        return

    if result.returncode != 0:
        # prefer stderr, but fall back to stdout or return code if nothing
        # was emitted.  A negative return code means the process was killed
        # by a signal (segfaults in particular show up as -11).  Include a
        # more descriptive message in that case so the user can tell what
        # went wrong.
        if result.returncode < 0:
            sig = -result.returncode
            msg = f"crashed with signal {sig}"
        else:
            msg = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        print(f"  Warning: betterbib update had issues: {msg}")
        shutil.copy2(backup_path, bib_file)
        return

    print("  betterbib update completed")

    # basic sanity check – if DOI changed entirely, bail out
    after_db = core.parse_bibtex_file(bib_file)
    if after_db and before_db:
        for e in after_db.entries:
            k = e.get('ID', '')
            if k in dois_before:
                doi_after = utils.normalize_doi(e.get('doi') or e.get('DOI'))
                if dois_before[k] and doi_after and dois_before[k] != doi_after:
                    print(f"  Suspicious metadata change detected for {k}")
                    print(f"  Warning: betterbib changed DOI for {k} ({dois_before[k]} → {doi_after}), restoring")
                    shutil.copy2(backup_path, bib_file)
                    return

    # remove the temporary backup if everything looks sane
    try:
        backup_path.unlink()
    except Exception:  # best-effort cleanup only
        pass

    # some entries get commented-out; let the shared helper deal with it
    # once betterbib may comment entries; the shared fix handles it
    uncomment_bibtex_entries(bib_file)


def abbreviate_with_betterbib(bib_file: Path) -> None:
    """Invoke ``betterbib abbreviate-journal-names`` on *bib_file*.

    This helper is deliberately lightweight compared to
    :func:`update_with_betterbib` – we don't create an extra backup since a
    full backup was already created by :func:`process_bib_file` and the
    operation is generally idempotent.  The routine prints warnings if the
    external command fails, but never raises an exception.  Abbreviations
    provided by the tool are preferred over the built-in map/heuristic;
    the latter still runs later as a fallback.
    """
    print("  Abbreviating journal names with betterbib...")
    # import directly like :func:`update_with_betterbib`; failures are
    # unexpected because the package is required, but we retain a friendly
    # warning rather than letting an ImportError bubble up.
    try:
        import betterbib  # type: ignore[import]
    except ImportError:  # pragma: no cover
        print("  Warning: betterbib not installed, skipping abbreviation")
        return

    cmd = [sys.executable, '-m', 'betterbib.cli._main', 'abbreviate-journal-names', '-i', str(bib_file)]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("  Warning: betterbib abbreviation timed out")
        return
    except Exception as exc:  # pragma: no cover - very rare
        print(f"  Warning: betterbib abbreviation failed: {exc}")
        return

    if result.returncode != 0:
        if result.returncode < 0:
            sig = -result.returncode
            msg = f"crashed with signal {sig}"
        else:
            msg = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        print(f"  Warning: betterbib abbreviation had issues: {msg}")
        return

    print("  betterbib journal abbreviation completed")


def format_with_bibfmt(bib_file: Path) -> None:
    """Call ``bibfmt`` to format and drop unwanted fields.

    The function is intentionally simple: we build the command-line once,
    invoke it and ignore most errors.  ``bibfmt`` is already robust and
    the surrounding workflow has further sanity checks.
    """
    print("  Formatting with bibfmt and removing non-standard fields...")

    cmd = ['bibfmt', '-i', '--indent', '2', '--align', '14', '-d', 'braces']
    for field in FIELDS_TO_REMOVE:
        cmd += ['--drop', field]
    cmd.append(str(bib_file))

    # keep both the raw text and the parsed database so we can
    # intelligently detect title/DOI changes later.
    try:
        before = bib_file.read_text(encoding='utf-8')
    except Exception:
        before = None
    try:
        before_db = core.parse_bibtex_file(bib_file)
    except Exception:
        before_db = None

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except Exception as exc:  # pragma: no cover
        print(f"  Warning: bibfmt failed: {exc}")
        return

    if result.returncode != 0:
        msg = result.stderr.strip() or result.stdout.strip() or f"return code {result.returncode}"
        print(f"  Warning: bibfmt had issues: {msg}")
        return
    else:
        print("  bibfmt formatting completed")

    # parse the after state so we can look for actual field-level changes
    try:
        after = bib_file.read_text(encoding='utf-8')
    except Exception:
        after = None
    try:
        after_db = core.parse_bibtex_file(bib_file)
    except Exception:
        after_db = None

    if before_db and after_db:
        changed_titles = False
        changed_dois = False
        before_lookup = {e.get('ID', ''): e for e in before_db.entries}
        for entry in after_db.entries:
            key = entry.get('ID', '')
            orig = before_lookup.get(key)
            if not orig:
                continue
            if orig.get('title') and entry.get('title') and orig.get('title') != entry.get('title'):
                changed_titles = True
            doi_before = utils.normalize_doi(orig.get('doi') or orig.get('DOI') or orig.get('Doi'))
            doi_after = utils.normalize_doi(entry.get('doi') or entry.get('DOI') or entry.get('Doi'))
            if doi_before and doi_after and doi_before != doi_after:
                changed_dois = True
        if changed_titles:
            print("  Warning: bibfmt appears to have altered title")
        if changed_dois:
            print("  Warning: bibfmt changed DOI for entries")
    elif before is not None and after is not None and before != after:
        # fallback to the old always-warning behaviour if parsing failed
        print("  Warning: bibfmt appears to have altered title")
        print("  Warning: bibfmt changed DOI for entries")


# ---------------------------------------------------------------------------
# duplicate/DOI key logic
# ---------------------------------------------------------------------------

def find_duplicates(bib_files: Iterable[Path]) -> dict[str, list[tuple[Path, dict]]]:
    """Return a mapping key -> list of (file, entry) for duplicated keys."""
    entries: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if not db:
            continue
        for entry in db.entries:
            key = entry.get('ID', '')
            if key:
                entries[key].append((bib, entry))
    return {k: v for k, v in entries.items() if len(v) > 1}


def choose_best_entry(entries: list[tuple[Path, dict]]) -> dict:
    """Return the most complete entry from *entries*.

    A very simple heuristic: count how many ``important_fields`` are
    present, and break ties by total number of keys.  The original CLI used
    this logic and the tests depend on its behaviour so we keep it verbatim.
    """
    def score(entry: dict) -> float:
        important = ['title', 'author', 'year', 'journal', 'doi', 'pages', 'volume']
        # start with a float so that later additions preserve a float type
        s: float = sum(1 for f in important if entry.get(f))
        s += 0.1 * len(entry)
        return s

    return max((e for _, e in entries), key=score)


def synchronize_duplicates(bib_files: Iterable[Path], duplicates: dict) -> None:
    """Rewrite all files so that duplicate keys share the same data."""
    if not duplicates:
        return
    dbs = {bib: core.parse_bibtex_file(bib) for bib in bib_files}
    for key, items in duplicates.items():
        best = choose_best_entry(items)
        for bib, _ in items:
            db = dbs.get(bib)
            if not db:
                continue
            for idx, ent in enumerate(db.entries):
                if ent.get('ID') == key:
                    new = best.copy()
                    new['ID'] = key
                    db.entries[idx] = new
    for bib, db in dbs.items():
        if db:
            core.write_bib_file(bib, db)
            print(f"  Updated {bib}")


def find_duplicate_dois(bib_files: Iterable[Path]) -> dict[str, list[dict]]:
    """Return mapping DOI -> list of metadata dicts for keys sharing the DOI."""
    doi_map: dict[str, list[dict]] = defaultdict(list)
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if not db:
            continue
        for entry in db.entries:
            key = utils.normalize_unicode(entry.get('ID', ''))
            doi = entry.get('doi') or entry.get('DOI') or entry.get('Doi')
            norm = utils.normalize_doi(doi)
            if norm:
                doi_map[norm].append({'key': key, 'file': bib, 'entry': entry})
    return {d: lst for d, lst in doi_map.items() if len({e['key'] for e in lst}) > 1}


def choose_best_key(entries_list: list[dict]) -> str:
    """Pick the most sensible citation key from a list of DOI entries.

    A simple heuristic is applied to score each key.  Uppercase first letters,
    a pattern like ``Name2020`` and absence of underscores are favoured, with a
    small penalty for length.  The scoring logic is intentionally localised
    here to keep the public API minimal.
    """
    def score(k: str) -> float:
        s = 0.0
        if k and k[0].isupper():
            s += 10
        if re.match(r'^[A-Z][a-z]+\d{4}', str(k)):
            s += 20
        if '_' not in str(k):
            s += 5
        s -= 0.1 * len(str(k))
        return s

    keys = list({e['key'] for e in entries_list})
    return max(keys, key=score)


def consolidate_duplicate_dois(bib_files: Iterable[Path], duplicates: dict) -> dict[str, str]:
    """Consolidate entries sharing the same DOI and return key mapping.

    The algorithm is executed in-place on the files given in *bib_files*.
    """
    mapping: dict[str, str] = {}
    if not duplicates:
        return mapping
    dbs = {bib: core.parse_bibtex_file(bib) for bib in bib_files}
    for doi, entries in duplicates.items():
        best_key = choose_best_key(entries)
        best_entry = choose_best_entry([(e['file'], e['entry']) for e in entries])
        best_entry['ID'] = best_key
        print(f"  DOI {doi}: consolidating to {best_key}")
        for info in entries:
            old = info['key']
            if old != best_key:
                mapping[old] = best_key
        for bib in {info['file'] for info in entries}:
            db = dbs.get(bib)
            if not db:
                continue
            # remove or replace old entries
            to_del = []
            for idx, ent in enumerate(db.entries):
                k = utils.normalize_unicode(ent.get('ID', ''))
                if k != best_key and k in mapping:
                    to_del.append(idx)
                elif k == best_key:
                    db.entries[idx] = best_entry.copy()
            for idx in reversed(to_del):
                del db.entries[idx]
    for bib, db in dbs.items():
        if db:
            core.write_bib_file(bib, db)
    print(f"  Consolidated {len(duplicates)} DOIs, created {len(mapping)} key mappings")
    return mapping


# ---------------------------------------------------------------------------
# high-level workflows
# ---------------------------------------------------------------------------



def _apply_basic_fixes(bib_file: Path) -> None:
    """Run the standard collection of small fix routines on *bib_file*."""
    fix_invalid_utf8_bytes(bib_file)
    fix_html_entities(bib_file)
    fix_malformed_author_fields(bib_file)
    remove_accents_from_names(bib_file)
    fix_problematic_unicode(bib_file)
    # abbreviate journal titles before other formatting; the mapping is
    # intentionally small but ensures the feature is exercised by tests.
    from .fixes import abbreviate_journal_names
    abbreviate_journal_names(bib_file)
    # we previously wrapped the Path in a BibFile here; the fix
    # function now expects a Path directly.
    fix_unescaped_percent(bib_file)
    # legacy date fixes run at end
    fix_legacy_year_fields(bib_file)
    fix_legacy_month_fields(bib_file)


def process_bib_file(
    bib_file: Path,
    create_backups: bool = True,
    use_betterbib: bool = True,
) -> None:
    """Apply the standard series of fixes and formatting operations to one file.

    The *use_betterbib* flag allows callers to disable both the metadata update
    and the journal abbreviation steps.  This is useful when the optional
    helper is unavailable or known to be broken (for example on minimal
    installations or when the binary resides in the source tree).
    """
    print(f"\nProcessing {bib_file.name}...")
    if create_backups:
        create_backup(bib_file)
    if use_betterbib:
        update_with_betterbib(bib_file)
        abbreviate_with_betterbib(bib_file)
    else:
        print("  Skipping betterbib steps")
    print("  Fixing invalid UTF-8 byte sequences...")
    _apply_basic_fixes(bib_file)
    format_with_bibfmt(bib_file)
    print("  Checking for commented entries...")
    from .fixes import uncomment_bibtex_entries
    uncomment_bibtex_entries(bib_file)
    print(f"  Completed processing {bib_file.name}")




def consolidate_duplicate_titles(bib_files: Iterable[Path]) -> dict[str, str]:
    """Find title duplicates and return mapping old_key -> new_key."""
    title_map: dict[str, list[tuple[Path, dict]]] = defaultdict(list)
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if not db:
            continue
        for entry in db.entries:
            title = entry.get('title', '')
            norm = utils.normalize_title(title)
            if norm:
                title_map[norm].append((bib, entry))
    duplicates = {t: e for t, e in title_map.items() if len(e) > 1}
    keymap: dict[str, str] = {}
    if not duplicates:
        print("  No duplicate titles to consolidate.")
        return {}
    dbs = {bib: core.parse_bibtex_file(bib) for bib in bib_files}
    for norm, entries in duplicates.items():
        best = choose_best_entry(entries)
        best_key = best['ID']
        print(f"  Title '{norm}' -> keeping {best_key}")
        for bib, ent in entries:
            old = utils.normalize_unicode(ent.get('ID', ''))
            if not old:
                continue
            if old != best_key:
                keymap[old] = best_key
        for bib, ent in entries:
            db = dbs.get(bib)
            if not db:
                continue
            k = utils.normalize_unicode(ent.get('ID', ''))
            if k == best_key and bib not in keymap.values():
                # ensure content matches best entry
                for idx,e in enumerate(db.entries):
                    if utils.normalize_unicode(e.get('ID','')) == best_key:
                        db.entries[idx] = best.copy()
                        db.entries[idx]['ID'] = best_key
                        break
            elif k != best_key:
                for idx,e in enumerate(db.entries):
                    if utils.normalize_unicode(e.get('ID','')) == k:
                        del db.entries[idx]
                        break
    for bib, db in dbs.items():
        if db:
            core.write_bib_file(bib, db)
    print(f"  Consolidated {len(duplicates)} title groups")
    return keymap


def remove_duplicate_entries_across_files(bib_files: Iterable[Path]) -> int:
    """Keep a single copy of each key across a set of bib files."""
    key_map: dict[str, list[Path]] = defaultdict(list)
    dbs: dict[Path, Any] = {}
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if db:
            dbs[bib] = db
            for entry in db.entries:
                key = entry.get('ID', '')
                if key:
                    key_map[key].append(bib)
    removed = 0
    for key, files in key_map.items():
        if len(files) < 2:
            continue
        files_sorted = sorted(files, key=lambda p: p.name)
        keeper = files_sorted[0]
        for other in files_sorted[1:]:
            db = dbs[other]
            entries_to_remove = [i for i,e in enumerate(db.entries) if e.get('ID','') == key]
            for idx in reversed(entries_to_remove):
                del db.entries[idx]
                removed += 1
        print(f"    {key}: kept in {keeper.name}, removed from {len(files)-1} file(s)")
    for bib, db in dbs.items():
        if any(k in key_map and bib in key_map[k] for k in key_map):
            core.write_bib_file(bib, db)
    if removed:
        print(f"\n  Removed {removed} duplicate entry/entries")
    return removed


def remove_unused_entries(bib_files: Iterable[Path]) -> int:
    """Delete entries that are not cited anywhere (crossrefs are preserved)."""
    tex_files = helpers.collect_all_tex_files()
    cited = set()
    for tex in tex_files:
        cited.update(helpers.extract_citations_from_tex(tex))
    cross = set()
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if not db:
            continue
        for entry in db.entries:
            cr = entry.get('crossref') or entry.get('Crossref')
            if cr:
                norm = utils.normalize_unicode(cr)
                if norm:
                    cross.add(norm)
    cited |= cross
    removed = 0
    for bib in bib_files:
        db = core.parse_bibtex_file(bib)
        if not db:
            continue
        to_drop = [i for i,e in enumerate(db.entries) if utils.normalize_unicode(e.get('ID','')) not in cited]
        for idx in reversed(to_drop):
            del db.entries[idx]
            removed += 1
        if to_drop:
            core.write_bib_file(bib, db)
            print(f"  {bib.name}: removed {len(to_drop)} unused entries")
    print(f"  Total unused entries removed: {removed}")
    return removed


def curate_bibliography(
    bib_files: Iterable[Path],
    create_backups: bool = True,
    preserve_keys: bool = False,
    use_betterbib: bool = True,
) -> None:
    # honour environment variable override for convenience in CI or
    # minimal installs
    if os.environ.get("BIBFIXER_NO_BETTERBIB"):
        use_betterbib = False
    """Run the full curation workflow on a list of files.

    See :mod:`bibfixer.cli` for the original documentation and steps.
    """
    print("=" * 70)
    print("BibTeX Curation")
    print("=" * 70)

    # initial statistics may be useful for reporting later
    # optionally collect statistics (not currently used)
    # (previous implementation stashed _before here; it was never used.)

    # process each file individually
    for bib in bib_files:
        process_bib_file(
            bib,
            create_backups=create_backups,
            use_betterbib=use_betterbib,
        )

    # key sanitization and updates are handled by helpers directly
    if not preserve_keys:
        all_mappings: dict[str, str] = {}
        for bib in bib_files:
            all_mappings.update(helpers.sanitize_citation_keys(bib))
        texs = helpers.collect_all_tex_files()
        if any(t.name == 'main.tex' for t in texs):
            print("\nKey standardization will run (main.tex present)")
            for bib in bib_files:
                all_mappings.update(helpers.standardize_citation_keys(bib))
        else:
            print("\nSkipping citation key standardization (no main.tex found)")
        if all_mappings:
            helpers.update_tex_citations(texs, all_mappings)

    # remove unused entries
    remove_unused_entries(bib_files)

    # deduplicate and sync remaining entries
    dup = find_duplicates(bib_files)
    synchronize_duplicates(bib_files, dup)

    if not preserve_keys:
        doi_dup = find_duplicate_dois(bib_files)
        doi_map = consolidate_duplicate_dois(bib_files, doi_dup)
        if doi_map:
            helpers.update_tex_citations(helpers.collect_all_tex_files(), doi_map)
        title_map = consolidate_duplicate_titles(bib_files)
        if title_map:
            helpers.update_tex_citations(helpers.collect_all_tex_files(), title_map)

    # final formatting and fix pass - reuse the basic fix helper to avoid
    # repeating logic. we still run bibfmt once more and uncomment entries
    # after everything settles.
    for bib in bib_files:
        format_with_bibfmt(bib)
        _apply_basic_fixes(bib)
        uncomment_bibtex_entries(bib)
        print(f"  ✓ {bib.name}: All fixes applied")

    # final validation/report
    from .validation import generate_report
    generate_report(bib_files)

    print("\nCuration complete!")

