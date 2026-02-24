import sys
import pathlib

# ensure workspace root is on path so that the bibliography package can be imported
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from bibliography.utils import normalize_doi


def test_version():
    import bibliography

    assert hasattr(bibliography, "__version__")
    assert isinstance(bibliography.__version__, str)


def test_normalize_doi_basic():
    assert normalize_doi("10.1000/xyz") == "10.1000/xyz"


def test_normalize_doi_with_prefixes():
    assert normalize_doi("doi:10.1000/xyz") == "10.1000/xyz"
    assert normalize_doi("DOI:10.1000/xyz") == "10.1000/xyz"
    assert normalize_doi("https://doi.org/10.1000/xyz") == "10.1000/xyz"
    assert normalize_doi("http://dx.doi.org/10.1000/xyz") == "10.1000/xyz"


def test_normalize_doi_strip_whitespace_and_case():
    assert normalize_doi("  DOI:10.1000/XYZ ") == "10.1000/xyz"


def test_normalize_doi_none_or_empty():
    assert normalize_doi(None) is None
    assert normalize_doi("") is None
    assert normalize_doi("   ") is None
