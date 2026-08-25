from models import Chunk, validate_chunks


def _valid_chunk(**overrides):
    fields = dict(
        chunk_id="test::0",
        text="some text",
        source_file="test.md",
        page_id="test",
        sdk_version="v3",
        page_type="reference",
    )
    fields.update(overrides)
    return Chunk(**fields)


def test_valid_chunk_passes_validation():
    assert validate_chunks([_valid_chunk()]) == []


def test_chunk_missing_source_file_fails_validation():
    bad_chunk = _valid_chunk(source_file="")
    errors = validate_chunks([bad_chunk])
    assert len(errors) == 1
    assert "source_file" in errors[0]


def test_chunk_missing_multiple_fields_reports_each():
    bad_chunk = _valid_chunk(source_file="", sdk_version="")
    errors = validate_chunks([bad_chunk])
    assert len(errors) == 2
