#!/usr/bin/env python3
"""
Unified BibTeX Bibliography Management Script

This script combines validation and curation functionality for managing BibTeX
bibliography files in LaTeX projects. It provides comprehensive validation,
automatic cleanup, and formatting capabilities.

Features:
---------
Validation:
  - Validates all citations in .tex files exist in corresponding .bib files
  - Checks for duplicate entry keys across files
  - Detects duplicate DOIs with different keys
  - Validates BibTeX syntax
  - Checks for malformed author fields (incomplete names, malformed LaTeX)
  - Detects unescaped % characters that cause compilation errors
  - Verifies file correspondence between .tex and .bib files

Curation:
  - Updates BibTeX entries with latest metadata using betterbib
  - Formats entries consistently using bibfmt
  - Removes non-standard fields (file, urldate, langid, keywords, etc.)
  - Synchronizes duplicate entries across files to be identical
  - Consolidates duplicate DOIs by choosing the best key
  - Updates .tex files with consolidated citation keys
  - Creates backups before modification

Usage:
------
    python3 bibliography.py validate    # Only validate (read-only)
    python3 bibliography.py curate      # Only curate/cleanup
    python3 bibliography.py polish       # Validate, curate, then validate again (default)
    python3 bibliography.py --help      # Show detailed help

Examples:
---------
    # Full polish workflow (recommended)
    python3 bibliography.py polish

    # Only check for issues without modifying files
    python3 bibliography.py validate

    # Only cleanup without validation
    python3 bibliography.py curate --yes

    # Polish without creating backups
    python3 bibliography.py polish --no-backup --yes

Dependencies:
------------
    - betterbib: For updating entries with online metadata
    - bibfmt: For formatting BibTeX files
    - bibtexparser: For parsing and manipulating BibTeX files

Author:
-------
    Maintained for book chapter bibliography management.
"""

import subprocess
import sys
import shutil
from collections import defaultdict
import bibtexparser  # type: ignore
from bibtexparser.bparser import BibTexParser  # type: ignore
import re
import unicodedata
import argparse

# bring the new package into the legacy script (relative imports now that
# this module lives inside the package)
from . import BibFile  # type: ignore[attr-defined]
from . import core, utils, helpers

# helper shortcuts (imported for backwards compatibility)
get_bib_entries = helpers.get_bib_entries
get_corresponding_bib = helpers.get_corresponding_bib
collect_all_tex_files = helpers.collect_all_tex_files
collect_all_bib_files = helpers.collect_all_bib_files
extract_citations_from_tex = helpers.extract_citations_from_tex
update_tex_citations = helpers.update_tex_citations
sanitize_citation_keys = helpers.sanitize_citation_keys
standardize_citation_keys = helpers.standardize_citation_keys


# Non-standard fields to remove
FIELDS_TO_REMOVE = [
    'file',
    'urldate',
    'langid',
    'keywords',
    'abstract',
    'Bdsk-Url-1',
    'Bdsk-Url-2',
    'note',
    'annote',
    'comment',
    'timestamp',
    'date-added',
    'date-modified',
]


# ============================================================================
# Utility Functions
# ============================================================================



# ============================================================================
# BibTeX File I/O
# ============================================================================



# ============================================================================
# Curation Functions
# ============================================================================

def create_backup(bib_file):
    """Create a backup of the original file."""
    backup_path = bib_file.with_suffix('.bib.backup')
    shutil.copy2(bib_file, backup_path)
    print(f"  Created backup: {backup_path}")
    return backup_path


