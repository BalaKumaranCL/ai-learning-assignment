import os

from loader import load_pages

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def test_loads_exactly_six_pages():
    pages = load_pages(DOCS_DIR)
    assert len(pages) == 6


def test_every_page_has_required_metadata():
    pages = load_pages(DOCS_DIR)
    for page in pages:
        assert page.page_id
        assert page.sdk_version == "v3"
        assert page.page_type
        assert page.source_file
        assert page.body.strip()
