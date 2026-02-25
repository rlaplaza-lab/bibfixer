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
   appropriate; citation keys may additionally be standardised
   (AuthorYearJournalFirstTitleWord) **only if a `main.tex` file is present**,
   ensuring corresponding `.tex` updates.
3. Removes unused bibliography entries (those not cited in any `.tex` file).
4. Detects and consolidates duplicate references, first by DOI and then by
   title (loose matching ignores case, braces and punctuation).
5. Applies formatting fixes (via ``bibfmt``) and removes non‑standard fields.
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

The core library requires both `bibtexparser` and the formatting tool
`bibfmt` (installed from GitHub, since it isn’t yet on PyPI).  Curation
routines use `bibfmt` by default to normalise and drop non-standard fields.
Other helpers such as `betterbib` or `pybtex` remain optional extras.

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

1. Bump the version in `bibliography/__init__.py` and `pyproject.toml`.
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

