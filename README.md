# Bibfixer

Small Python package and command-line utility extracted from a standalone
script used to inspect and clean LaTeX project bibliographies.  It provides
helpers for parsing `.bib` files, normalising entry keys, and scanning
`.tex` sources for citation commands.  After installation a console script
called ``bibfixer`` is available for validating and curating bibliographies.

## Development

Run the tests and linting tools with:

```bash
python -m pip install -e .[test]
ruff check .
mypy .
pytest
```

The core library only requires `bibtexparser`.  Additional features such as
updating with `betterbib` or formatting with `bibfmt` are available as
optional extras (`pip install .[betterbib]`, etc.) and are not needed for
the unit tests.

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

