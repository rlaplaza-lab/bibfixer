"""Canonical pipeline runner for bibfixer actions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import helpers
from .curate import curate_bibliography
from .runlog import RunLogger
from .validation import validate_bibliography


@dataclass
class PipelineOptions:
    """Execution options shared by all actions."""

    create_backups: bool = True
    preserve_keys: bool = False
    use_metadata_update: bool = True


@dataclass
class PipelineResult:
    """Normalized pipeline result used by CLI exit handling."""

    success: bool
    validation_pre_ok: bool | None = None
    validation_post_ok: bool | None = None


def run_pipeline(action: str, options: PipelineOptions, bib_files: list[Path]) -> PipelineResult:
    """Run the canonical plan for validate/curate/polish."""
    logger = RunLogger(action=action)
    if action == "validate":
        logger.start_phase("validate", "Validation")
        valid = validate_bibliography(logger=logger)
        logger.end_phase("validate")
        logger.render_final_summary()
        return PipelineResult(success=valid, validation_pre_ok=valid, validation_post_ok=valid)

    if action == "curate":
        logger.start_phase("curate", "Curation")
        curate_bibliography(
            bib_files,
            create_backups=options.create_backups,
            preserve_keys=options.preserve_keys,
            use_metadata_update=options.use_metadata_update,
            logger=logger,
        )
        logger.end_phase("curate")
        logger.render_final_summary()
        return PipelineResult(success=True)

    logger.start_phase("validate_pre", "Initial validation")
    validation_pre_ok = validate_bibliography(logger=logger)
    logger.end_phase("validate_pre")

    logger.start_phase("curate", "Curation")
    curate_bibliography(
        bib_files,
        create_backups=options.create_backups,
        preserve_keys=options.preserve_keys,
        use_metadata_update=options.use_metadata_update,
        logger=logger,
    )
    logger.end_phase("curate")

    logger.start_phase("validate_post", "Final validation")
    validation_post_ok = validate_bibliography(logger=logger)
    logger.end_phase("validate_post")
    logger.render_final_summary()

    return PipelineResult(
        success=validation_post_ok,
        validation_pre_ok=validation_pre_ok,
        validation_post_ok=validation_post_ok,
    )


def resolve_bib_files(explicit_inputs: list[str] | None = None) -> list[Path]:
    """Resolve bibliography inputs consistently for all actions.

    When *explicit_inputs* is provided, only those paths are used.
    """
    if not explicit_inputs:
        return helpers.collect_all_bib_files()

    bib_files: list[Path] = []
    missing: list[str] = []
    seen: set[Path] = set()

    for raw in explicit_inputs:
        candidate = Path(raw)
        if not candidate.exists():
            missing.append(raw)
            continue
        if candidate.is_dir():
            for nested in sorted(candidate.glob("*.bib")):
                if nested not in seen:
                    seen.add(nested)
                    bib_files.append(nested)
            continue
        if candidate.suffix.lower() != ".bib":
            continue
        if candidate not in seen:
            seen.add(candidate)
            bib_files.append(candidate)

    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Bibliography file(s) not found: {joined}")
    if not bib_files:
        raise ValueError("No .bib files found in explicit inputs")
    return bib_files
