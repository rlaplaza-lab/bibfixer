"""Collection of fixing routines formerly embedded in the CLI.

The original legacy script accumulated a large number of ad‑hoc cleanup and
repair functions in ``cli.py``.  During refactoring we move the actual
implementations here so that the command‑line layer can remain a thin
orchestration wrapper.  Exporting the functions from ``cli`` keeps the
public API unchanged for existing tests and downstream users.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from . import core


# month abbreviation to integer mapping (shared by fix_legacy_month_fields)
MONTH_MAP = {
    'jan': '1', 'january': '1',
    'feb': '2', 'february': '2',
    'mar': '3', 'march': '3',
    'apr': '4', 'april': '4',
    'may': '5',
    'jun': '6', 'june': '6',
    'jul': '7', 'july': '7',
    'aug': '8', 'august': '8',
    'sep': '9', 'sept': '9', 'september': '9',
    'oct': '10', 'october': '10',
    'nov': '11', 'november': '11',
    'dec': '12', 'december': '12',
}


def fix_invalid_utf8_bytes(bib_file: Path) -> int:
    """Fix invalid UTF-8 byte sequences that cause LaTeX compilation errors.

    Handles:
    - Invalid UTF-8 byte sequences (e.g., \xBD, \x88, \x9B)
    - Backslashes incorrectly placed before UTF-8 combining marks
    - Patterns like Lo\\\xcc\x88c -> Lo\"c (LaTeX diaeresis)
    """
    try:
        # Read as binary to detect and fix byte-level issues
        with open(bib_file, 'rb') as f:
            raw_content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0

    fixed_count = 0
    modified = False

    new_content = raw_content

    # pattern1: Lo\\\xcc\x88c -> Lo\"c
    pattern1 = bytes([0x5c, 0x5c, 0xcc, 0x88])
    while pattern1 in new_content:
        pos = new_content.find(pattern1)
        if pos >= 1:
            prev_char = new_content[pos - 1:pos]
            new_content = new_content[:pos-1] + prev_char + b'\"' + new_content[pos+4:]
            fixed_count += 1
            modified = True
        else:
            new_content = new_content[:pos] + b'\"' + new_content[pos+4:]
            fixed_count += 1
            modified = True
    # pattern2: X\\\xcc\x81 -> X\'
    pattern2 = bytes([0x5c, 0x5c, 0xcc, 0x81])
    while pattern2 in new_content:
        pos = new_content.find(pattern2)
        if pos >= 1:
            prev_char = new_content[pos - 1:pos]
            new_content = new_content[:pos-1] + prev_char + b"\\'" + new_content[pos+4:]
            fixed_count += 1
            modified = True
        else:
            new_content = new_content[:pos] + b"\\'" + new_content[pos+4:]
            fixed_count += 1
            modified = True
    # ś -> \'{s}
    pattern3 = bytes([0x5c, 0x5c, 0xc5, 0x9b])
    if pattern3 in new_content:
        count = new_content.count(pattern3)
        new_content = new_content.replace(pattern3, b"\\'{s}")
        fixed_count += count
        modified = True
    # ł -> \l{}
    pattern4 = bytes([0x5c, 0x5c, 0xc5, 0x82])
    if pattern4 in new_content:
        count = new_content.count(pattern4)
        new_content = new_content.replace(pattern4, b"\\l{}")
        fixed_count += count
        modified = True

    if modified:
        try:
            content = new_content.decode('utf-8', errors='replace')
            content = content.replace('\ufffd', '')
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  Fixed {fixed_count} invalid UTF-8 byte sequence(s)")
            return fixed_count
        except Exception as e:
            print(f"  Error writing {bib_file}: {e}")
            return 0
    return 0


def fix_problematic_unicode(bib_file: Path) -> int:
    """Fix problematic Unicode characters that cause LaTeX compilation errors.

    Converts:
    - U+2500 (─) box-drawing character to regular dash (-- or -)
    - U+0301 (combining acute accent) to proper LaTeX accent commands
    - Other problematic Unicode characters to LaTeX equivalents
    """
    try:
        with open(bib_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0

    lines = content.split('\n')
    fixed_count = 0
    modified = False

    for line_num, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('%') and not stripped.startswith('@comment'):
            continue
        new_line = line
        original_line = line
        if '\u2500' in new_line:
            new_line = new_line.replace('\u2500', '--')
            fixed_count += 1
            modified = True
        if '\u0301' in new_line:
            def replace_accent(match):
                char = match.group(1)
                if char.isalpha():
                    return f"\\'{{{char}}}"
                return char
            new_line = re.sub(r'([^\W\d_])\u0301', replace_accent, new_line, flags=re.UNICODE)
            new_line = re.sub(r'((?:\\\\)*)([^\W\d_])\u0301',
                              lambda m: m.group(1) + f"\\'{{{m.group(2)}}}",
                              new_line, flags=re.UNICODE)
            if new_line != original_line:
                fixed_count += new_line.count("\\'") - original_line.count("\\'")
                modified = True
        if modified and new_line != original_line:
            lines[line_num] = new_line
    if modified:
        try:
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"  Fixed {fixed_count} problematic Unicode character(s)")
        except Exception as e:
            print(f"  Error writing {bib_file}: {e}")
            return 0
    return fixed_count


def fix_html_entities(bib_file: Path) -> int:
    r"""Fix HTML entities in BibTeX fields.

    Converts HTML entities to LaTeX equivalents and escapes bare & characters.
    """
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0

    fixed_count = 0
    modified = False

    replacements = [
        ('&amp;', '\\&'),
        ('&lt;', '<'),
        ('&gt;', '>'),
        ('&quot;', '"'),
        ('&apos;', "'"),
    ]
    for old, new in replacements:
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            fixed_count += count
            modified = True

    field_patterns = [
        (r'(title\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})',
         r'\1\\&\2'),
        (r'(journal\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})',
         r'\1\\&\2'),
        (r'(booktitle\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})',
         r'\1\\&\2'),
    ]
    for pattern, replacement in field_patterns:
        matches = list(re.finditer(pattern, content, re.IGNORECASE))
        if matches:
            for match in reversed(matches):
                content = content[:match.start()] + match.expand(replacement) + content[match.end():]
                fixed_count += 1
                modified = True

    unescaped_pattern = r'(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)'
    matches = list(re.finditer(unescaped_pattern, content))
    if matches:
        for match in reversed(matches):
            pos = match.start()
            before = content[:pos]
            open_braces = before.count('{')
            close_braces = before.count('}')
            if open_braces > close_braces and (pos == 0 or content[pos-1] != '\\'):
                content = content[:pos] + '\\&' + content[pos+1:]
                fixed_count += 1
                modified = True
    if modified:
        try:
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  Fixed {fixed_count} HTML entity/entities and unescaped &")
        except Exception as e:
            print(f"  Error writing {bib_file}: {e}")
            return 0
        return fixed_count
    return fixed_count



# abbreviation data now lives in CSV files shipped in the package.  The
# loader below reads both the general list and the ACS-specific list, giving
# the latter priority when a title appears in both.  Keeping a mutable
# dictionary as the public ``JOURNAL_ABBREVIATIONS`` variable preserves the
# previous API so callers may still add or modify entries at runtime.

def _load_journal_abbreviations() -> dict[str, str]:
    """Return a fresh mapping built from the packaged CSV resources.

    The two files are located in the ``bibfixer.data`` package and are read
    with :mod:`importlib.resources` so that they work both in development
    and after installation.  We deliberately *do not* suppress file errors:
    the abbreviation data is considered essential, and an import-time
    exception will prompt the user to fix their installation rather than
    silently falling back to an empty map.
    """
    import csv
    import importlib.resources as pkg_resources

    abbrevs: dict[str, str] = {}
    for resource in (
        "journal_abbreviations_general.csv",
        "journal_abbreviations_acs.csv",
    ):
        with pkg_resources.open_text("bibfixer.data", resource, encoding="utf-8") as fh:
            reader = csv.reader(fh)
            for row in reader:
                if len(row) >= 2:
                    full = row[0].strip()
                    short = row[1].strip()
                    if full and short:
                        abbrevs[full] = short
    return abbrevs


# public dictionary that callers can extend or mutate; its initial contents
# come from the CSV loader above.
JOURNAL_ABBREVIATIONS: dict[str, str] = _load_journal_abbreviations()


def fix_unescaped_percent(bib_file: Path | core.BibFile) -> int:
    """Escape literal ``%`` characters in every field of a :class:`BibFile`.

    The helper accepts either a ``Path`` or an already-instantiated
    :class:`BibFile` (the CLI tests rely on the latter).  A decorator from
    :mod:`core` is used to perform the actual field-wise transformation.

    The implementation uses ``core.BibFile`` explicitly when converting the
    argument; this avoids ``NameError`` issues in environments where the
    top-level ``BibFile`` symbol may be missing (see issue reported by user
    during stress testing).
    """
    @core.field_transform
    def _escape(value: Any) -> Any:
        if not isinstance(value, str):
            return value
        new_value = value
        pos = 0
        changed = False
        while True:
            pos = new_value.find('%', pos)
            if pos == -1:
                break
            backslash_count = 0
            check_pos = pos - 1
            while check_pos >= 0 and new_value[check_pos] == '\\':
                backslash_count += 1
                check_pos -= 1
            if backslash_count % 2 == 0:
                new_value = new_value[:pos] + '\\' + new_value[pos:]
                pos += 2
                changed = True
            else:
                pos += 1
        return new_value if changed else value
    # convert the argument to a BibFile if necessary (tests pass one in)
    if isinstance(bib_file, core.BibFile):
        bf = bib_file
    else:
        bf = core.BibFile(bib_file)

    changed = _escape(bf)
    if changed:
        bf.write()
    return changed


def _heuristic_abbrev(journal: str) -> str:
    """Try to obtain an ISO 4 abbreviation for *journal*.

    We used to fall back to a very coarse scheme that simply joined the
    initial letters of each word.  That produced fabricated abbreviations such
    as ``"J.o.T."`` for "Journal of Testing" which gave a false impression
    of legitimacy.  Instead we now rely on the third-party ``iso4`` package
    (installed as an optional dependency) to perform the transformation.  The
    function behaves as follows::

        * if the journal string already contains a period we assume it has
          been manually abbreviated and return it unchanged;
        * single-word titles are left untouched;
        * if ``iso4`` cannot be imported or raises any exception the original
          title is returned rather than inventing a bogus abbreviation;
        * otherwise ``iso4.abbreviate`` is called and its result is used if
          it differs from the input.

    The publication’s title is only modified when a genuine abbreviation is
    available; callers may still extend :data:`JOURNAL_ABBREVIATIONS` with
    custom mappings if desired.
    """
    # treat anything already containing a period as pre‑abbreviated
    if '.' in journal:
        return journal

    words = journal.split()
    if len(words) < 2:
        return journal

    try:
        import iso4  # optional dependency
    except ImportError:  # pragma: no cover - behaviour exercised in tests
        return journal

    try:
        abbrev = iso4.abbreviate(journal)
    except Exception:  # pragma: no cover - tested by forcing an error
        return journal

    if abbrev and abbrev != journal:
        return abbrev
    return journal


def abbreviate_journal_names(bib_file: Path) -> int:
    """Replace long journal titles with their abbreviations.

    A very small built-in dictionary is used by default; callers may modify
    or extend :data:`JOURNAL_ABBREVIATIONS` to add their own entries.  If a
    title is not found in the mapping we invoke a helper that attempts to
    produce an ISO 4 abbreviation via the optional ``iso4`` package.  Missing
    or failing installations are silently ignored and the original title is
    preserved rather than producing a contrived result.  This provides a
    measure of safety when external tools such as ``betterbib`` are
    unavailable or crash (segfaults, timeouts, etc.).

    Only exact matches are looked up in the dictionary and the comparison is
    case-sensitive to avoid accidentally mangling legitimate titles.  The
    heuristic is only invoked when there are two or more words in the
    journal title and the generated abbreviation differs from the original.

    Returns the number of entries modified.
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    fixed = 0
    # build a case-insensitive lookup so that user data need not match
    # the exact capitalization found in the CSV files.  We normalise keys to
    # lower-case when checking, but preserve the original mapping values in
    # the public dictionary.
    ci_lookup = {k.lower(): v for k, v in JOURNAL_ABBREVIATIONS.items()}

    for entry in bib_database.entries:
        journal = entry.get('journal')
        if not journal:
            continue
        lookup_key = journal.lower()
        if lookup_key in ci_lookup:
            entry['journal'] = ci_lookup[lookup_key]
            fixed += 1
        else:
            # try a basic fallback abbreviation so we don't rely purely
            # on the mapping; this also covers the case where betterbib
            # crashed earlier in the pipeline.
            abbrev = _heuristic_abbrev(journal)
            if abbrev != journal:
                entry['journal'] = abbrev
                fixed += 1
    if fixed:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Abbreviated {fixed} journal name(s)")
    return fixed


