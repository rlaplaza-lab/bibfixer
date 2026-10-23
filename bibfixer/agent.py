"""Non-interactive API for agents that need to repair bibliographies."""

from __future__ import annotations

import io
import os
from collections.abc import Sequence
from contextlib import redirect_stdout
from pathlib import Path
from typing import TypedDict

from .pipeline import PipelineOptions, resolve_bib_files, run_pipeline

_ACTIONS = ("validate", "curate", "polish")


class AgentResult(TypedDict):
    """JSON-ready outcome of one bibfixer action."""

    success: bool
    action: str
    project_dir: str
    bib_files: list[str]
    log: str


def run_references(
    action: str = "polish",
    *,
    project_dir: str | None = None,
    bib_paths: Sequence[str] | None = None,
    create_backups: bool = True,
    preserve_keys: bool = False,
    skip_metadata_update: bool = False,
) -> AgentResult:
    """Run validate, curate, or polish and capture the terminal log.

    ``project_dir`` is the LaTeX project root. Discovery treats that directory
    as the working directory. Pass ``bib_paths`` to limit the run to those
    ``.bib`` files. The call does not prompt for confirmation.
    """
    root = Path(project_dir).expanduser().resolve() if project_dir else Path.cwd()
    if action not in _ACTIONS:
        return _failure(
            action,
            str(root),
            f"Unknown action {action!r}. Use validate, curate, or polish.",
        )
    if project_dir and not root.is_dir():
        return _failure(action, str(root), f"Project directory not found: {root}")

    previous = Path.cwd()
    try:
        os.chdir(root)
        try:
            selected = resolve_bib_files(list(bib_paths) if bib_paths else None)
        except ValueError as exc:
            return _failure(action, str(root), str(exc))
        if not selected:
            return _failure(
                action,
                str(root),
                "No .bib files found in sections/ or the project root.",
            )

        options = PipelineOptions(
            create_backups=create_backups,
            preserve_keys=preserve_keys,
            use_metadata_update=not skip_metadata_update,
        )
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            result = run_pipeline(action, options, selected)
        return {
            "success": result.success,
            "action": action,
            "project_dir": str(root),
            "bib_files": [str(path.resolve()) for path in selected],
            "log": buffer.getvalue(),
        }
    finally:
        os.chdir(previous)


def _failure(action: str, project_dir: str, log: str) -> AgentResult:
    return {
        "success": False,
        "action": action,
        "project_dir": project_dir,
        "bib_files": [],
        "log": log,
    }
