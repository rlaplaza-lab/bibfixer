from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Set, Dict
import re

from . import utils
from .core import parse_bibtex_file, write_bib_file


# common citation patterns used when parsing and rewriting
# ``.tex`` files.  These were previously hard-coded in two separate
# functions; keeping a single constant reduces the chance of divergence and
# makes the behaviour easier to test.
# common citation patterns used when parsing and rewriting
# ``.tex`` files.  Historically the original script only knew about a
# handful of natbib commands but real documents often employ a variety of
# citation macros (\parencite, \textcite, \autocite, etc.).  Rather than
# maintaining a long hard-coded list we match any command containing the
# word ``cite`` with optional alphabetic prefixes/suffixes.  This keeps
# the behaviour broad enough for most LaTeX packages while remaining easy
# to test.
CITATION_PATTERNS: list[str] = [
    r'\\[A-Za-z]*cite[a-zA-Z]*\{([^}]+)\}',
]


def get_corresponding_bib(tex_file: Path) -> Path | None:
    """Return the bib file we expect to accompany *tex_file*.

    The heuristics are copied from the legacy script.  This helper makes
    it easier to test and reuse the logic from both validation and curation
    workflows.
    """
    tex_path = Path(tex_file)
    tex_name = tex_path.stem
    bib_candidate = tex_path.parent / f"{tex_name}.bib"
    if bib_candidate.exists():
        return bib_candidate.resolve()

    if tex_name == 'main':
        root = Path('.')
        for name in ('references.bib', 'bibliography.bib'):
            root_bib = root / name
            if root_bib.exists():
                return root_bib.resolve()
        others = sorted(p for p in root.glob('*.bib') if p.name not in
                        ('references.bib', 'bibliography.bib'))
        if others:
            return others[0].resolve()
    return None


# "/sections/" handling is specific to the original project layout,
# so the helpers operate relative to the current working directory.

def collect_all_tex_files() -> list[Path]:
    """Return every ``.tex`` file the script should inspect.

    The legacy script looked in ``sections/`` and the project root, so
    we preserve that behaviour here for compatibility.
    """
    tex_list: list[Path] = []
    sections_dir = Path('sections')
    if sections_dir.exists():
        tex_list.extend(sorted(sections_dir.glob('*.tex')))
    root_main = Path('main.tex')
    if root_main.exists():
        tex_list.append(root_main)
    return tex_list


def collect_all_bib_files() -> list[Path]:
    """Return every ``.bib`` file the script should process.

    Prefers the conventional names ``references.bib`` and ``bibliography.bib``
    at the root, then falls back to anything it can find.  Backup files are
    ignored.
    """
    bib_list: list[Path] = []
    sections_dir = Path('sections')
    if sections_dir.exists():
        bib_list.extend(sorted(sections_dir.glob('*.bib')))

    for name in ('references.bib', 'bibliography.bib'):
        path = Path(name)
        if path.exists():
            bib_list.append(path)

    if not bib_list:
        for path in sorted(Path('.').glob('*.bib')):
            if not path.name.endswith('.backup'):
                bib_list.append(path)

    return sorted(bib_list)


