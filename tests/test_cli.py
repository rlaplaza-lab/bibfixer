import subprocess
import sys


def test_cli_help():
    # call the CLI script to make sure it runs without error
    result = subprocess.run([sys.executable, "-m", "bibfixer.cli", "--help"],
                            capture_output=True,
                            text=True)
    assert result.returncode == 0
    # the help text should reference BibTeX functionality
    assert "unified bibtex" in result.stdout.lower()
