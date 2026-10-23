# Bibfixer

Use this package to inspect and repair LaTeX bibliographies. Do not hand-edit `.bib` entries or `\cite` keys when a bibfixer action can do it.

## Fix references

Prefer the bibfixer MCP tools when the server is available:

- `validate_references` — report citation and field problems. It can still apply text-level parse fixes. It does not drop entries or contact Crossref.
- `curate_references` — rewrite the bibliography: backups, unused and duplicate entries, field cleanup, and citation-key updates.
- `polish_references` — validate, curate, then validate again. Use this when the user asks to fix references.

Pass `project_dir` as the LaTeX project root. Pass `bib_paths` only when the user named specific `.bib` files. Leave `skip_metadata_update` false unless the user wants an offline run. `curate_references` and `polish_references` write files in place and create `.backup` copies unless `create_backups` is false. Do not call them for a read-only question.

The same actions from a shell, run in the project root:

```bash
bibfixer validate
bibfixer curate --yes
bibfixer polish --yes
```

`curate` and `polish` wait on stdin unless `--yes` is set. `validate` does not prompt.

From Python, without a prompt:

```python
from bibfixer.agent import run_references

run_references("polish", project_dir=".", skip_metadata_update=False)
```

Discovery is relative to the project root: `sections/*.bib`, `sections/*.tex`, root `main.tex`, then `references.bib` or `bibliography.bib`. Other root `.bib` files are used only when those conventional names are absent. Full citation-key standardization runs only when `main.tex` exists. Metadata updates call Crossref and need network access.

## Developing this repository

```bash
python -m pip install -e ".[test]"
ruff check .
mypy bibfixer
vulture bibfixer tests bibfixer.py --min-confidence 80
pytest -q tests
```

The core package supports Python 3.9, 3.10, and 3.11. CI runs on Ubuntu 24.04
because Ubuntu 26.04 does not provide Python 3.9; keep that runner pin. The
MCP extra needs Python 3.10+:

```bash
python -m pip install -e ".[mcp]"
python -m bibfixer.mcp
```

Do not reformat the tree with `ruff format` unless asked. Keep broad `except Exception` only at bibtexparser, pybtex, and metadata boundaries.
