from pathlib import Path

from bibfixer.agent import run_references


def test_unknown_action_does_not_change_directory(tmp_path: Path) -> None:
    start = Path.cwd()
    result = run_references("explode", project_dir=str(tmp_path))
    assert result["success"] is False
    assert "Unknown action" in result["log"]
    assert Path.cwd() == start


def test_missing_project_directory() -> None:
    result = run_references("validate", project_dir="/this/bibfixer/path/does/not/exist")
    assert result["success"] is False
    assert "not found" in result["log"]


def test_missing_bib_path(tmp_path: Path) -> None:
    result = run_references("validate", project_dir=str(tmp_path), bib_paths=["missing.bib"])
    assert result["success"] is False
    assert "missing.bib" in result["log"]
    assert result["bib_files"] == []


def test_validate_reports_discovered_bibliography(tmp_path: Path) -> None:
    bib = tmp_path / "references.bib"
    bib.write_text(
        """@article{A,
  title={Kept},
  author={Doe, Jane},
  journal={J. Test},
  year={2020},
}
"""
    )
    (tmp_path / "main.tex").write_text(r"\cite{A}")
    original = bib.read_text()

    result = run_references("validate", project_dir=str(tmp_path))

    assert result["action"] == "validate"
    assert result["bib_files"] == [str(bib.resolve())]
    assert "Run Summary" in result["log"]
    assert "Action: validate" in result["log"]
    assert bib.read_text() == original


def test_polish_removes_uncited_entry_offline(tmp_path: Path) -> None:
    start = Path.cwd()
    bib = tmp_path / "references.bib"
    bib.write_text(
        """@article{Used,
  title={Kept},
  author={Doe, Jane},
  journal={J. Test},
  year={2020},
}
@article{Unused,
  title={Drop me},
  author={Roe, Richard},
  journal={J. Test},
  year={2021},
}
"""
    )
    (tmp_path / "main.tex").write_text(r"\cite{Used}")

    result = run_references(
        "polish",
        project_dir=str(tmp_path),
        skip_metadata_update=True,
    )

    text = bib.read_text()
    assert "Kept" in text
    assert "Drop me" not in text
    assert "Run Summary" in result["log"]
    assert Path.cwd() == start