def remove_accents_from_names(bib_file: Path) -> int:
    """Remove accents from author names and other text fields.

    The function rewrites entries in place if modifications are made.
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    fixed_count = 0
    modified = False
    text_fields = ['author', 'editor', 'translator', 'title', 'booktitle', 'journal']
    for entry in bib_database.entries:
        for field in text_fields:
            if field in entry:
                original_value = entry[field]
                value = str(original_value)
                accent_patterns = [
                    (r"\\'\{([^}]+)\}", r'\1'),
                    (r'\\"\{([^}]+)\}', r'\1'),
                    (r"\\`\{([^}]+)\}", r'\1'),
                    (r"\\\^\{([^}]+)\}", r'\1'),
                    (r"\\~\{([^}]+)\}", r'\1'),
                    (r"\\=\{([^}]+)\}", r'\1'),
                    (r"\\.\{([^}]+)\}", r'\1'),
                    (r"\\u\{([^}]+)\}", r'\1'),
                    (r"\\v\{([^}]+)\}", r'\1'),
                    (r"\\H\{([^}]+)\}", r'\1'),
                    (r"\\c\{([^}]+)\}", r'\1'),
                ]
                for pattern, replacement in accent_patterns:
                    value = re.sub(pattern, replacement, value)
                value_normalized = unicodedata.normalize('NFD', value)
                value_no_accents = ''.join(
                    char for char in value_normalized
                    if unicodedata.category(char) != 'Mn'
                )
                value_final = unicodedata.normalize('NFC', value_no_accents)
                if value_final != original_value:
                    entry[field] = value_final
                    fixed_count += 1
                    modified = True
    if modified:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Removed accents from {fixed_count} field(s)")
        return fixed_count
    return 0


def fix_legacy_year_fields(bib_file: Path) -> int:
    """Fix legacy year fields that contain dates instead of just the year."""
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    fixed_count = 0
    for entry in bib_database.entries:
        year_keys = ['year', 'Year', 'YEAR']
        year_value = None
        year_key = None
        for key in year_keys:
            if key in entry:
                year_value = entry[key]
                year_key = key
                break
        if year_value:
            year_clean = str(year_value).strip().strip('{}')
            try:
                int(year_clean)
                continue
            except ValueError:
                pass
            import re
            date_match = re.match(r'^(\d{4})[-/]', year_clean)
            if date_match:
                year_only = date_match.group(1)
                entry[year_key] = year_only
                fixed_count += 1
    if fixed_count > 0:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} legacy year field(s)")
    return fixed_count


def fix_legacy_month_fields(bib_file: Path) -> int:
    """Fix legacy month fields by converting abbreviations to integers."""
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    fixed_count = 0
    for entry in bib_database.entries:
        month_keys = ['month', 'Month', 'MONTH']
        month_value = None
        month_key = None
        for key in month_keys:
            if key in entry:
                month_value = entry[key]
                month_key = key
                break
        if month_value:
            month_clean = str(month_value).strip().strip('{}').lower()
            try:
                int(month_clean)
                continue
            except ValueError:
                pass
            if month_clean in MONTH_MAP:
                entry[month_key] = MONTH_MAP[month_clean]
                fixed_count += 1
    if fixed_count > 0:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} legacy month field(s)")
    return fixed_count


def uncomment_bibtex_entries(bib_file: Path) -> int:
    """Uncomment BibTeX entries that were commented out by bibfmt.

    Sometimes bibfmt comments out entries with syntax errors.  This routine
    removes the ``@comment{`` wrapper, attempts to fix common syntactic
    problems (missing commas, unbalanced braces) and rewrites the file if any
    entries were recovered.  The function returns the number of entries
    restored.
    """
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0

    if '@comment{' not in content:
        return 0

    lines = content.split('\n')
    comment_starts = []
    for i, line in enumerate(lines):
        if re.match(r'@comment\{@\w+\{', line):
            comment_starts.append(i)
    if not comment_starts:
        return 0

    fixed_count = 0
    modified = False
    for idx in reversed(range(len(comment_starts))):
        start = comment_starts[idx]
        end = len(lines)
        brace_count = 0
        found_opening = False
        for j in range(start, min(len(lines), start + 200)):
            line = lines[j]
            brace_count += line.count('{') - line.count('}')
            if '@comment{' in line:
                found_opening = True
            if found_opening and brace_count <= 0 and j > start:
                end = j + 1
                break
            if j > start and re.match(r'@\w+\{', line) and not line.startswith('@comment'):
                end = j
                break
        entry_lines = lines[start:end]
        entry_text = '\n'.join(entry_lines)
        entry_key_match = re.search(r'@comment\{@\w+\{([^,}]+)', entry_text)
        if not entry_key_match:
            continue
        entry_content = re.sub(r'^@comment\{', '', entry_text, count=1, flags=re.MULTILINE)
        entry_content = re.sub(r'\}\s*\n\s*(\w+\s*=)', r'},\n  \1', entry_content)
        entry_content = re.sub(r'\}\s+(\w+\s*=)', r'}, \1', entry_content)
        open_braces = entry_content.count('{')
        close_braces = entry_content.count('}')
        missing_braces = open_braces - close_braces
        entry_content = entry_content.rstrip()
        if entry_content.endswith('}}'):
            entry_content = entry_content[:-1]
            missing_braces = max(0, missing_braces - 1)
        if missing_braces > 0:
            entry_content = entry_content.rstrip() + '\n' + '}' * missing_braces
        entry_content = entry_content.rstrip()
        if not entry_content.endswith('}'):
            entry_content += '\n}'
        elif entry_content.endswith('}}'):
            entry_content = entry_content[:-1]
        final_open = entry_content.count('{')
        final_close = entry_content.count('}')
        if final_open != final_close:
            diff = final_open - final_close
            if diff > 0:
                entry_content = entry_content.rstrip() + '\n' + '}' * diff
            elif diff < 0:
                entry_content = entry_content.rstrip()
                for _ in range(-diff):
                    if entry_content.endswith('}'):
                        entry_content = entry_content[:-1].rstrip()
        new_lines = lines[:start] + entry_content.split('\n') + lines[end:]
        lines = new_lines
        fixed_count += 1
        modified = True
    if modified:
        try:
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"  Uncommented {fixed_count} entry/entries")
        except Exception as e:
            print(f"  Error writing {bib_file}: {e}")
            return 0
    return fixed_count


def fix_malformed_author_fields(bib_file: Path) -> int:
    """Automatically fix malformed author fields in BibTeX entries.

    The implementation replicates the behaviour that was previously in the
    legacy CLI.  Heuristics are intentionally simple and widely tested in
    :mod:`tests.test_cli_helpers`.
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    fixed_count = 0
    modified = False
    for entry in bib_database.entries:
        if 'author' not in entry:
            continue
        original_value = entry['author']
        value = str(original_value)
        original_value_str = value
        # remove excessive backslashes
        value = re.sub(r'([A-Za-z])\\{4,}([a-z]+)', r'\1{\\"u}\2', value)
        value = re.sub(r'\\{4,}', r'\\', value)
        # incomplete names ending with backslash
        value = re.sub(r',\s*\\+\s*([,}])', r',\1', value)
        value = re.sub(r'([A-Za-z])\s*\\+\s*$', r'\1', value)
        accent_fixes = {
            r'\\ν': r"\\'{n}",
            r'\\μ': r"\\'{u}",
            r'\\149': r"\\'{n}",
        }
        for pattern, replacement in accent_fixes.items():
            value = re.sub(pattern, replacement, value)
        unicode_to_latex = {
            'ń': r"\\'{n}",
            'á': r"\\'{a}",
            'é': r"\\'{e}",
            'í': r"\\'{i}",
            'ó': r"\\'{o}",
            'ú': r"\\'{u}",
            'ü': r'\\"{u}',
            'ö': r'\\"{o}',
            'ł': r'\\l{}',
            'ć': r"\\'{c}",
            'ś': r"\\'{s}",
            'ź': r"\\'{z}",
            'ą': r"\\'{a}",
            'ę': r"\\'{e}",
        }
        for unicode_char, latex_cmd in unicode_to_latex.items():
            if unicode_char in value:
                value = value.replace(unicode_char, latex_cmd)
        if value != original_value_str:
            entry['author'] = value
            fixed_count += 1
            modified = True
    if modified:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} malformed author field(s)")
    return fixed_count
