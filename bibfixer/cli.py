#!/usr/bin/env python3
"""Command line interface for the *bibfmt* package.

This module used to contain nearly two thousand lines of logic; most of the
heavy lifting has now been moved into :mod:`bibfixer.curate` and
:mod:`bibfixer.validation`.  The remaining code is just a small wrapper
that exposes the familiar ``validate`` / ``curate`` / ``polish`` commands.

The export names are preserved for backwards compatibility so that existing
scripts and tests continue to work without modification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path  # noqa: F401

from . import helpers
from .curate import (  # noqa: F401
    create_backup,
    update_with_betterbib,
    format_with_bibfmt,
    find_duplicates,
    choose_best_entry,
    synchronize_duplicates,
    find_duplicate_dois,
    choose_best_key,
    consolidate_duplicate_dois,
    process_bib_file,
    curate_bibliography,
    remove_duplicate_entries_across_files,
    remove_unused_entries,
    consolidate_duplicate_titles,
)

# compatibility helpers that wrap the low-level fixes module
from .fixes import (  # noqa: F401
    fix_invalid_utf8_bytes,
    fix_problematic_unicode,
    fix_html_entities,
    fix_unescaped_percent,
    uncomment_bibtex_entries,
    remove_accents_from_names,
    fix_legacy_year_fields,
    fix_legacy_month_fields,
    fix_malformed_author_fields,
)
from .validation import (  # noqa: F401
    validate_citations,
    validate_bib_file,
    generate_report,
    check_duplicate_titles,
    check_duplicate_keys,
    check_duplicate_dois,
    check_bibtex_syntax,
    check_malformed_author_fields,
    check_unescaped_percent,
    check_file_correspondence,
    generate_summary,
    validate_bibliography,
)

# helper shortcuts (these used to be defined inline in this module)
get_corresponding_bib = helpers.get_corresponding_bib
collect_all_tex_files = helpers.collect_all_tex_files
collect_all_bib_files = helpers.collect_all_bib_files
extract_citations_from_tex = helpers.extract_citations_from_tex
update_tex_citations = helpers.update_tex_citations
sanitize_citation_keys = helpers.sanitize_citation_keys
standardize_citation_keys = helpers.standardize_citation_keys


# ==========================================================================
# Main Entry Point
# ==========================================================================


def main():
    """Parse command-line arguments and dispatch to the appropriate workflow."""
    parser = argparse.ArgumentParser(
        description='Unified BibTeX bibliography management script',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s validate          # Only validate bibliography
  %(prog)s curate            # Only curate/cleanup bibliography
  %(prog)s polish            # Validate, curate, then validate again (default)
  %(prog)s polish --no-backup  # Polish without creating backups
        """,
    )

    parser.add_argument(
        'action',
        nargs='?',
        default='polish',
        choices=['validate', 'curate', 'polish'],
        help='Action to perform: validate (only check), curate (only cleanup), or polish (validate + curate + validate)'
    )
    parser.add_argument('--no-backup', action='store_true', help='Skip creating backup files during curation')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt and proceed automatically')
    parser.add_argument('--preserve-keys', action='store_true', help='Do not modify citation keys (skip sanitization and consolidation)')

    args = parser.parse_args()

    bib_files = collect_all_bib_files()
    if not bib_files:
        print("No .bib files found in sections/ directory or root")
        return 1

    if args.action == 'validate':
        return validate_bibliography()

    if args.action == 'curate':
        if not args.yes:
            resp = input("\nProceed with curation? This will modify files in place. [y/N]: ")
            if resp.lower() != 'y':
                print("Aborted.")
                return 0
        curate_bibliography(bib_files, create_backups=not args.no_backup, preserve_keys=args.preserve_keys)
        return 0

    # polish
    if not args.yes:
        resp = input("\nProceed with polishing? This will modify files in place. [y/N]: ")
        if resp.lower() != 'y':
            print("Aborted.")
            return 0

    print("=" * 80)
    print("BIBLIOGRAPHY POLISHING")
    print("=" * 80)
    print("\nStep 1: Initial validation")
    print("=" * 80)
    validate_bibliography()

    print("\n\n" + "=" * 80)
    print("Step 2: Curation and cleanup")
    print("=" * 80)
    curate_bibliography(bib_files, create_backups=not args.no_backup, preserve_keys=args.preserve_keys)

    print("\n\n" + "=" * 80)
    print("Step 3: Final validation")
    print("=" * 80)
    validate_bibliography()

    print("\n\n" + "=" * 80)
    print("POLISHING COMPLETE")
    print("=" * 80)
    return 0


if __name__ == '__main__':
    sys.exit(main())
