"""Pytest configuration for the bibliography project.

This file ensures that the project root is on ``sys.path`` so that tests can
import the package without each module having to manipulate ``sys.path``.
Common imports used across tests (such as ``os`` and ``re``) are also
available here if desired.
"""

from __future__ import annotations

import sys
import pathlib

# add workspace root to path for test imports
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest


@pytest.fixture
def disable_bibfmt(monkeypatch):
    """Patch subprocess.run so that external bibfmt calls are no-ops.

    Tests which exercise formatting logic can override this if they need to
    simulate actual bibfmt behaviour; otherwise it avoids invoking an external
    command during the curation workflow.
    """
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: type("R", (), {"returncode": 0, "stderr": ""})())
    return monkeypatch