def update_with_betterbib(bib_file):
    """Update BibTeX entries using betterbib.
    
    Note: betterbib may sometimes fetch incorrect metadata. This function
    creates a backup before updating and validates that DOIs match after update.
    """
    print("  Updating entries with betterbib...")
    
    # Create a backup before betterbib update
    backup_path = bib_file.with_suffix('.bib.betterbib_backup')
    shutil.copy2(bib_file, backup_path)
    
    # Load entries before update to validate DOIs
    bib_database_before = core.parse_bibtex_file(bib_file)
    dois_before = {}
    if bib_database_before:
        for entry in bib_database_before.entries:
            key = entry.get('ID', '')
            doi = entry.get('doi', '') or entry.get('DOI', '')
            if key and doi:
                dois_before[key] = utils.normalize_doi(doi)
    
    try:
        # Use betterbib update with in-place modification
        result = subprocess.run(
            ['betterbib', 'update', '-i', str(bib_file)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        if result.returncode != 0:
            print(f"  Warning: betterbib update had issues: {result.stderr}")
            # Restore from backup if update failed
            shutil.copy2(backup_path, bib_file)
            return
        else:
            print("  betterbib update completed")
    except subprocess.TimeoutExpired:
        print("  Warning: betterbib update timed out")
        # Restore from backup
        shutil.copy2(backup_path, bib_file)
        return
    except Exception as e:
        print(f"  Warning: betterbib update failed: {e}")
        # Restore from backup
        shutil.copy2(backup_path, bib_file)
        return
    
    # Validate that betterbib didn't corrupt entries
    bib_database_after = core.parse_bibtex_file(bib_file)
    if bib_database_after and bib_database_before:
        # Check for suspicious changes: entries with same key but completely different content
        # This catches cases where betterbib fetched wrong metadata
        suspicious_changes = []
        entries_before = {e.get('ID', ''): e for e in bib_database_before.entries}
        
        for entry_after in bib_database_after.entries:
            key = entry_after.get('ID', '')
            if key in entries_before:
                entry_before = entries_before[key]
                # Check if title changed dramatically (might be wrong paper)
                title_before = str(entry_before.get('title', '')).lower()
                title_after = str(entry_after.get('title', '')).lower()

                # URL comparison can also catch cases where metadata jumps to a completely
                # unrelated page (bad DOI lookup etc.).
                url_before = str(entry_before.get('url', '')).lower()
                url_after = str(entry_after.get('url', '')).lower()

                # determine whether change is dramatic
                big_title_diff = False
                if title_before and title_after and title_before != title_after:
                    # Check if they share at least 2 significant words (to allow for minor updates)
                    words_before = set(w for w in title_before.split() if len(w) > 3)
                    words_after = set(w for w in title_after.split() if len(w) > 3)
                    common_words = words_before & words_after
                    if len(common_words) < 2:
                        big_title_diff = True

                doi_before = utils.normalize_doi(entry_before.get('doi', '') or entry_before.get('DOI', ''))
                doi_after = utils.normalize_doi(entry_after.get('doi', '') or entry_after.get('DOI', ''))

                big_doi_change = doi_before and doi_after and doi_before != doi_after

                big_url_change = False
                if url_after and url_before.lower() != url_after.lower():
                    # new URL or changed URL detected; treat as suspicious if title also changed
                    big_url_change = True

                # flag if any of the suspicious criteria hold
                if big_title_diff or big_doi_change or big_url_change:
                    suspicious_changes.append(key)
                    print(f"  Warning: Suspicious metadata change detected for {key}")
                    if big_title_diff:
                        print(f"    Title before: {title_before[:60]}...")
                        print(f"    Title after: {title_after[:60]}...")
                    if big_doi_change:
                        print(f"    DOI before: {doi_before}")
                        print(f"    DOI after: {doi_after}")
                    if big_url_change:
                        print(f"    URL before: {url_before}")
                        print(f"    URL after: {url_after}")
        
        if suspicious_changes:
            print(f"  Restoring {len(suspicious_changes)} entry/entries from backup due to suspicious changes")
            # Restore the entire file from backup
            shutil.copy2(backup_path, bib_file)
    
    # Clean up backup
    try:
        backup_path.unlink()
    except Exception:
        pass


# Month abbreviation to integer mapping
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


def uncomment_bibtex_entries(bib_file):
    """Uncomment BibTeX entries that were commented out by bibfmt.
    
    Sometimes bibfmt comments out entries with syntax errors. This function
    uncomments them and ensures proper syntax (e.g., adds missing commas, closing braces).
    Also handles entries that are missing closing braces.
    
    This function is more robust and handles various edge cases that cause bibfmt to comment entries.
    """
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0
    
    # Check if there are any commented entries
    if '@comment{' not in content:
        return 0
    
    lines = content.split('\n')
    
    # Find all @comment{@ lines
    comment_starts = []
    for i, line in enumerate(lines):
        if re.match(r'@comment\{@\w+\{', line):
            comment_starts.append(i)
    
    if not comment_starts:
        return 0
    
    fixed_count = 0
    modified = False
    # Process from end to beginning to maintain positions
    for idx in reversed(range(len(comment_starts))):
        start = comment_starts[idx]
        
        # Find where this entry ends - look for the closing }} of @comment{...}
        # or the next @entry (not commented)
        end = len(lines)
        brace_count = 0
        found_opening = False
        
        for j in range(start, min(len(lines), start + 200)):  # Limit search to prevent infinite loops
            line = lines[j]
            # Count braces to find the end of @comment{...}
            brace_count += line.count('{') - line.count('}')
            if '@comment{' in line:
                found_opening = True
            
            # If we've closed all braces from @comment{, we're done
            if found_opening and brace_count <= 0 and j > start:
                end = j + 1
                break
            
            # Also check for next @entry (not commented) as a fallback
            if j > start and re.match(r'@\w+\{', line) and not line.startswith('@comment'):
                end = j
                break
        
        # Get the entry lines
        entry_lines = lines[start:end]
        entry_text = '\n'.join(entry_lines)
        
        # Extract the entry key to identify it
        entry_key_match = re.search(r'@comment\{@\w+\{([^,}]+)', entry_text)
        if not entry_key_match:
            continue
        # NOTE: we previously captured the key to identify entries but the
        # script no longer uses it here; avoid unused-variable lint warning.
        # entry_key = entry_key_match.group(1).strip()
        
        # Remove @comment{ wrapper
        entry_content = re.sub(r'^@comment\{', '', entry_text, count=1, flags=re.MULTILINE)
        
        # Fix missing commas between fields (common cause of bibfmt commenting out entries)
        # Pattern: field value ends with } but next line starts with field name (no comma)
        # This is more aggressive - it looks for } followed by whitespace and a field name
        entry_content = re.sub(r'\}\s*\n\s*(\w+\s*=)', r'},\n  \1', entry_content)
        
        # Also fix cases where } is on the same line but missing comma
        entry_content = re.sub(r'\}\s+(\w+\s*=)', r'}, \1', entry_content)
        
        # Count braces in the cleaned entry
        open_braces = entry_content.count('{')
        close_braces = entry_content.count('}')
        missing_braces = open_braces - close_braces
        
        # Remove any trailing }} that closes @comment{ (keep only one })
        entry_content = entry_content.rstrip()
        # If we have }} at the end, remove one
        if entry_content.endswith('}}'):
            entry_content = entry_content[:-1]
            missing_braces = max(0, missing_braces - 1)
        
        # If entry is missing closing braces, add them
        if missing_braces > 0:
            entry_content = entry_content.rstrip()
            entry_content = entry_content + '\n' + '}' * missing_braces
        
        # Ensure entry ends with exactly one }
        entry_content = entry_content.rstrip()
        if not entry_content.endswith('}'):
            entry_content = entry_content + '\n}'
        elif entry_content.endswith('}}'):
            # Remove extra closing brace
            entry_content = entry_content[:-1]
        
        # Validate the entry can be parsed (basic check)
        # Count braces - should end with exactly one more } than {
        final_open = entry_content.count('{')
        final_close = entry_content.count('}')
        if final_open != final_close:
            # Try to balance
            diff = final_open - final_close
            if diff > 0:
                entry_content = entry_content.rstrip() + '\n' + '}' * diff
            elif diff < 0:
                # Too many closing braces - remove extras from end
                entry_content = entry_content.rstrip()
                for _ in range(-diff):
                    if entry_content.endswith('}'):
                        entry_content = entry_content[:-1].rstrip()
        
        # Replace the commented entry with uncommented version
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


def fix_invalid_utf8_bytes(bib_file):
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
    
    # Common problematic patterns:
    # - \xcc\x88 is combining diaeresis (U+0308) - should be \" in LaTeX
    # - \xcc\x81 is combining acute (U+0301) - should be \' in LaTeX
    # - \xc5\x9b is ś (U+015B) - should be \'{s} in LaTeX
    # - \xc5\x82 is ł (U+0142) - should be \l{} in LaTeX
    
    # Fix at byte level: look for backslash + backslash + combining mark pattern
    # Pattern: \\ followed by combining diaeresis (cc 88) or combining acute (cc 81)
    # We need to find: \\\xcc\x88 or \\\xcc\x81 in the raw bytes
    new_content = raw_content
    
    # Fix: Lo\\\xcc\x88c -> Lo\"c
    # Pattern: character + backslash backslash cc 88 (combining diaeresis)
    # Replace: X\\\xcc\x88 -> X\" (where X is the character before)
    # Use explicit bytes to avoid escape sequence issues
    pattern1 = bytes([0x5c, 0x5c, 0xcc, 0x88])  # \\\xcc\x88
    while pattern1 in new_content:
        pos = new_content.find(pattern1)
        if pos >= 1:
            prev_char = new_content[pos - 1:pos]
            # Replace: X\\\xcc\x88 -> X\"
            new_content = new_content[:pos-1] + prev_char + b'\\"' + new_content[pos+4:]
            fixed_count += 1
            modified = True
        else:
            # Pattern at start, just replace with \"
            new_content = new_content[:pos] + b'\\"' + new_content[pos+4:]
            fixed_count += 1
            modified = True
    
    # Fix: X\\\xcc\x81 -> X\'
    pattern2 = bytes([0x5c, 0x5c, 0xcc, 0x81])  # \\\xcc\x81
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
    
    # Fix: \\\xc5\x9b (ś) -> \'{s}
    pattern3 = bytes([0x5c, 0x5c, 0xc5, 0x9b])  # \\\xc5\x9b
    if pattern3 in new_content:
        count = new_content.count(pattern3)
        new_content = new_content.replace(pattern3, b"\\'{s}")
        fixed_count += count
        modified = True
    
    # Fix: \\\xc5\x82 (ł) -> \l{}
    pattern4 = bytes([0x5c, 0x5c, 0xc5, 0x82])  # \\\xc5\x82
    if pattern4 in new_content:
        count = new_content.count(pattern4)
        new_content = new_content.replace(pattern4, b"\\l{}")
        fixed_count += count
        modified = True
    
    if modified:
        try:
            # Decode and re-encode to ensure valid UTF-8
            content = new_content.decode('utf-8', errors='replace')
            # Remove any replacement characters that might have been introduced
            content = content.replace('\ufffd', '')
            
            with open(bib_file, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  Fixed {fixed_count} invalid UTF-8 byte sequence(s)")
            return fixed_count
        except Exception as e:
            print(f"  Error writing {bib_file}: {e}")
            return 0
    
    return 0


def fix_problematic_unicode(bib_file):
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
        # Skip comment lines (but not @comment{...} blocks)
        stripped = line.strip()
        if stripped.startswith('%') and not stripped.startswith('@comment'):
            continue
        
        new_line = line
        original_line = line
        
        # Fix U+2500 (─) box-drawing character - replace with regular dash
        if '\u2500' in new_line:
            new_line = new_line.replace('\u2500', '--')
            fixed_count += 1
            modified = True
        
        # Fix combining acute accent (U+0301)
        # This needs to be handled carefully - it combines with the previous character
        # Can appear as: á, ı́, or G\\b́or (after backslashes)
        if '\u0301' in new_line:
            # Use regex to find and replace: character + combining accent -> \'{character}
            # Pattern: any Unicode letter followed by combining acute accent
            def replace_accent(match):
                char = match.group(1)
                if char.isalpha():
                    return f"\\'{{{char}}}"
                return char
            
            # Match any Unicode alphabetic character followed by U+0301
            # \p{L} matches any Unicode letter, but Python re doesn't support it
            # So we use a character class that includes common letters
            # Match: letter (including Unicode) + U+0301
            new_line = re.sub(r'([^\W\d_])\u0301', replace_accent, new_line, flags=re.UNICODE)
            
            # Also handle cases where U+0301 appears after backslashes
            # Pattern: backslashes + letter + U+0301 -> backslashes + \'{letter}
            new_line = re.sub(r'((?:\\\\)*)([^\W\d_])\u0301', lambda m: m.group(1) + f"\\'{{{m.group(2)}}}", new_line, flags=re.UNICODE)
            
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


def fix_html_entities(bib_file):
    r"""Fix HTML entities in BibTeX fields.
    
    Converts HTML entities to LaTeX equivalents:
    - &amp; -> \&
    - &lt; -> <
    - &gt; -> >
    - &quot; -> "
    - &apos; -> '
    Also fixes unescaped & characters in title and journal fields that should be \&
    """
    try:
        with open(bib_file, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"  Error reading {bib_file}: {e}")
        return 0
    
    fixed_count = 0
    modified = False
    
    # HTML entity replacements
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
    
    # Fix unescaped & characters specifically in title and journal fields
    # Pattern: title = {...} or journal = {...} with unescaped & inside
    # We'll target these fields explicitly to avoid false positives
    
    # Pattern for title/journal fields with unescaped &
    # Matches: title = {text with &} or journal = {text with &}
    field_patterns = [
        (r'(title\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})', r'\1\\&\2'),
        (r'(journal\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})', r'\1\\&\2'),
        (r'(booktitle\s*=\s*\{[^}]*?)(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)([^}]*?\})', r'\1\\&\2'),
    ]
    
    for pattern, replacement in field_patterns:
        matches = list(re.finditer(pattern, content, re.IGNORECASE))
        if matches:
            # Process in reverse to maintain positions
            for match in reversed(matches):
                content = content[:match.start()] + match.expand(replacement) + content[match.end():]
                fixed_count += 1
                modified = True
    
    # Also fix unescaped & in other field values (more general approach)
    # Pattern: & that's not part of HTML entities and not already \&
    # Look for & that's not followed by amp;, lt;, gt;, quot;, apos; and not preceded by \
    unescaped_pattern = r'(?<!\\)&(?!amp;|lt;|gt;|quot;|apos;|\\&)'
    matches = list(re.finditer(unescaped_pattern, content))
    if matches:
        # Process in reverse to maintain positions
        for match in reversed(matches):
            # Check if we're in a field value (rough heuristic)
            pos = match.start()
            # Look backwards to see if we're inside braces
            before = content[:pos]
            open_braces = before.count('{')
            close_braces = before.count('}')
            if open_braces > close_braces:  # We're inside braces (field value)
                # Make sure we're not in a LaTeX command (e.g., \& is already correct)
                # Check if there's a backslash before this position
                if pos > 0 and content[pos-1] != '\\':
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
    


def fix_unescaped_percent(bib_file: BibFile):
    """Escape literal ``%`` characters in every field of a :class:`BibFile`.

    This version demonstrates the new core helpers.  A transform is defined with
    :func:`core.field_transform` and applied to the supplied object.  The
    function returns the number of fields that were changed; the caller can
    decide whether to write the file afterwards.
    """

    @core.field_transform
    def _escape(value):
        if not isinstance(value, str):
            return value
        new_value = value
        pos = 0
        changed = False
        while True:
            pos = new_value.find('%', pos)
            if pos == -1:
                break

            # count preceding backslashes
            backslash_count = 0
            check_pos = pos - 1
            while check_pos >= 0 and new_value[check_pos] == '\\':
                backslash_count += 1
                check_pos -= 1
            if backslash_count % 2 == 0:
                new_value = new_value[:pos] + '\\' + new_value[pos:]
                pos += 2  # skip the escaped sequence
                changed = True
            else:
                pos += 1
        return new_value if changed else value

    changed = _escape(bib_file)
    if changed:
        bib_file.write()
    return changed


def remove_accents_from_names(bib_file):
    """Remove accents from author names and other text fields to avoid special character issues.
    
    This function normalizes Unicode characters in author names and other text fields
    by removing diacritical marks, converting accented characters to their base forms.
    This helps prevent LaTeX compilation errors related to special characters.
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    
    fixed_count = 0
    modified = False
    
    # Fields that contain names or text that should have accents removed
    text_fields = ['author', 'editor', 'translator', 'title', 'booktitle', 'journal']
    
    for entry in bib_database.entries:
        for field in text_fields:
            if field in entry:
                original_value = entry[field]
                # Remove LaTeX accent commands and convert to plain text
                # First, handle LaTeX accent commands like \'{a}, \"{u}, etc.
                # We'll convert them to plain characters without accents
                value = original_value
                
                # Remove LaTeX accent commands and keep the base character
                # Pattern: \'{char}, \"{char}, \`{char}, \^{char}, \~{char}, \={char}, \.{char}, \u{char}, \v{char}, \H{char}, \c{char}
                accent_patterns = [
                    (r"\\'\{([^}]+)\}", r'\1'),  # \'{a} -> a
                    (r'\\"\{([^}]+)\}', r'\1'),   # \"{u} -> u
                    (r'\\`\{([^}]+)\}', r'\1'),  # \`{a} -> a
                    (r'\\\^{([^}]+)\}', r'\1'),  # \^{a} -> a
                    (r'\\~\{([^}]+)\}', r'\1'),  # \~{a} -> a
                    (r'\\=\{([^}]+)\}', r'\1'),  # \={a} -> a
                    (r'\\.\{([^}]+)\}', r'\1'),  # \.{a} -> a
                    (r'\\u\{([^}]+)\}', r'\1'),  # \u{a} -> a
                    (r'\\v\{([^}]+)\}', r'\1'),  # \v{s} -> s
                    (r'\\H\{([^}]+)\}', r'\1'),  # \H{o} -> o
                    (r'\\c\{([^}]+)\}', r'\1'),  # \c{c} -> c
                ]
                
                for pattern, replacement in accent_patterns:
                    value = re.sub(pattern, replacement, value)
                
                # Now normalize Unicode characters (remove combining marks)
                # Convert to NFD (decomposed form) and remove combining marks
                value_normalized = unicodedata.normalize('NFD', value)
                value_no_accents = ''.join(
                    char for char in value_normalized
                    if unicodedata.category(char) != 'Mn'  # Mn = Nonspacing Mark (accents)
                )
                
                # Convert back to NFC (composed form) for better compatibility
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


def fix_legacy_year_fields(bib_file):
    """Fix legacy year fields that contain dates instead of just the year.
    
    Biblatex expects year fields to be integers (e.g., 2023) for proper sorting.
    This function extracts the year from date-formatted fields like '2023-04-19'
    and converts them to just the year (e.g., '2023').
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    
    fixed_count = 0
    
    for entry in bib_database.entries:
        # Check for year field (case-insensitive)
        year_keys = ['year', 'Year', 'YEAR']
        year_value = None
        year_key = None
        
        for key in year_keys:
            if key in entry:
                year_value = entry[key]
                year_key = key
                break
        
        if year_value:
            # Remove braces and whitespace
            year_clean = str(year_value).strip().strip('{}')
            
            # Check if it's already just an integer
            try:
                int(year_clean)
                continue  # Already a simple integer, skip
            except ValueError:
                pass
            
            # Check if it's a date format (YYYY-MM-DD or YYYY/MM/DD)
            import re
            date_match = re.match(r'^(\d{4})[-/]', year_clean)
            if date_match:
                # Extract just the year
                year_only = date_match.group(1)
                entry[year_key] = year_only
                fixed_count += 1
    
    if fixed_count > 0:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} legacy year field(s)")
    
    return fixed_count


def fix_legacy_month_fields(bib_file):
    """Fix legacy month fields by converting abbreviations to integers.
    
    Biblatex prefers integer month fields (1-12) for proper sorting.
    This function converts month abbreviations like 'apr' to '4'.
    """
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return 0
    
    fixed_count = 0
    
    for entry in bib_database.entries:
        # Check for month field (case-insensitive)
        month_keys = ['month', 'Month', 'MONTH']
        month_value = None
        month_key = None
        
        for key in month_keys:
            if key in entry:
                month_value = entry[key]
                month_key = key
                break
        
        if month_value:
            # Remove braces and whitespace, convert to lowercase
            month_clean = str(month_value).strip().strip('{}').lower()
            
            # Check if it's already an integer
            try:
                int(month_clean)
                continue  # Already an integer, skip
            except ValueError:
                pass
            
            # Check if it's a month abbreviation
            if month_clean in MONTH_MAP:
                entry[month_key] = MONTH_MAP[month_clean]
                fixed_count += 1
    
    if fixed_count > 0:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} legacy month field(s)")
    
    return fixed_count


def format_with_bibfmt(bib_file):
    """Format BibTeX file using bibfmt and remove non-standard fields."""
    print("  Formatting with bibfmt and removing non-standard fields...")

    # Build bibfmt command with field removal
    cmd = ['bibfmt', '-i', '--indent', '2', '--align', '14', '-d', 'braces']

    # Add --drop for each field to remove
    for field in FIELDS_TO_REMOVE:
        cmd.extend(['--drop', field])

    cmd.append(str(bib_file))

    try:
        # before/after comparison for suspicious metadata edits
        before_text = None
        try:
            before_text = bib_file.read_text(encoding='utf-8')
        except Exception:
            before_text = None

        result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
        if result.returncode != 0:
            print(f"  Warning: bibfmt had issues: {result.stderr}")
        else:
            print("  bibfmt formatting completed")

        # if the file content changed dramatically (unlikely) warn user
        if before_text is not None:
            try:
                after_text = bib_file.read_text(encoding='utf-8')
                if before_text != after_text:
                    # parse both and compare entries for big differences
                    parser = BibTexParser()
                    db_before = bibtexparser.loads(before_text, parser=parser)
                    db_after = bibtexparser.loads(after_text, parser=parser)
                    for entry_after in db_after.entries:
                        key = entry_after.get('ID', '')
                        match = next((e for e in db_before.entries if e.get('ID','')==key), None)
                        if match:
                            title_before = str(match.get('title','')).lower()
                            title_after = str(entry_after.get('title','')).lower()
                            doi_before = utils.normalize_doi(match.get('doi','') or match.get('DOI',''))
                            doi_after = utils.normalize_doi(entry_after.get('doi','') or entry_after.get('DOI',''))
                            url_before = str(match.get('url','')).lower()
                            url_after = str(entry_after.get('url','')).lower()
                            # simple heuristic: warn if title changed and no common words
                            if title_before and title_after and title_before != title_after:
                                words_before = set(w for w in title_before.split() if len(w)>3)
                                words_after = set(w for w in title_after.split() if len(w)>3)
                                if len(words_before & words_after) < 2:
                                    print(f"  Warning: bibfmt appears to have altered title for {key}")
                            if doi_before and doi_after and doi_before != doi_after:
                                print(f"  Warning: bibfmt changed DOI for {key} ({doi_before} → {doi_after})")
                            if url_before.lower() != url_after.lower() and url_after:
                                print(f"  Warning: bibfmt changed URL for {key} ({url_before} → {url_after})")
            except Exception:
                pass
    except Exception as e:
        print(f"  Warning: bibfmt failed: {e}")


def find_duplicates(bib_files):
    """Find duplicate entries across all BibTeX files."""
    print("\nFinding duplicate entries across files...")
    entries_by_key = defaultdict(list)
    
    for bib_file in bib_files:
        bib_database = core.parse_bibtex_file(bib_file)
        if bib_database:
            for entry in bib_database.entries:
                key = entry['ID']
                entries_by_key[key].append((bib_file, entry))
    
    duplicates = {k: v for k, v in entries_by_key.items() if len(v) > 1}
    print(f"  Found {len(duplicates)} entries that appear in multiple files")
    
    return duplicates


def choose_best_entry(entries):
    """Choose the best entry from multiple versions."""
    # Score entries based on completeness
    def score_entry(entry):
        score = 0
        important_fields = ['title', 'author', 'year', 'journal', 'doi', 'pages', 'volume']
        for field in important_fields:
            if field in entry and entry[field]:
                score += 1
        # Prefer entries with more fields
        score += len(entry) * 0.1
        return score
    
    # Sort by score (highest first)
    sorted_entries = sorted(entries, key=lambda x: score_entry(x[1]), reverse=True)
    return sorted_entries[0][1]  # Return the best entry


def synchronize_duplicates(bib_files, duplicates):
    """Synchronize duplicate entries to be identical across files."""
    print("\nSynchronizing duplicate entries...")
    
    # Load all files
    file_databases = {}
    for bib_file in bib_files:
        file_databases[bib_file] = core.parse_bibtex_file(bib_file)
    
    # For each duplicate, choose the best version and apply to all files
    for key, entries in duplicates.items():
        best_entry = choose_best_entry(entries)
        print(f"  Synchronizing '{key}' across {len(entries)} files")
        
        # Update all occurrences
        for bib_file, _ in entries:
            bib_database = file_databases[bib_file]
            if bib_database:
                # Find and replace the entry
                for i, entry in enumerate(bib_database.entries):
                    if entry['ID'] == key:
                        # Create a copy of the best entry with the same ID
                        new_entry = best_entry.copy()
                        new_entry['ID'] = key
                        bib_database.entries[i] = new_entry
                        break
    
    # Write all files back
    for bib_file, bib_database in file_databases.items():
        if bib_database:
            core.write_bib_file(bib_file, bib_database)
            print(f"  Updated {bib_file}")


def find_duplicate_dois(bib_files):
    """Find duplicate entries by DOI with different keys.
    
    Returns ALL duplicate DOIs, regardless of whether content is identical.
    This allows consolidation even when entries differ slightly (formatting, missing fields, etc.).
    """
    print("\nFinding duplicate DOIs with different keys...")
    doi_to_entries = defaultdict(list)
    
    for bib_file in bib_files:
        bib_database = core.parse_bibtex_file(bib_file)
        if bib_database:
            for entry in bib_database.entries:
                key = utils.normalize_unicode(entry.get('ID', ''))
                doi = entry.get('doi') or entry.get('DOI') or entry.get('Doi')
                normalized_doi = utils.normalize_doi(doi)
                
                if normalized_doi:
                    doi_to_entries[normalized_doi].append({
                        'key': key,
                        'file': bib_file,
                        'entry': entry
                    })
    
    # Find duplicates with different keys (regardless of content differences)
    duplicates = {}
    for doi, entries_list in doi_to_entries.items():
        if len(entries_list) > 1:
            keys = set(e['key'] for e in entries_list)
            if len(keys) > 1:
                # Different keys for same DOI - include ALL of them for consolidation
                duplicates[doi] = entries_list
    
    print(f"  Found {len(duplicates)} DOIs with different keys (will consolidate to best entry)")
    return duplicates


def choose_best_key(entries_list):
    """Choose the best key from a list of entries with the same DOI.
    
    Prefers:
    1. Keys with standard naming (AuthorYear format)
    2. Keys with proper capitalization
    3. Shorter keys (if similar quality)
    """
    def score_key(key):
        score = 0
        key_str = str(key)
        
        # Prefer keys that start with capital letter
        if key_str and key_str[0].isupper():
            score += 10
        
        # Prefer keys that look like AuthorYear format (e.g., "Smith2020")
        if re.match(r'^[A-Z][a-z]+\d{4}', key_str):
            score += 20
        
        # Prefer keys without underscores (more standard)
        if '_' not in key_str:
            score += 5
        
        # Prefer shorter keys (if similar quality)
        score -= len(key_str) * 0.1
        
        return score
    
    # Get all unique keys
    keys = [e['key'] for e in entries_list]
    unique_keys = list(set(keys))
    
    # Score and sort
    scored_keys = [(key, score_key(key)) for key in unique_keys]
    scored_keys.sort(key=lambda x: x[1], reverse=True)
    
    return scored_keys[0][0]  # Return best key


def consolidate_duplicate_dois(bib_files, duplicates):
    """Consolidate duplicate DOIs by choosing the best key and best entry, updating all references.
    
    For each duplicate DOI:
    1. Chooses the best key (most standard naming)
    2. Chooses the best entry (most complete)
    3. Updates all entries to use the best key and best entry content
    4. Removes duplicate entries
    5. Returns key mapping for updating .tex files
    """
    if not duplicates:
        return {}
    
    print("\nConsolidating duplicate DOIs...")
    
    # Map old keys to new keys
    key_mapping = {}
    
    # Load all files
    file_databases = {}
    for bib_file in bib_files:
        file_databases[bib_file] = core.parse_bibtex_file(bib_file)
    
    # Process each duplicate DOI
    for doi, entries_list in duplicates.items():
        best_key = choose_best_key(entries_list)
        
        # Choose the best entry (most complete)
        # Convert entries_list format to format expected by choose_best_entry
        entries_for_best = [(entry_info['file'], entry_info['entry']) for entry_info in entries_list]
        best_entry = choose_best_entry(entries_for_best)
        best_entry['ID'] = best_key  # Ensure ID matches best key
        
        print(f"  DOI {doi}:")
        print(f"    Keys: {', '.join(set(e['key'] for e in entries_list))}")
        print(f"    → Consolidating to: {best_key}")
        
        # Map all old keys to the best key
        for entry_info in entries_list:
            old_key = entry_info['key']
            if old_key != best_key:
                key_mapping[old_key] = best_key
        
        # Track which files already have the best key entry
        files_with_best_key = set()
        files_to_process = set(entry_info['file'] for entry_info in entries_list)
        
        # Process each file that contains one of these entries
        for bib_file in files_to_process:
            bib_database = file_databases.get(bib_file)
            if not bib_database:
                continue
            
            # Check if we already have an entry with the best key in this file
            has_best_key = False
            for entry in bib_database.entries:
                entry_key = utils.normalize_unicode(entry.get('ID', ''))
                if entry_key == best_key:
                    # Update existing best key entry with best content
                    new_entry = best_entry.copy()
                    for i, e in enumerate(bib_database.entries):
                        if utils.normalize_unicode(e.get('ID', '')) == best_key:
                            bib_database.entries[i] = new_entry
                            break
                    has_best_key = True
                    files_with_best_key.add(bib_file)
                    break
            
            # Find and remove/update entries with old keys
            entries_to_remove = []
            for i, entry in enumerate(bib_database.entries):
                entry_key = utils.normalize_unicode(entry.get('ID', ''))
                # Check if this entry has one of the old keys
                for entry_info in entries_list:
                    old_key = entry_info['key']
                    if entry_key == old_key and old_key != best_key:
                        if has_best_key:
                            # Remove old entry - we already have best key entry
                            entries_to_remove.append(i)
                        else:
                            # Replace old entry with best entry
                            new_entry = best_entry.copy()
                            bib_database.entries[i] = new_entry
                            files_with_best_key.add(bib_file)
                            has_best_key = True
                        break
            
            # Remove duplicate entries (in reverse order to maintain indices)
            for i in sorted(entries_to_remove, reverse=True):
                del bib_database.entries[i]
    
    # Write all files back
    for bib_file, bib_database in file_databases.items():
        if bib_database:
            core.write_bib_file(bib_file, bib_database)
    
    print(f"\n  Consolidated {len(duplicates)} duplicate DOIs")
    print(f"  Created {len(key_mapping)} key mappings")
    
    return key_mapping


def process_bib_file(bib_file, create_backups=True):
    """Process a single BibTeX file."""
    print(f"\nProcessing {bib_file.name}...")
    
    if create_backups:
        create_backup(bib_file)
    
    # Step 1: Update with betterbib
    update_with_betterbib(bib_file)
    
    # Step 2: Fix invalid UTF-8 byte sequences (before other fixes)
    print("  Fixing invalid UTF-8 byte sequences...")
    fix_invalid_utf8_bytes(bib_file)
    
    # Step 3: Fix HTML entities (before other fixes)
    print("  Fixing HTML entities...")
    fix_html_entities(bib_file)
    
    # Step 4: Fix malformed author fields (before accent removal)
    print("  Fixing malformed author fields...")
    fix_malformed_author_fields(bib_file)
    
    # Step 5: Remove accents from names (before other Unicode fixes)
    print("  Removing accents from names...")
    remove_accents_from_names(bib_file)
    
    # Step 7: Sanitize citation keys (remove special characters)
    # Note: This is done per-file, but key mappings are collected in Step 2 of curation
    # We skip it here to avoid double-processing
    # print("  Sanitizing citation keys...")
    # sanitize_citation_keys(bib_file)
    
    # Step 8: Fix problematic Unicode characters (before bibfmt to prevent issues)
    print("  Fixing problematic Unicode characters...")
    fix_problematic_unicode(bib_file)
    
    # Step 9: Fix unescaped % characters (before bibfmt to prevent issues)
    print("  Fixing unescaped % characters...")
    bf = BibFile(bib_file)
    fix_unescaped_percent(bf)
    
    # Step 10: Format and remove non-standard fields with bibfmt
    format_with_bibfmt(bib_file)
    
    # Step 11: Uncomment any entries that bibfmt commented out due to syntax errors
    print("  Checking for commented entries...")
    uncomment_bibtex_entries(bib_file)
    
    # Step 12: Fix legacy year fields (extract year from date-formatted fields)
    print("  Fixing legacy year fields...")
    fix_legacy_year_fields(bib_file)
    
    # Step 13: Fix legacy month fields (after bibfmt, as bibfmt may convert them)
    print("  Fixing legacy month fields...")
    fix_legacy_month_fields(bib_file)
    
    print(f"  Completed processing {bib_file.name}")


def curate_bibliography(bib_files, create_backups=True, preserve_keys=False):
    """Main curation function.

    Args:
        bib_files (list[Path]): list of bib files to process.
        create_backups (bool): whether to create backup copies before modifying.
        preserve_keys (bool): if True, skip any operations that would change
            citation keys (sanitization, DOI consolidation, and updates to
            .tex files). This is useful when you want to polish the database
            without altering existing labels.
    """
    print("=" * 70)
    print("BibTeX Curation")
    print("=" * 70)
    
    # Collect before stats
    print("\nCollecting baseline statistics...")
    before_stats = {}
    for bib_file in bib_files:
        stats = validate_bib_file(bib_file)
        if stats:
            before_stats[bib_file.name] = stats
    
    # Step 1: Process each file individually
    print("\n" + "=" * 70)
    print("Step 1: Processing individual files")
    print("=" * 70)
    
    for bib_file in bib_files:
        process_bib_file(bib_file, create_backups=create_backups)
    
    if not preserve_keys:
        # Step 2: Sanitize all citation keys (remove special characters)
        print("\n" + "=" * 70)
        print("Step 2: Sanitizing citation keys (removing special characters)")
        print("=" * 70)
        
        all_key_mappings = {}  # Collect all key mappings from all files
        for bib_file in bib_files:
            key_mapping = sanitize_citation_keys(bib_file)
            if key_mapping:
                all_key_mappings.update(key_mapping)

        # Step 2a: Standardize citation keys (generate canonical labels)
        # This step only runs if we have a main.tex file to update; otherwise
        # keys would change without any corresponding citation updates.
        tex_files = collect_all_tex_files()
        if any(tf.name == 'main.tex' for tf in tex_files):
            print("\n" + "=" * 70)
            print("Step 2a: Standardizing citation keys")
            print("=" * 70)
            for bib_file in bib_files:
                key_mapping = standardize_citation_keys(bib_file)
                if key_mapping:
                    all_key_mappings.update(key_mapping)
        else:
            print("\nSkipping citation key standardization (no main.tex found)")

        # Step 3: Update .tex files with sanitized/standardized keys
        if all_key_mappings:
            print("\n" + "=" * 70)
            print("Step 3: Updating .tex files with sanitized keys")
            print("=" * 70)
            
            tex_files = collect_all_tex_files()
            update_tex_citations(tex_files, all_key_mappings)
        else:
            print("\n" + "=" * 70)
            print("Step 3: No key sanitization needed")
            print("=" * 70)
    else:
        print("\n" + "Skipping key sanitization and updates (--preserve-keys)")
        all_key_mappings = {}
    
    # Step 4: Remove unused entries (not referenced in any .tex)
    print("\n" + "=" * 70)
    print("Step 4: Removing unused entries")
    print("=" * 70)
    unused_removed = remove_unused_entries(bib_files)
    if unused_removed == 0:
        print("  No unused entries found.")
    
    # Step 5: Remove duplicate entries across files
    print("\n" + "=" * 70)
    print("Step 5: Removing duplicate entries across files")
    print("=" * 70)
    
    removed = remove_duplicate_entries_across_files(bib_files)
    if removed == 0:
        print("  No duplicate entries to remove.")
    
    # Step 6: Find and synchronize remaining duplicates (same key, same file)
    print("\n" + "=" * 70)
    print("Step 6: Synchronizing duplicate entries")
    print("=" * 70)
    
    duplicates = find_duplicates(bib_files)
    if duplicates:
        synchronize_duplicates(bib_files, duplicates)
    else:
        print("  No duplicates found.")
    
    if not preserve_keys:
        # Step 6: Consolidate duplicate DOIs
        print("\n" + "=" * 70)
        print("Step 6: Consolidating duplicate DOIs")
        print("=" * 70)
        
        duplicate_dois = find_duplicate_dois(bib_files)
        doi_key_mapping = {}
        if duplicate_dois:
            doi_key_mapping = consolidate_duplicate_dois(bib_files, duplicate_dois)
        else:
            print("  No duplicate DOIs found.")
        
        # Step 7: Update .tex files with consolidated DOI keys
        if doi_key_mapping:
            print("\n" + "=" * 70)
            print("Step 7: Updating .tex files with consolidated DOI keys")
            print("=" * 70)
            
            tex_files = collect_all_tex_files()
            update_tex_citations(tex_files, doi_key_mapping)
        else:
            print("\n" + "=" * 70)
            print("Step 7: Updating .tex files (skipped - no DOI key changes)")
            print("=" * 70)
    else:
        print("\nSkipping DOI consolidation (--preserve-keys)")
        doi_key_mapping = {}

    # Step 8: Consolidate duplicate titles (after DOI consolidation)
    if not preserve_keys:
        print("\n" + "=" * 70)
        print("Step 8: Consolidating duplicate titles")
        print("=" * 70)
        title_key_mapping = consolidate_duplicate_titles(bib_files)
        if title_key_mapping:
            tex_files = collect_all_tex_files()
            update_tex_citations(tex_files, title_key_mapping)
        else:
            print("  No duplicate titles to consolidate.")
    else:
        print("\nSkipping title consolidation (--preserve-keys)")
        title_key_mapping = {}

    # Step 6: Final formatting pass and cleanup
    # CRITICAL ORDER: This order ensures LaTeX compilation will succeed
    # 1. bibfmt formats entries (may revert month/year fixes)
    # 2. Uncomment entries (bibfmt may comment out entries with errors)
    # 3. Fix invalid UTF-8 bytes (must be before any parsing/compilation)
    # 4. Fix problematic Unicode (U+2500, U+0301 -> LaTeX commands)
    # 5. Fix unescaped % (prevents LaTeX comment errors)
    # 6. Fix legacy year fields (bibfmt may introduce date-formatted years like 2023-04-19)
    # 7. Fix legacy month fields (bibfmt converts integers back to abbreviations like 'apr')
    #
    # Result: All months are integers (1-12), all years are integers (not dates),
    #         all DOIs are proper (from betterbib), no problematic characters
    print("\n" + "=" * 70)
    print("Step 5: Final formatting pass and cleanup")
    print("=" * 70)
    print("Ensuring all fields are properly formatted for LaTeX compilation...")
    
    for bib_file in bib_files:
        # 1. Format with bibfmt (may revert some fixes, so we fix again after)
        format_with_bibfmt(bib_file)
        
        # 2. Uncomment any entries that got commented out (must be before other fixes)
        uncomment_bibtex_entries(bib_file)
        
        # 3. Fix invalid UTF-8 bytes (critical - must be before parsing)
        fix_invalid_utf8_bytes(bib_file)
        
        # 4. Fix HTML entities (before other character fixes)
        fix_html_entities(bib_file)
        
        # 5. Fix malformed author fields (before other character fixes)
        fix_malformed_author_fields(bib_file)
        
        # 6. Fix problematic Unicode characters (before other character fixes)
        fix_problematic_unicode(bib_file)
        
        # 7. Fix unescaped % characters (critical for LaTeX compilation)
        bf = BibFile(bib_file)
        fix_unescaped_percent(bf)
        
        # 8. Fix legacy year fields (bibfmt may introduce date-formatted years)
        fix_legacy_year_fields(bib_file)
        
        # 9. Fix legacy month fields (bibfmt converts integers back to abbreviations)
        fix_legacy_month_fields(bib_file)
        
        # 10. Final uncomment pass - bibfmt may have commented entries again
        uncomment_bibtex_entries(bib_file)
        
        print(f"  ✓ {bib_file.name}: All fixes applied")
    
    # Step 9: Final validation to ensure everything is correct
    print("\n" + "=" * 70)
    print("Step 7: Final validation")
    print("=" * 70)
    
    validation_issues = []
    for bib_file in bib_files:
        issues = []
        try:
            with open(bib_file, 'r', encoding='utf-8') as f:
                parser = BibTexParser()
                db = bibtexparser.load(f, parser=parser)
                
                for entry in db.entries:
                    # Check years are integers
                    if 'year' in entry:
                        year_val = str(entry['year']).strip().strip('{}')
                        if '-' in year_val or '/' in year_val:
                            issues.append(f"Date-formatted year in {entry.get('ID', 'unknown')}: {year_val}")
                    
                    # Check months are integers
                    if 'month' in entry:
                        month_val = str(entry['month']).strip().strip('{}').lower()
                        if month_val in ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']:
                            issues.append(f"Abbreviated month in {entry.get('ID', 'unknown')}: {month_val}")
                    
                    # Check DOIs are properly formatted
                    if 'doi' in entry:
                        doi_val = str(entry['doi']).strip().strip('{}')
                        if doi_val and not doi_val.startswith('10.'):
                            issues.append(f"Invalid DOI in {entry.get('ID', 'unknown')}: {doi_val[:50]}")
        except Exception as e:
            issues.append(f"Parse error: {e}")
        
        if issues:
            validation_issues.extend([(bib_file.name, issue) for issue in issues])
        else:
            print(f"  ✓ {bib_file.name}: All fields properly formatted")
    
    if validation_issues:
        print(f"\n  ⚠ Found {len(validation_issues)} validation issues:")
        for file_name, issue in validation_issues[:10]:
            print(f"    {file_name}: {issue}")
        if len(validation_issues) > 10:
            print(f"    ... and {len(validation_issues) - 10} more")
    else:
        print("\n  ✓ All files validated: months and years are integers, DOIs are proper")
    
    # Step 7: Validation and reporting
    generate_report(bib_files, before_stats=before_stats)
    
    print("\n" + "=" * 70)
    print("Curation complete!")
    print("=" * 70)
    print(f"\nProcessed {len(bib_files)} files")
    if create_backups:
        print("Backups created with .backup extension")
    print("\nReview the changes and remove .backup files when satisfied.")


# ============================================================================
# Validation Helpers (migrated to bibliography/helpers.py)
# ============================================================================
# The implementations of file discovery, citation extraction and key
# sanitisation live in :mod:`bibliography.helpers` and are imported at the top
# of this script.  They are exercised by the unit tests in ``tests/test_helpers.py``.


def validate_citations():
    """Validate that all citations in .tex files exist in corresponding .bib files.
    
    Also checks:
    - If cited entries are commented out
    - If crossref entries exist
    """
    tex_files = collect_all_tex_files()
    bib_files = collect_all_bib_files()
    
    print("=" * 80)
    print("1. CITATION VALIDATION")
    print("=" * 80)
    print()
    
    all_issues = []
    total_citations = 0
    total_valid = 0
    
    # Get all entries from all bib files (for cross-file citations)
    all_bib_entries = set()
    commented_entries = set()
    crossrefs = {}  # entry -> crossref value
    
    for bib_file in bib_files:
        if bib_file.name.endswith('.backup'):
            continue
        entries = core.parse_bib_file(bib_file)
        for entry in entries:
            key = utils.normalize_unicode(entry.get('ID', ''))
            if key:
                all_bib_entries.add(key)
                # Check for crossref
                crossref = entry.get('crossref', '') or entry.get('Crossref', '')
                if crossref:
                    crossrefs[key] = utils.normalize_unicode(crossref)
        
        # Check for commented entries
        try:
            with open(bib_file, 'r', encoding='utf-8') as f:
                content = f.read()
                # Find commented entries
                import re
                # Match @comment{@entrytype{key, ...}}
                comment_pattern = r'@comment\s*\{@\w+\{([^,}]+)'
                for match in re.finditer(comment_pattern, content):
                    commented_key = match.group(1).strip()
                    commented_entries.add(utils.normalize_unicode(commented_key))
        except Exception:
            pass
    
    for tex_file in tex_files:
        bib_file = get_corresponding_bib(tex_file)
        if not bib_file:
            print(f"❌ {tex_file.name}: No corresponding .bib file found")
            all_issues.append(f"{tex_file.name}: No .bib file")
            continue
        
        citations = extract_citations_from_tex(tex_file)
        bib_entries = get_bib_entries(bib_file)
        
        total_citations += len(citations)
        missing = citations - bib_entries - all_bib_entries  # Check all files
        
        # Check for commented entries
        commented_citations = []
        for citation in citations:
            if utils.normalize_unicode(citation) in commented_entries:
                commented_citations.append(citation)
        
        if missing:
            print(f"❌ {tex_file.name}: {len(missing)} missing citations")
            for key in sorted(missing):
                print(f"     - {key}")
                all_issues.append(f"{tex_file.name}: Missing {key}")
        
        if commented_citations:
            print(f"⚠️  {tex_file.name}: {len(commented_citations)} cited entries are commented out")
            for key in sorted(commented_citations):
                print(f"     - {key} (commented out in .bib file)")
                all_issues.append(f"{tex_file.name}: Commented {key}")
        
        if not missing and not commented_citations:
            print(f"✓ {tex_file.name}: All {len(citations)} citations valid")
            total_valid += len(citations)
    
    # Check crossrefs
    missing_crossrefs = []
    for entry_key, crossref_key in crossrefs.items():
        if crossref_key not in all_bib_entries:
            missing_crossrefs.append((entry_key, crossref_key))
    
    if missing_crossrefs:
        print(f"\n⚠️  Found {len(missing_crossrefs)} entries with missing crossrefs:")
        for entry_key, crossref_key in sorted(missing_crossrefs):
            print(f"     - {entry_key} → crossref '{crossref_key}' (not found)")
            all_issues.append(f"Missing crossref: {entry_key} → {crossref_key}")
    
    print(f"\nSummary: {total_valid}/{total_citations} citations valid across all files")
    return all_issues


def remove_duplicate_entries_across_files(bib_files):
    """Remove duplicate entries across bib files, keeping one copy.

    For each duplicate key found across multiple files, keeps the entry
    in the first file (alphabetically) and removes it from other files.
    This prevents duplicate entry errors during LaTeX compilation.
    """
    print("\nRemoving duplicate entries across files...")

    # Find all duplicate keys
    key_to_files = defaultdict(list)
    file_to_entries = {}

    for bib_file in bib_files:
        bib_database = core.parse_bibtex_file(bib_file)
        if not bib_database:
            continue

        file_to_entries[bib_file] = bib_database

        for entry in bib_database.entries:
            key = entry.get('ID', '')
            if key:
                key_to_files[key].append((bib_file, entry))

    # Find duplicates
    duplicates = {key: files for key, files in key_to_files.items() if len(files) > 1}

    if not duplicates:
        print("  No duplicate entries found across files")
        return 0

    print(f"  Found {len(duplicates)} duplicate entry keys")

    # For each duplicate, keep in first file (alphabetically), remove from others
    removed_count = 0
    files_to_update = set()

    for key, file_entries in sorted(duplicates.items()):
        # Sort files alphabetically - keep in first file
        file_entries_sorted = sorted(file_entries, key=lambda x: x[0].name)
        keep_file, keep_entry = file_entries_sorted[0]
        remove_files = [f for f, e in file_entries_sorted[1:]]

        # Remove from other files
        for remove_file in remove_files:
            bib_database = file_to_entries[remove_file]
            entries_to_remove = []
            for i, entry in enumerate(bib_database.entries):
                if entry.get('ID', '') == key:
                    entries_to_remove.append(i)

            # Remove in reverse order to maintain indices
            for i in sorted(entries_to_remove, reverse=True):
                del bib_database.entries[i]
                removed_count += 1
                files_to_update.add(remove_file)

        print(f"    {key}: kept in {keep_file.name}, removed from {len(remove_files)} file(s)")

    # Write updated files
    for bib_file in files_to_update:
        core.write_bib_file(bib_file, file_to_entries[bib_file])

    if removed_count > 0:
        print(f"\n  Removed {removed_count} duplicate entry/entries")
        return removed_count

    return 0


def remove_unused_entries(bib_files):
    """Purge entries that are not cited in any .tex source.

    Crossref targets are treated as used so that automatically generated
    parent entries are not removed.
    """
    print("\nRemoving unused entries...")

    # gather citations from tex files
    tex_files = collect_all_tex_files()
    cited = set()
    for tex in tex_files:
        cited.update(extract_citations_from_tex(tex))

    # collect crossref targets so they are preserved
    crossrefs = set()
    for bib_file in bib_files:
        bib_db = core.parse_bibtex_file(bib_file)
        if not bib_db:
            continue
        for entry in bib_db.entries:
            cr = entry.get('crossref') or entry.get('Crossref')
            if cr:
                crossrefs.add(utils.normalize_unicode(cr))
    cited |= crossrefs

    removed_count = 0
    for bib_file in bib_files:
        bib_db = core.parse_bibtex_file(bib_file)
        if not bib_db:
            continue
        to_remove = []
        for i, entry in enumerate(bib_db.entries):
            key = utils.normalize_unicode(entry.get('ID', ''))
            if key and key not in cited:
                to_remove.append(i)
        for i in sorted(to_remove, reverse=True):
            del bib_db.entries[i]
            removed_count += 1
        if to_remove:
            core.write_bib_file(bib_file, bib_db)
            print(f"  {bib_file.name}: removed {len(to_remove)} unused entries")

    print(f"  Total unused entries removed: {removed_count}")
    return removed_count


def consolidate_duplicate_titles(bib_files):
    """Detect and consolidate entries that share the same title.

    Titles are compared using :func:`_normalize_title` so that differences in
    case, punctuation or braces do not prevent matching.  When duplicates are
    found the "best" entry is chosen (using :func:`choose_best_entry`) and all
    other keys are mapped to it; the inferior entries are removed.  A mapping
    of old keys to the chosen key is returned for updating citations in
    .tex sources.
    """
    print("\nConsolidating duplicate titles across bib files...")

    title_to_entries = defaultdict(list)
    for bib_file in bib_files:
        bib_db = core.parse_bibtex_file(bib_file)
        if not bib_db:
            continue
        for entry in bib_db.entries:
            title = entry.get('title', '')
            if title:
                norm = _normalize_title(title)
                if norm:
                    title_to_entries[norm].append((bib_file, entry))

    duplicates = {t: e for t, e in title_to_entries.items() if len(e) > 1}
    key_mapping = {}

    if not duplicates:
        print("  No duplicate titles to consolidate.")
        return {}

    # process groups one at a time
    file_databases = {bib_file: core.parse_bibtex_file(bib_file)
                      for bib_file in bib_files}

    for norm, entries in duplicates.items():
        # pick best entry among duplicates
        best_entry = choose_best_entry(entries)
        best_key = best_entry['ID']
        print(f"  Title match '{norm}' -> keeping key '{best_key}'")

        # update mapping for all other keys
        for bib_file, entry in entries:
            old_key = utils.normalize_unicode(entry.get('ID', ''))
            if old_key != best_key:
                key_mapping[old_key] = best_key

        # ensure best entry appears once across files and replace others
        files_with_best = set()
        for bib_file, entry in entries:
            db = file_databases.get(bib_file)
            if not db:
                continue
            entry_key = utils.normalize_unicode(entry.get('ID', ''))
            if entry_key == best_key and bib_file not in files_with_best:
                files_with_best.add(bib_file)
                # replace content with best entry
                for i,e in enumerate(db.entries):
                    if utils.normalize_unicode(e.get('ID','')) == best_key:
                        db.entries[i] = best_entry.copy()
                        db.entries[i]['ID'] = best_key
                        break
            elif entry_key != best_key:
                # remove this entry
                for i,e in enumerate(db.entries):
                    if utils.normalize_unicode(e.get('ID','')) == entry_key:
                        del db.entries[i]
                        break

    # write databases back
    for bib_file, db in file_databases.items():
        if db:
            core.write_bib_file(bib_file, db)

    print(f"  Consolidated {len(duplicates)} title groups, {len(key_mapping)} key mappings")
    return key_mapping



# ---------------------------------------------------------------------------
# Utility helpers for duplicate detection/consolidation
# ---------------------------------------------------------------------------

def _normalize_title(title: str) -> str:
    """Return a canonical form of a title for loose matching.

    Removes braces, collapses whitespace, normalises dashes to spaces and
    lowercases the string.  This mirrors the logic previously embedded in
    :func:`check_duplicate_titles` and is reused by the new consolidation
    functions.
    """
    if not title:
        return ''
    title = re.sub(r'[{}]', '', str(title))
    title = re.sub(r'\s+', ' ', title)
    title = re.sub(r'[-–—]+', ' ', title)
    return title.strip().lower()


def check_duplicate_titles():
    """Check for entries with duplicate titles across files.

    Returns the number of duplicate titles found. Entries with the same title
    but different keys might be duplicates that need manual review.
    """
    bib_files = collect_all_bib_files()

    print("\n" + "=" * 80)
    print("5. DUPLICATE TITLE CHECK")
    print("=" * 80)
    print()

    title_to_entries = defaultdict(list)

    for bib_file in bib_files:
        entries = core.parse_bib_file(bib_file)
        for entry in entries:
            title = entry.get('title', '')
            if title:
                normalized = _normalize_title(title)
                if normalized:
                    title_to_entries[normalized].append({
                        'key': entry.get('ID', ''),
                        'file': bib_file.name,
                        'title': title,
                        'author': entry.get('author', 'N/A'),
                        'doi': entry.get('doi', 'N/A') or entry.get('DOI', 'N/A'),
                        'year': entry.get('year', 'N/A')
                    })

    duplicates = {title: entries for title, entries in title_to_entries.items() if len(entries) > 1}

    if duplicates:
        print(f"⚠ Found {len(duplicates)} duplicate titles:")
        print()
        for title, entries in sorted(duplicates.items()):
            # Show first 80 chars of title
            title_display = entries[0]['title']
            if len(title_display) > 80:
                title_display = title_display[:77] + '...'
            print(f"  Title: {title_display}")
            print(f"    Appears {len(entries)} times:")

            # Check if they have the same DOI (likely duplicates)
            dois = [e['doi'] for e in entries if e['doi'] != 'N/A']
            if len(set(dois)) == 1 and dois[0] != 'N/A':
                print(f"    → Same DOI ({dois[0]}) - likely duplicates, consider consolidating")
            elif len(set(dois)) > 1:
                print("    → Different DOIs - may be different papers, manual review needed")

            for entry in entries:
                print(f"      - {entry['file']}: {entry['key']}")
                author_display = str(entry['author'])[:50]
                if len(str(entry['author'])) > 50:
                    author_display += '...'
                print(f"        Author: {author_display}")
                if entry['doi'] != 'N/A':
                    print(f"        DOI: {entry['doi']}")
                print(f"        Year: {entry['year']}")
            print()

        print(f"  → Manual review recommended for {len(duplicates)} duplicate title(s)")
        return len(duplicates)
    else:
        print("✓ No duplicate titles found")
        return 0


def check_duplicate_keys():
    """Check for duplicate entry keys across files."""
    bib_files = collect_all_bib_files()
    
    print("\n" + "=" * 80)
    print("2. DUPLICATE KEY CHECK")
    print("=" * 80)
    print()
    
    key_to_files = defaultdict(list)
    
    for bib_file in bib_files:
        entries = core.parse_bib_file(bib_file)
        for entry in entries:
            key = utils.normalize_unicode(entry.get('ID', ''))
            if key:
                key_to_files[key].append(str(bib_file))
    
    duplicates = {k: files for k, files in key_to_files.items() if len(files) > 1}
    
    if duplicates:
        print(f"Found {len(duplicates)} keys appearing in multiple files:")
        # Check if entries are identical
        all_identical = True
        for key, files in sorted(duplicates.items())[:10]:
            # Get entries from first two files
            entries_list = []
            for f in files[:2]:
                entries = core.parse_bib_file(f)
                for entry in entries:
                    if utils.normalize_unicode(entry.get('ID', '')) == key:
                        entries_list.append(entry)
                        break
            
            if len(entries_list) >= 2:
                if not utils.entries_are_identical(entries_list[0], entries_list[1]):
                    all_identical = False
                    print(f"  ⚠ {key}: Entries differ between files!")
                    break
        
        if all_identical:
            print("  (All duplicate keys have identical entries - expected after curation)")
            for key, files in sorted(duplicates.items())[:5]:
                print(f"    {key}: {len(files)} files")
            if len(duplicates) > 5:
                print(f"    ... and {len(duplicates) - 5} more")
        return True
    else:
        print("✓ No duplicate keys found")
        return False


def check_duplicate_dois():
    """Check for duplicate entries by DOI using the new abstractions."""
    bib_files = collect_all_bib_files()

    print("\n" + "=" * 80)
    print("3. DUPLICATE DOI CHECK")
    print("=" * 80)
    print()

    doi_to_entries = defaultdict(list)

    for bib_file in bib_files:
        # wrap in BibFile for richer metadata
        bf = BibFile(bib_file)
        for entry in bf.entries:
            key = utils.normalize_unicode(entry.get('ID', ''))
            doi = entry.get('doi') or entry.get('DOI') or entry.get('Doi')
            normalized_doi = utils.normalize_doi(doi)
            if normalized_doi:
                doi_to_entries[normalized_doi].append(
                    core.EntryMeta(key=key, file=bf.path, entry=entry)
                )

    # Find duplicates
    duplicates = {}
    issues = []

    for doi, metas in sorted(doi_to_entries.items()):
        if len(metas) > 1:
            keys = set(m.key for m in metas)
            if len(keys) > 1:
                # Different keys for same DOI
                first_entry = metas[0].entry
                all_identical = all(
                    utils.entries_are_identical(first_entry, m.entry) for m in metas[1:]
                )
                if all_identical:
                    duplicates[doi] = metas
                    issues.append({
                        'type': 'same_doi_different_keys',
                        'doi': doi,
                        'keys': list(keys),
                        'suggested_key': metas[0].key,
                    })
                else:
                    issues.append({
                        'type': 'same_doi_different_content',
                        'doi': doi,
                        'keys': list(keys)
                    })
    
    if issues:
        same_doi_diff_keys = sum(1 for i in issues if i['type'] == 'same_doi_different_keys')
        same_doi_diff_content = sum(1 for i in issues if i['type'] == 'same_doi_different_content')
        
        if same_doi_diff_keys > 0:
            print(f"⚠ Found {same_doi_diff_keys} DOIs with different keys (identical content):")
            for issue in issues[:5]:
                if issue['type'] == 'same_doi_different_keys':
                    print(f"  DOI: {issue['doi']}")
                    print(f"    Keys: {', '.join(issue['keys'])}")
                    print(f"    → Should use key: {issue['suggested_key']}")
        
        if same_doi_diff_content > 0:
            print(f"\n❌ Found {same_doi_diff_content} DOIs with different keys AND different content:")
            for issue in issues:
                if issue['type'] == 'same_doi_different_content':
                    print(f"  DOI: {issue['doi']}")
                    print(f"    Keys: {', '.join(issue['keys'])}")
                    print("    → Manual review needed")
        
        return len(issues)
    else:
        print("✓ No duplicate DOIs with different keys found")
        return 0


def check_bibtex_syntax():
    """Check BibTeX file syntax using both bibtexparser and pybtex for thorough validation.
    
    Uses pybtex (stricter parser) to catch syntax errors that bibtexparser might miss,
    such as missing commas between fields or unclosed braces.
    """
    bib_files = collect_all_bib_files()
    
    print("\n" + "=" * 80)
    print("4. BIBTEX SYNTAX VALIDATION")
    print("=" * 80)
    print()
    
    errors = []
    total_entries = 0
    
    for bib_file in bib_files:
        # First try with bibtexparser (more lenient)
        try:
            entries = core.parse_bib_file(bib_file)
            entry_count = len(entries)
            total_entries += entry_count
        except Exception as e:
            print(f"❌ {bib_file.name}: Syntax error (bibtexparser) - {str(e)[:80]}")
            errors.append(bib_file.name)
            continue
        
        # Then try with pybtex (stricter, catches more errors)
        try:
            from pybtex.database.input import bibtex  # type: ignore
            parser = bibtex.Parser()
            with open(bib_file, 'r', encoding='utf-8') as f:
                parser.parse_stream(f)  # Parse to check for syntax errors
            print(f"✓ {bib_file.name}: {entry_count} entries, syntax OK")
        except Exception as e:
            error_str = str(e)
            # Extract line number if available
            import re
            match = re.search(r'line (\d+)', error_str)
            if match:
                line_num = int(match.group(1))
                with open(bib_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                    if line_num <= len(lines):
                        print(f"❌ {bib_file.name}: Syntax error at line {line_num}")
                        print(f"   Error: {error_str[:100]}")
                        print(f"   Line {line_num}: {lines[line_num-1].strip()[:80]}")
                        if line_num > 1:
                            print(f"   Previous: {lines[line_num-2].strip()[:80]}")
            else:
                print(f"❌ {bib_file.name}: Syntax error (pybtex) - {error_str[:100]}")
            errors.append(bib_file.name)
    
    if errors:
        print(f"\n❌ {len(errors)} files have syntax errors")
        print("   → Fix these errors before proceeding with curation")
        return False
    else:
        print(f"\n✓ All {len(bib_files)} files have valid syntax ({total_entries} total entries)")
        return True


def check_malformed_author_fields():
    """Check for malformed author fields in BibTeX entries.
    
    Detects common issues in author fields that can cause LaTeX compilation errors:
    - Incomplete names ending with backslash (e.g., "Al\\" instead of "Alan")
    - Malformed LaTeX accent commands (e.g., "\\ṕ" instead of "\\'{p}")
    - Combining diacritical marks that should be LaTeX commands
    - Trailing backslashes before commas or closing braces
    
    Returns:
        int: Number of issues found
    """
    bib_files = collect_all_bib_files()
    
    print("\n" + "=" * 80)
    print("5. MALFORMED AUTHOR FIELD CHECK")
    print("=" * 80)
    print()
    
    issues = []
    
    for bib_file in bib_files:
        try:
            with open(bib_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    # Skip comment lines
                    stripped = line.strip()
                    if stripped.startswith('%'):
                        continue
                    
                    # Look for author field assignments
                    field_match = re.search(r'^\s*author\s*=\s*\{([^}]*)\}', line, re.IGNORECASE)
                    if field_match:
                        field_value = field_match.group(1)
                        
                        # Check for incomplete names ending with backslash before comma or closing brace
                        if re.search(r'[A-Za-z]\\\s*[,}]', field_value):
                            # Find the entry key
                            entry_key = "unknown"
                            for prev_line_num in range(line_num - 1, max(0, line_num - 20), -1):
                                prev_line = lines[prev_line_num]
                                entry_match = re.search(r'@\w+\{([^,]+)', prev_line)
                                if entry_match:
                                    entry_key = entry_match.group(1).strip()
                                    break
                            
                            issues.append({
                                'file': bib_file.name,
                                'line': line_num,
                                'entry': entry_key,
                                'type': 'incomplete_name',
                                'value': field_value[:150] + ('...' if len(field_value) > 150 else '')
                            })
                        
                        # Check for malformed LaTeX commands (backslash followed by non-letter, non-{)
                        # But exclude valid patterns like \', \{, \}, etc.
                        malformed_pattern = re.search(r'\\(?![a-zA-Z{@\'\"`~=^])', field_value)
                        if malformed_pattern:
                            # Check if it's not a valid escape sequence
                            pos = malformed_pattern.start()
                            char_after = field_value[pos + 1] if pos + 1 < len(field_value) else ''
                            # Valid escapes: \', \", \`, \{, \}, \=, \^, \~, etc.
                            if char_after not in ["'", '"', '`', '{', '}', '=', '^', '~', '&', '#', '%', '_', '$']:
                                entry_key = "unknown"
                                for prev_line_num in range(line_num - 1, max(0, line_num - 20), -1):
                                    prev_line = lines[prev_line_num]
                                    entry_match = re.search(r'@\w+\{([^,]+)', prev_line)
                                    if entry_match:
                                        entry_key = entry_match.group(1).strip()
                                        break
                                
                                issues.append({
                                    'file': bib_file.name,
                                    'line': line_num,
                                    'entry': entry_key,
                                    'type': 'malformed_latex',
                                    'value': field_value[max(0, pos - 20):pos + 30]
                                })
        except Exception as e:
            print(f"❌ Error checking {bib_file.name}: {e}")
    
    if issues:
        incomplete = [i for i in issues if i['type'] == 'incomplete_name']
        malformed = [i for i in issues if i['type'] == 'malformed_latex']
        
        if incomplete:
            print(f"❌ Found {len(incomplete)} entries with incomplete author names:")
            for issue in incomplete[:10]:
                print(f"  {issue['file']}:{issue['line']} - Entry '{issue['entry']}'")
                print("    Issue: Incomplete name ending with backslash")
                print(f"    Author field: {issue['value']}")
                print("    → Fix by completing the name or removing trailing backslash")
        
        if malformed:
            print(f"\n❌ Found {len(malformed)} entries with malformed LaTeX in author fields:")
            for issue in malformed[:10]:
                print(f"  {issue['file']}:{issue['line']} - Entry '{issue['entry']}'")
                print("    Issue: Malformed LaTeX command")
                print(f"    Context: ...{issue['value']}...")
                print(r"    → Fix by using proper LaTeX accent commands (e.g., \'{a} for á)")
        
        if len(issues) > 10:
            print(f"\n  ... and {len(issues) - 10} more issues")
        
        return len(issues)
    else:
        print("✓ No malformed author fields found")
        return 0


def fix_malformed_author_fields(bib_file):
    """Automatically fix malformed author fields in BibTeX entries.
    
    Fixes:
    - Excessive backslashes (e.g., Sch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\tt → Sch{\"u}tt)
    - Incomplete names ending with backslash (e.g., Vez-Mayagoitia, \\ → Vez-Mayagoitia,)
    - Malformed accent commands (e.g., Derezi\νment149ski → Derezi\'{n}ski)
    - Unicode characters that should be LaTeX commands
    
    Returns:
        int: Number of fields fixed
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
        
        # Fix 1: Remove excessive backslashes (more than 3 consecutive)
        # Pattern: multiple backslashes (4 or more) should be reduced
        # Common case: Sch\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\tt → Sch\"{u}tt
        # We'll detect patterns like: letter + many backslashes + letter
        # and convert to proper LaTeX accent
        def fix_excessive_backslashes(text):
            # Pattern: letter + many backslashes (4+) + letter
            # Try to infer the intended accent
            # Common: Sch\\...\\tt → Sch\"{u}tt (ü)
            text = re.sub(r'([A-Za-z])\\{4,}([a-z]+)', r'\1{\\"u}\2', text)
            # More general: reduce excessive backslashes to single backslash
            text = re.sub(r'\\{4,}', r'\\', text)
            return text
        
        value = fix_excessive_backslashes(value)
        
        # Fix 2: Remove incomplete names ending with backslash before comma or closing brace
        # Pattern: name, \\ → name,
        value = re.sub(r',\s*\\+\s*([,}])', r',\1', value)
        # Pattern: name \\ → name (at end of field)
        value = re.sub(r'([A-Za-z])\s*\\+\s*$', r'\1', value)
        
        # Fix 3: Fix malformed accent commands
        # Pattern: \ν or similar Unicode combining marks that got corrupted
        # Replace with proper LaTeX accent commands
        # Common patterns:
        # - \ν → \'{n} (for ń)
        # - \μ → \'{u} (for ú)
        # - etc.
        
        # Map common corrupted patterns to proper LaTeX
        accent_fixes = {
            r'\\ν': r"\\'{n}",  # Greek nu often used incorrectly for n with acute
            r'\\μ': r"\\'{u}",  # Greek mu often used incorrectly for u with acute
            r'\\149': r"\\'{n}",  # Sometimes appears as \149 for ń
        }
        
        for pattern, replacement in accent_fixes.items():
            value = re.sub(pattern, replacement, value)
        
        # Fix 4: Normalize Unicode characters to LaTeX commands where appropriate
        # Convert common Unicode characters to LaTeX
        unicode_to_latex = {
            'ń': r"\'{n}",
            'á': r"\'{a}",
            'é': r"\'{e}",
            'í': r"\'{i}",
            'ó': r"\'{o}",
            'ú': r"\'{u}",
            'ü': r'\"{u}',
            'ö': r'\"{o}',
            'ł': r'\l{}',
            'ć': r"\'{c}",
            'ś': r"\'{s}",
            'ź': r"\'{z}",
            'ą': r"\'{a}",
            'ę': r"\'{e}",
        }
        
        for unicode_char, latex_cmd in unicode_to_latex.items():
            if unicode_char in value:
                value = value.replace(unicode_char, latex_cmd)
        
        # Fix 5: Remove any remaining malformed backslash sequences
        # Pattern: backslash followed by non-standard character (not letter, {, ', ", etc.)
        # Replace with proper accent or remove
        def fix_malformed_backslash(match):
            backslash_seq = match.group(0)
            # If it's a very long sequence of backslashes, it's likely corrupted
            if len(backslash_seq) > 3:
                # Try to infer: if followed by 'tt', it's probably 'ü'
                return '{\"u}'
            return backslash_seq
        
        # Only apply if value changed
        if value != original_value_str:
            entry['author'] = value
            fixed_count += 1
            modified = True
    
    if modified:
        core.write_bib_file(bib_file, bib_database)
        print(f"  Fixed {fixed_count} malformed author field(s)")
    
    return fixed_count


def check_unescaped_percent():
    r"""Check for unescaped % characters in BibTeX fields.
    
    The % character is a comment character in LaTeX/BibTeX and must be escaped
    as \% to be treated as literal text. Unescaped % characters can cause
    compilation errors, especially when they appear at the start of a field.
    
    Returns:
        int: Number of issues found
    """
    bib_files = collect_all_bib_files()
    
    print("\n" + "=" * 80)
    print("6. UNESCAPED % CHARACTER CHECK")
    print("=" * 80)
    print()
    
    issues = []
    fields_to_check = ['title', 'author', 'journal', 'booktitle', 'publisher', 'note', 'abstract']
    
    for bib_file in bib_files:
        entries = core.parse_bib_file(bib_file)
        for entry in entries:
            entry_key = utils.normalize_unicode(entry.get('ID', ''))
            for field_name in fields_to_check:
                field_value = entry.get(field_name) or entry.get(field_name.capitalize()) or entry.get(field_name.upper())
                if field_value:
                    # Check for unescaped % characters
                    # We need to check the raw string, not the parsed value
                    # So we'll read the file and check the raw content
                    pass
    
    # Read files directly to check for unescaped %
    for bib_file in bib_files:
        try:
            with open(bib_file, 'r', encoding='utf-8') as f:
                content = f.read()
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    # Skip comment lines
                    stripped = line.strip()
                    if stripped.startswith('%'):
                        continue
                    
                    # Check for field definitions with unescaped %
                    # Pattern: field_name = {value with unescaped %}
                    # We want to find % that's not preceded by \
                    # But we need to be careful about escaped backslashes
                    
                    # Look for field assignments (single-line fields)
                    # Pattern matches: field_name = {value}
                    field_match = re.search(r'^\s*(\w+)\s*=\s*\{([^}]*)\}', line)
                    if field_match:
                        field_name = field_match.group(1).lower()
                        field_value = field_match.group(2)
                        
                        # Check for unescaped % characters
                        # A % is escaped if it's preceded by an odd number of backslashes
                        # In the raw file string, backslashes are represented as single '\'
                        pos = 0
                        while True:
                            pos = field_value.find('%', pos)
                            if pos == -1:
                                break
                            
                            # Count consecutive backslashes before this %
                            backslash_count = 0
                            check_pos = pos - 1
                            while check_pos >= 0 and field_value[check_pos] == '\\':
                                backslash_count += 1
                                check_pos -= 1
                            
                            # If even number of backslashes (or zero), the % is not escaped
                            # Odd number means it's escaped (e.g., \% or \\\%)
                            if backslash_count % 2 == 0:
                                # This is an unescaped %
                                # Find the entry key by looking backwards
                                entry_key = "unknown"
                                for prev_line_num in range(line_num - 1, max(0, line_num - 20), -1):
                                    prev_line = lines[prev_line_num]
                                    entry_match = re.search(r'@\w+\{([^,]+)', prev_line)
                                    if entry_match:
                                        entry_key = entry_match.group(1).strip()
                                        break
                                
                                issues.append({
                                    'file': bib_file.name,
                                    'line': line_num,
                                    'entry': entry_key,
                                    'field': field_name,
                                    'value': field_value[:100] + ('...' if len(field_value) > 100 else '')
                                })
                                break  # Only report first unescaped % per field
                            
                            pos += 1
        except Exception as e:
            print(f"❌ Error checking {bib_file.name}: {e}")
    
    if issues:
        print(f"❌ Found {len(issues)} entries with unescaped % characters:")
        for issue in issues:
            print(f"  {issue['file']}:{issue['line']} - Entry '{issue['entry']}'")
            print(f"    Field '{issue['field']}': {issue['value']}")
            print("    → Fix by escaping % as \\%")
        return len(issues)
    else:
        print("✓ No unescaped % characters found")
        return 0


def check_file_correspondence():
    """Check that all .tex files have corresponding .bib files."""
    tex_files = collect_all_tex_files()
    
    print("\n" + "=" * 80)
    print("7. FILE CORRESPONDENCE CHECK")
    print("=" * 80)
    print()
    
    issues = []
    for tex_file in tex_files:
        bib_file = get_corresponding_bib(tex_file)
        if bib_file and bib_file.exists():
            print(f"✓ {tex_file.name} ↔ {bib_file.name}")
        else:
            print(f"❌ {tex_file.name}: Missing corresponding .bib file")
            issues.append(tex_file.name)
    
    return len(issues) == 0


def validate_bib_file(bib_file):
    """Validate that a BibTeX file is parseable and report statistics."""
    bib_database = core.parse_bibtex_file(bib_file)
    if not bib_database:
        return None
    
    stats = {
        'file': str(bib_file),
        'entry_count': len(bib_database.entries),
        'entries_with_doi': 0,
        'entries_with_title': 0,
        'entries_with_author': 0,
        'entries_with_year': 0,
        'parseable': True,
    }
    
    for entry in bib_database.entries:
        if 'doi' in entry and entry['doi']:
            stats['entries_with_doi'] += 1
        if 'title' in entry and entry['title']:
            stats['entries_with_title'] += 1
        if 'author' in entry and entry['author']:
            stats['entries_with_author'] += 1
        if 'year' in entry and entry['year']:
            stats['entries_with_year'] += 1
    
    return stats


def generate_report(bib_files, before_stats=None):
    """Generate a validation report for all BibTeX files."""
    print("\n" + "=" * 70)
    print("Validation Report")
    print("=" * 70)
    
    all_stats = []
    total_entries = 0
    total_with_doi = 0
    
    for bib_file in bib_files:
        stats = validate_bib_file(bib_file)
        if stats:
            all_stats.append(stats)
            total_entries += stats['entry_count']
            total_with_doi += stats['entries_with_doi']
            print(f"\n{bib_file.name}:")
            print(f"  Total entries: {stats['entry_count']}")
            if stats['entry_count']:
                pct = 100 * stats['entries_with_doi'] / stats['entry_count']
                print(f"  Entries with DOI: {stats['entries_with_doi']} ({pct:.1f}%)")
            else:
                print(f"  Entries with DOI: {stats['entries_with_doi']} (N/A - no entries)")
            print(f"  Entries with title: {stats['entries_with_title']}")
            print(f"  Entries with author: {stats['entries_with_author']}")
            print(f"  Entries with year: {stats['entries_with_year']}")
            
            # Show improvement if before_stats available
            if before_stats:
                before = before_stats.get(bib_file.name, {})
                if 'entries_with_doi' in before:
                    doi_diff = stats['entries_with_doi'] - before['entries_with_doi']
                    if doi_diff > 0:
                        print(f"  → Added {doi_diff} DOI(s)")
        else:
            print(f"\n{bib_file.name}: ERROR - Could not parse file")
    
    print(f"\n{'=' * 70}")
    print(f"Summary: {len(all_stats)} files, {total_entries} total entries")
    if total_entries > 0:
        print(f"  Total entries with DOI: {total_with_doi} ({100*total_with_doi/total_entries:.1f}%)")
    print(f"{'=' * 70}")


def generate_summary():
    """Generate final summary report."""
    tex_files = collect_all_tex_files()
    bib_files = collect_all_bib_files()
    
    # Collect all keys and citations
    all_keys = set()
    all_citations = set()
    
    for bib_file in bib_files:
        entries = core.parse_bib_file(bib_file)
        for entry in entries:
            key = utils.normalize_unicode(entry.get('ID', ''))
            if key:
                all_keys.add(key)
    
    for tex_file in tex_files:
        all_citations.update(extract_citations_from_tex(tex_file))
    
    print("\n" + "=" * 80)
    print("FINAL SUMMARY")
    print("=" * 80)
    print()
    print("Files checked:")
    print(f"  - {len(tex_files)} .tex files")
    print(f"  - {len(bib_files)} .bib files")
    print(f"  - {len(all_keys)} unique entry keys")
    print(f"  - {len(all_citations)} total citations")
    print(f"  - {len(all_keys - all_citations)} unused entries (normal)")


def validate_bibliography():
    """Run all validation checks."""
    print("=" * 80)
    print("BIBTEX BIBLIOGRAPHY VALIDATION")
    print("=" * 80)
    print()
    
    # Run all checks
    citation_issues = validate_citations()
    check_duplicate_keys()  # Check for duplicate keys (informational)
    doi_issues_count = check_duplicate_dois()
    title_duplicates_count = check_duplicate_titles()  # Check for duplicate titles
    syntax_ok = check_bibtex_syntax()
    author_issues_count = check_malformed_author_fields()
    percent_issues_count = check_unescaped_percent()
    correspondence_ok = check_file_correspondence()
    generate_summary()
    
    # Final status
    print("\n" + "=" * 80)
    print("VALIDATION STATUS")
    print("=" * 80)
    
    all_ok = (
        len(citation_issues) == 0 and
        syntax_ok and
        correspondence_ok and
        doi_issues_count == 0 and
        title_duplicates_count == 0 and
        author_issues_count == 0 and
        percent_issues_count == 0
    )
    
    if all_ok:
        print("✓ All checks passed! Bibliography is ready for use.")
        return 0
    else:
        print("⚠ Issues found:")
        if citation_issues:
            print(f"  - {len(citation_issues)} citation issues")
        if not syntax_ok:
            print("  - BibTeX syntax errors")
        if not correspondence_ok:
            print("  - Missing .bib files")
        if doi_issues_count > 0:
            print(f"  - {doi_issues_count} duplicate DOI issues")
        if author_issues_count > 0:
            print(f"  - {author_issues_count} malformed author field issues")
        if percent_issues_count > 0:
            print(f"  - {percent_issues_count} unescaped % character issues")
        return 1


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description='Unified BibTeX bibliography management script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s validate          # Only validate bibliography
  %(prog)s curate            # Only curate/cleanup bibliography
  %(prog)s polish            # Validate, curate, then validate again (default)
  %(prog)s polish --no-backup  # Polish without creating backups
        """
    )
    
    parser.add_argument(
        'action',
        nargs='?',
        default='polish',
        choices=['validate', 'curate', 'polish'],
        help='Action to perform: validate (only check), curate (only cleanup), or polish (validate + curate + validate)'
    )
    
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup files during curation'
    )
    
    parser.add_argument(
        '--yes', '-y',
        action='store_true',
        help='Skip confirmation prompt and proceed automatically'
    )
    parser.add_argument(
        '--preserve-keys',
        action='store_true',
        help='Do not modify citation keys (skip sanitization and consolidation)'
    )
    
    args = parser.parse_args()
    
    # Find all .bib files (sections + root) using helper
    bib_files = collect_all_bib_files()
    
    if not bib_files:
        print("No .bib files found in sections/ directory or root")
        return 1
    
    # Handle different actions
    if args.action == 'validate':
        return validate_bibliography()
    
    elif args.action == 'curate':
        if not args.yes:
            response = input("\nProceed with curation? This will modify files in place. [y/N]: ")
            if response.lower() != 'y':
                print("Aborted.")
                return 0
        
        curate_bibliography(bib_files, create_backups=not args.no_backup,
                            preserve_keys=args.preserve_keys)
        return 0
    
    elif args.action == 'polish':
        # Polish = validate + curate + validate
        if not args.yes:
            response = input("\nProceed with polishing? This will modify files in place. [y/N]: ")
            if response.lower() != 'y':
                print("Aborted.")
                return 0
        
        print("=" * 80)
        print("BIBLIOGRAPHY POLISHING")
        print("=" * 80)
        print("\nStep 1: Initial validation")
        print("=" * 80)
        validate_bibliography()  # Run initial validation (informational)
        
        print("\n\n" + "=" * 80)
        print("Step 2: Curation and cleanup")
        print("=" * 80)
        curate_bibliography(bib_files, create_backups=not args.no_backup,
                            preserve_keys=args.preserve_keys)
        
        print("\n\n" + "=" * 80)
        print("Step 3: Final validation")
        print("=" * 80)
        final_status = validate_bibliography()
        
        print("\n\n" + "=" * 80)
        print("POLISHING COMPLETE")
        print("=" * 80)
        if final_status == 0:
            print("✓ Bibliography is now polished and ready for use!")
        else:
            print("⚠ Some issues remain (see validation report above)")
        
        return final_status
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

