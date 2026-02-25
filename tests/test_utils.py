from bibfixer.utils import (
    normalize_unicode,
    normalize_doi,
    normalize_url,
    normalize_keywords,
    normalize_entry,
    entries_are_identical,
    normalize_title,
)


def test_version():
    import bibfixer

    assert hasattr(bibfixer, "__version__")
    assert isinstance(bibfixer.__version__, str)


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


def test_normalize_unicode_and_url_and_keywords():
    # unicode normalization should return None for falsy and normalized form otherwise
    assert normalize_unicode(None) is None
    assert normalize_unicode("") is None
    assert normalize_unicode("E\u0301") == "É"  # decomposed to composed

    # url normalization lowercases scheme and strips whitespace
    assert normalize_url(" HTTP://EXAMPLE.COM/path ") == "http://EXAMPLE.COM/path"
    assert normalize_url(None) is None
    assert normalize_url("") is None

    # keyword normalization splits and lowercases
    assert normalize_keywords("Physics, Chemistry,  math ") == "physics,chemistry,math"
    assert normalize_keywords("   ") is None
    assert normalize_keywords(None) is None


def test_normalize_entry_and_comparison():
    entry1 = {"ID": "Key", "Title": "Test", "year": "2020"}
    entry2 = {"ID": "Other", "title": "Test", "Year": "2020"}
    norm1 = normalize_entry(entry1)
    norm2 = normalize_entry(entry2)
    # ID field should be removed and keys lowercased
    assert "id" not in norm1
    assert norm1 == norm2
    # entries_are_identical uses normalize_entry internally
    assert entries_are_identical(entry1, entry2)
    # difference in another field should break identity
    entry3 = {"ID": "Key", "title": "Test", "year": "2021"}
    assert not entries_are_identical(entry1, entry3)


def test_normalize_title_function():
    # braces removed, separators collapsed, lowercased
    raw = "{A} Title---with  {Hyphens} and {SPACES}"
    norm = normalize_title(raw)
    assert norm == "a title with hyphens and spaces"
    # different punctuation treated similarly
    assert normalize_title("A – Title") == "a title"
