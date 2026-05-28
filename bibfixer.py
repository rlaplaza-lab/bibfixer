#!/usr/bin/env python3
"""Legacy entry-point script.

This file was originally a standalone script but most of the logic has been
moved into the :mod:`bibfixer.cli` submodule.  The stub remains so that
invoking ``python bibfixer.py`` from a checkout still works, and the
same module path can be referenced in ``pyproject.toml`` entry points.
"""

from bibfixer.cli import main

if __name__ == '__main__':
    import sys
    sys.exit(main())
