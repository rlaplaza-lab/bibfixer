import subprocess
import sys


def test_cli_help():
    # call the CLI script to make sure it runs without error
    result = subprocess.run([sys.executable, "-m", "bibliography.cli", "--help"],
                            capture_output=True,
                            text=True)
    assert result.returncode == 0
    assert "Unified BibTeX bibliography management script" in result.stdout
