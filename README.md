# Bibfixer

Small Python package and command-line utility extracted from a standalone
script used to inspect and clean LaTeX project bibliographies.  It provides
helpers for parsing `.bib` files, normalising entry keys, and scanning
`.tex` sources for citation commands.  After installation a console script
called ``bibfixer`` is available for validating and curating bibliographies.

## Usage 📦

Once installed, the `bibfixer` command can be run from your project root to
inspect and repair your bibliography and TeX source.  By default it will
process ``references.bib`` and ``main.tex`` (but you may specify other paths
via command-line options).  The utility performs the following operations
*automatically*:

1. Creates backups of the original files (`.backup` suffix) before making any
   changes.
2. Normalises entry keys and fields using journal abbreviations where
   appropriate.  The base mapping is now sourced from two CSV files
   shipped with the package (general journals plus an ACS‑specific list);
   callers may still mutate ``bibfixer.fixes.JOURNAL_ABBREVIATIONS`` to
   add or override entries.  When a title isn’t found in the map we apply an ISO 4 standard
   abbreviation via the ``iso4`` package, which is now a mandatory
   dependency of the project.  If the library itself fails the exception will
   propagate rather than being swallowed; this makes installation problems
   obvious early.  The ``journal`` field itself will only be modified when a
   genuine abbreviation is available.  Citation keys may additionally be
   standardised (AuthorYearJournalFirstTitleWord) **only if a `main.tex`
   file is present**, ensuring corresponding `.tex` updates.
3. Removes unused bibliography entries (those not cited in any `.tex` file).
4. Detects and consolidates duplicate references, first by DOI and then by
   title (loose matching ignores case, braces and punctuation).
5. Applies formatting fixes (via ``bibfmt``) and removes non‑standard fields.
6. When validating, a summary of missing or commented citations is printed,
   along with a breakdown of how many of the citations in each file were
   actually found to be valid.
6. Generates a detailed report on all changes made, written to standard
   output.

### Example

```bash
pip install .            # install the package and its dependencies

# run on the default bibliography and tex files
bibfixer

# or specify files explicitly
bibfixer --bib references.bib --tex main.tex
```

After running, ``references.bib`` and ``main.tex`` will be updated (with
backups preserved) and you will see a summary report of the modifications.

---


## Development

Run the tests and linting tools with:

```bash
python -m pip install -e .[test]
ruff check .
mypy .
pytest
```

The core library requires `bibtexparser`, the formatting tool
`bibfmt` (installed from GitHub, since it isn’t yet on PyPI), and
`betterbib` (also pulled from GitHub).  The latter is no longer an optional
extra: the CLI uses it unconditionally during curation and the dependency is
recorded in :file:`pyproject.toml` using a direct URL to the
`rlaplaza-lab/betterbib` repository.  This ensures that CI jobs and end users
have a consistent installation that matches the version we test against.

For development you still might want a local copy of `betterbib` so you can
apply or test patches before they are merged upstream.  One convenient setup
is to clone the repo alongside this project and install it in editable mode:

```sh
cd /path/to/bibfixer
git clone https://github.com/rlaplaza/betterbib betterbib-src
pip install -e betterbib-src  # or using poetry/poetry in-project path
```

The copy under ``betterbib-src`` in the workspace already contains a few
safeguards (faulthandler enabled, extra error handling) that help when
`betterbib` misbehaves; updating that directory will pull in upstream fixes as
well.  **Note**: the upstream repository stores its large ``journals.json``
file in Git LFS.  `pip install` from GitHub does *not* fetch LFS objects, so
an install may end up with a tiny pointer file instead of the real data.  In
those situations the abbreviation subcommand will be skipped with a warning, but
catering to this corner case is less critical now that betterbib is a
standard dependency.  Our built-in mapping (and, if installed, the optional
``iso4`` package) will still be consulted later; if neither produces a valid
ISO 4 abbreviation the full journal title is left untouched.  The
command-line flag `--no-betterbib` (or environment variable
``BIBFIXER_NO_BETTERBIB``) can be used to disable both the update and
abbreviation steps entirely (for offline runs or troubleshooting).

When `betterbib` is installed we call it twice during curation:

* `betterbib update` to pull updated metadata (DOIs, titles, etc.)
* `betterbib abbreviate-journal-names -i` to apply the tool's internal
  journal mapping, optionally supplemented via an extra JSON file
  (`--extra-abbrev-file`).

If either invocation fails (timeout, crash, non‑zero exit code) the workflow
prints a warning and continues; our built-in map and the ISO 4
abbreviation provided by the mandatory ``iso4`` package will still run
later as a fallback, though it will refrain from inventing a spurious
abbreviation.  Crash messages include the signal number (e.g.
"crashed with signal 11").

Install the package normally, which will pull in bibfmt:

```bash
pip install .
```

After installing the package you can call the CLI directly:

```bash
bibfixer --help
```
## Packaging and distribution

A `pyproject.toml` is provided so the library can be built with `build` or
installed via `pip install .`.  Before a release:

1. Bump the version in `bibfixer/__init__.py` and `pyproject.toml`.
2. Add release notes or changelog entries.
3. Build wheel and sdist (`python -m build`).
4. Upload to PyPI with `twine`.

For professional distribution you may also want to:

* Publish the source on GitHub with a liberal open source license (MIT, BSD,
  etc.).
* Configure CI (GitHub Actions, GitLab CI) to run ruff/mypy/pytest on push and
  pull requests.
* Add `setup.cfg` or other configuration files for tooling such as
  `coverage`, `flake8`, etc.
* Tag releases and maintain a changelog.

