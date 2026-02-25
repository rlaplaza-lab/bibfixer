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
