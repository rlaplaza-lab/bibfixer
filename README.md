# Bibfixer

Small Python package and command-line utility extracted from a standalone
script used to inspect and clean LaTeX project bibliographies.  It provides
helpers for parsing `.bib` files, normalising entry keys, and scanning
`.tex` sources for citation commands.  After installation a console script
called ``bibfixer`` is available for validating and curating bibliographies.

## Usage 📦

Once installed, the `bibfixer` command can be run from your project root to
inspect and repair your bibliography and TeX source. The tool discovers
supported `.bib`/`.tex` files from the project layout automatically. The
utility performs the following operations
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
5. Applies formatting fixes and removes non‑standard fields.
6. When validating, a summary of missing or commented citations is printed,
   along with a breakdown of how many of the citations in each file were
   actually found to be valid.
7. Emits a structured terminal run log with phase/step outcomes, counters,
   and a deterministic final summary.

### Example

```bash
pip install .            # install the package and its dependencies

# run on the default bibliography and tex files
bibfixer

# explicitly choose workflow mode
bibfixer validate
bibfixer curate --yes
bibfixer polish --yes
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

The core library requires `bibtexparser` and `iso4`. Bibliography metadata
update, abbreviation, and formatting operations are implemented in-process
within `bibfixer`.

During curation, bibfixer performs internal metadata update/DOI fallback,
journal abbreviation, and formatting passes without requiring external helper
binaries on `PATH`.

The command-line flag `--skip-metadata-update` (or environment variable
`BIBFIXER_SKIP_METADATA`) disables metadata update and abbreviation
for troubleshooting or fully offline cleanup runs.

Install the package normally:

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

