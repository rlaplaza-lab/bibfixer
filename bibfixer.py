"""Legacy entry-point script.

This file was originally a standalone script but most of the logic has been
moved into the :mod:`bibfixer.cli` submodule.  The stub remains so that
invoking ``python bibfixer.py`` from a checkout still works.
"""

import sys

from bibfixer.cli import main

if __name__ == "__main__":
    sys.exit(main())