def extract_citations_from_tex(tex_file: Path) -> Set[str]:
    r"""Extract citation keys from a LaTeX source file.

    The implementation is intentionally simple; it looks for a handful of
    common ``\cite`` commands and splits comma-separated lists.  The returned
    keys are normalised with :func:`utils.normalize_unicode`.
    """
    try:
        with open(tex_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return set()

    # patterns defined at module level to keep behaviour consistent
    patterns = CITATION_PATTERNS

    citations: Set[str] = set()
    for pattern in patterns:
        for match in re.findall(pattern, content):
            keys = [k.strip() for k in match.split(',')]
            citations.update(keys)

    normalized: Set[str] = set()
    for k in citations:
        nk = utils.normalize_unicode(k)
        if nk:
            normalized.add(nk)
    return normalized


def update_tex_citations(tex_files: Iterable[Path],
                         key_mapping: Mapping[str, str]) -> None:
    """Rewrite citation keys in a collection of ``.tex`` files.

    ``key_mapping`` should map *normalized* old keys to new ones; the
    original case is preserved when possible.
    """
    if not key_mapping:
        return

    for tex_file in tex_files:
        try:
            with open(tex_file, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue

        original_content = content
        patterns = CITATION_PATTERNS

        def replace_citations(match):
            keys_str = match.group(1)
            keys = [k.strip() for k in keys_str.split(',')]
            updated_keys = []
            for key in keys:
                norm = utils.normalize_unicode(key)
                if norm in key_mapping:
                    updated_keys.append(key_mapping[norm])
                else:
                    updated_keys.append(key)
            # remove duplicates while preserving order
            seen = set()
            deduped = []
            for k in updated_keys:
                if k not in seen:
                    seen.add(k)
                    deduped.append(k)
            return match.group(0).replace(keys_str, ', '.join(deduped))

        for pattern in patterns:
            content = re.sub(pattern, replace_citations, content)

        if content != original_content:
            with open(tex_file, 'w', encoding='utf-8') as f:
                f.write(content)


def sanitize_citation_keys(bib_file: Path) -> Dict[str, str]:
    """Remove problematic characters from entry keys in *bib_file*.

    Returns a mapping from old normalized key to new key.  The file is
    rewritten in place if any changes are made.
    """
    bib_database = parse_bibtex_file(bib_file)
    if not bib_database:
        return {}

    modified = False
    key_mapping: Dict[str, str] = {}
    fixed_count = 0

    for entry in bib_database.entries:
        orig = entry.get('ID', '')
        original_key = utils.normalize_unicode(orig)
        if not original_key:
            continue
        sanitized_key = re.sub(r"[^A-Za-z0-9_:\-]+", "", original_key)
        if sanitized_key and sanitized_key != original_key:
            entry['ID'] = sanitized_key
            key_mapping[original_key] = sanitized_key
            fixed_count += 1
            modified = True

    if modified:
        write_bib_file(bib_file, bib_database)
    return key_mapping


def _generate_citation_key(entry: dict) -> str:
    """Build a key in AuthorYearJournalFirstTitleWord format from a BibTeX entry."""
    # last name of first author
    auth = entry.get('author', '')
    last = ''
    if auth:
        first_author = auth.split(' and ')[0].strip()
        if ',' in first_author:
            last = first_author.split(',')[0]
        else:
            last = first_author.split()[-1]
        last = re.sub(r"[^A-Za-z]", "", last)
    year = re.sub(r"[^0-9]", "", str(entry.get('year', '')))
    journal = entry.get('journal', '')
    jabr = ''
    if journal:
        jabr = ''.join(w[0] for w in journal.split() if w and w[0].isalpha())
    title = entry.get('title', '')
    firstword = ''
    if title:
        firstword = re.sub(r"[^A-Za-z0-9]", "", title.split()[0])
    key = f"{last}{year}{jabr}{firstword}"
    if key and not key[0].isalpha():
        key = f"k{key}"
    return key


def standardize_citation_keys(bib_file: Path) -> Dict[str, str]:
    """Assign canonical keys and rewrite the file.

    New keys follow the pattern: AuthorYearJournalFirstTitleWord.
    Collisions are avoided by appending a counter.
    Returns mapping from old normalized key to new key.
    """
    bib_database = parse_bibtex_file(bib_file)
    if not bib_database:
        return {}

    key_mapping: Dict[str, str] = {}
    used_keys: Set[str] = set()

    for entry in bib_database.entries:
        orig = entry.get('ID', '')
        norm = utils.normalize_unicode(orig)
        if not norm:
            continue
        new_key = _generate_citation_key(entry)
        if not new_key or new_key == norm:
            used_keys.add(norm)
            continue
        base = new_key
        i = 1
        while new_key in used_keys:
            new_key = f"{base}{i}"
            i += 1
        entry['ID'] = new_key
        key_mapping[norm] = new_key
        used_keys.add(new_key)

    if key_mapping:
        write_bib_file(bib_file, bib_database)
    return key_mapping
