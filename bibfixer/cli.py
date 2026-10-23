"""Command line interface for bibfixer.

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

from . import helpers
from .curate import (
    choose_best_entry,
    choose_best_key,
    consolidate_duplicate_dois,
    consolidate_duplicate_titles,
    create_backup,
    curate_bibliography,
    find_duplicate_dois,
    find_duplicates,
    format_bibliography_file,
    preprocess_bibliography,
    process_bib_file,
    remove_duplicate_entries_across_files,
    remove_duplicate_keys_within_files,
    remove_unused_entries,
    synchronize_duplicates,
    update_with_metadata,
)

# compatibility helpers that wrap the low-level fixes module
from .fixes import (
    fix_html_entities,
    fix_invalid_utf8_bytes,
    fix_latex_unsafe_characters,
    fix_legacy_month_fields,
    fix_legacy_month_fields_text,
    fix_legacy_year_fields,
    fix_malformed_author_fields,
    fix_problematic_unicode,
    fix_unescaped_percent,
    preprocess_bib_for_parsing,
    remove_accents_from_names,
    uncomment_bibtex_entries,
)
from .pipeline import PipelineOptions, resolve_bib_files, run_pipeline
from .validation import (
    check_bibtex_syntax,
    check_duplicate_dois,
    check_duplicate_keys,
    check_duplicate_titles,
    check_file_correspondence,
    check_malformed_author_fields,
    check_unescaped_percent,
    generate_report,
    generate_summary,
    validate_bib_file,
    validate_bibliography,
    validate_citations,
)

# helper shortcuts (these used to be defined inline in this module)
get_corresponding_bib = helpers.get_corresponding_bib
collect_all_tex_files = helpers.collect_all_tex_files
collect_all_bib_files = helpers.collect_all_bib_files
extract_citations_from_tex = helpers.extract_citations_from_tex
update_tex_citations = helpers.update_tex_citations
sanitize_citation_keys = helpers.sanitize_citation_keys
standardize_citation_keys = helpers.standardize_citation_keys
reconcile_bib_keys_with_tex_citations = helpers.reconcile_bib_keys_with_tex_citations
compose_key_mappings = helpers.compose_key_mappings

__all__ = [
    "PipelineOptions",
    "check_bibtex_syntax",
    "check_duplicate_dois",
    "check_duplicate_keys",
    "check_duplicate_titles",
    "check_file_correspondence",
    "check_malformed_author_fields",
    "check_unescaped_percent",
    "choose_best_entry",
    "choose_best_key",
    "collect_all_bib_files",
    "collect_all_tex_files",
    "compose_key_mappings",
    "consolidate_duplicate_dois",
    "consolidate_duplicate_titles",
    "create_backup",
    "curate_bibliography",
    "extract_citations_from_tex",
    "find_duplicate_dois",
    "find_duplicates",
    "fix_html_entities",
    "fix_invalid_utf8_bytes",
    "fix_latex_unsafe_characters",
    "fix_legacy_month_fields",
    "fix_legacy_month_fields_text",
    "fix_legacy_year_fields",
    "fix_malformed_author_fields",
    "fix_problematic_unicode",
    "fix_unescaped_percent",
    "format_bibliography_file",
    "generate_report",
    "generate_summary",
    "get_corresponding_bib",
    "main",
    "preprocess_bib_for_parsing",
    "preprocess_bibliography",
    "process_bib_file",
    "reconcile_bib_keys_with_tex_citations",
    "remove_accents_from_names",
    "remove_duplicate_entries_across_files",
    "remove_duplicate_keys_within_files",
    "remove_unused_entries",
    "resolve_bib_files",
    "run_pipeline",
    "sanitize_citation_keys",
    "standardize_citation_keys",
    "synchronize_duplicates",
    "uncomment_bibtex_entries",
    "update_tex_citations",
    "update_with_metadata",
    "validate_bib_file",
    "validate_bibliography",
    "validate_citations",
]


def main() -> int:
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
  %(prog)s references.bib    # Polish a specific bibliography file
        """,
    )

    parser.add_argument(
        'targets',
        nargs='*',
        help='Optional action (validate/curate/polish) followed by optional .bib file paths'
    )
    parser.add_argument('--no-backup', action='store_true', help='Skip creating backup files during curation')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt and proceed automatically')
    parser.add_argument('--preserve-keys', action='store_true', help='Do not modify citation keys (skip sanitization and consolidation)')
    parser.add_argument('--skip-metadata-update', action='store_true', help='Skip running metadata update and journal abbreviation steps')

    args = parser.parse_args()

    actions = {"validate", "curate", "polish"}
    action = "polish"
    explicit_inputs = list(args.targets)
    if explicit_inputs and explicit_inputs[0] in actions:
        action = explicit_inputs[0]
        explicit_inputs = explicit_inputs[1:]
    elif any(token in actions for token in explicit_inputs[1:]):
        parser.error("Action must be the first positional argument")

    try:
        bib_files = resolve_bib_files(explicit_inputs if explicit_inputs else None)
    except ValueError as exc:
        print(str(exc))
        return 1

    use_metadata_update = not args.skip_metadata_update
    if not bib_files:
        print("No .bib files found in sections/ directory or root")
        return 1

    if action == 'validate':
        result = run_pipeline(
            action='validate',
            options=PipelineOptions(
                create_backups=not args.no_backup,
                preserve_keys=args.preserve_keys,
                use_metadata_update=use_metadata_update,
            ),
            bib_files=bib_files,
        )
        return 0 if result.success else 1

    if action == 'curate':
        if not args.yes:
            resp = input("\nProceed with curation? This will modify files in place. [y/N]: ")
            if resp.lower() != 'y':
                print("Aborted.")
                return 0
        run_pipeline(
            action='curate',
            options=PipelineOptions(
                create_backups=not args.no_backup,
                preserve_keys=args.preserve_keys,
                use_metadata_update=use_metadata_update,
            ),
            bib_files=bib_files,
        )
        return 0

    # polish
    if not args.yes:
        resp = input("\nProceed with polishing? This will modify files in place. [y/N]: ")
        if resp.lower() != 'y':
            print("Aborted.")
            return 0

    result = run_pipeline(
        action='polish',
        options=PipelineOptions(
            create_backups=not args.no_backup,
            preserve_keys=args.preserve_keys,
            use_metadata_update=use_metadata_update,
        ),
        bib_files=bib_files,
    )
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())
