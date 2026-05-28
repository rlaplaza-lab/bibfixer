import subprocess
import sys
from pathlib import Path

from bibfixer import cli
from bibfixer import pipeline


def test_cli_help():
    # call the CLI script to make sure it runs without error
    result = subprocess.run([sys.executable, "-m", "bibfixer.cli", "--help"],
                            capture_output=True,
                            text=True)
    assert result.returncode == 0
    # the help text should reference BibTeX functionality
    assert "unified bibtex" in result.stdout.lower()


def test_polish_returns_failure_when_final_validation_fails(tmp_path, monkeypatch):
    bib = tmp_path / "local.bib"
    tex = tmp_path / "main.tex"
    bib.write_text("""@article{A,
  title={T},
}
""")
    tex.write_text(r"\cite{A}")
    monkeypatch.chdir(tmp_path)

    def fake_curate(*args, **kwargs):
        tex.write_text(r"\cite{MissingAfterCurate}")

    monkeypatch.setattr(pipeline, "curate_bibliography", fake_curate)
    monkeypatch.setattr(sys, "argv", ["bibfixer", "polish", "--yes", "--skip-metadata-update"])
    assert cli.main() == 1


def test_validate_command_emits_run_summary(tmp_path, monkeypatch, capsys):
    bib = Path(tmp_path / "local.bib")
    tex = Path(tmp_path / "main.tex")
    bib.write_text("""@article{A,
  title={T},
}
""")
    tex.write_text(r"\cite{A}")
    monkeypatch.chdir(tmp_path)
    # keep this assertion focused on CLI run-summary plumbing rather than
    # parser backend differences across Python versions.
    monkeypatch.setattr("bibfixer.validation.check_bibtex_syntax", lambda: True)
    monkeypatch.setattr(sys, "argv", ["bibfixer", "validate"])
    assert cli.main() == 0
    out = capsys.readouterr().out
    assert "Run Summary" in out
    assert "Action: validate" in out


def test_cli_accepts_bib_path_without_action(tmp_path, monkeypatch):
    bib = tmp_path / "references.bib"
    bib.write_text("""@article{A,
  title={T},
}
""")
    monkeypatch.chdir(tmp_path)

    captured: dict[str, object] = {}

    def fake_run_pipeline(action, options, bib_files):
        captured["action"] = action
        captured["bib_files"] = [Path(p) for p in bib_files]
        return pipeline.PipelineResult(success=True)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(sys, "argv", ["bibfixer", "references.bib", "--yes", "--skip-metadata-update"])

    assert cli.main() == 0
    assert captured["action"] == "polish"
    assert captured["bib_files"] == [Path("references.bib")]
