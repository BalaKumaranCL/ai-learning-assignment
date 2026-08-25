"""A tiny SIMULATED v2 index, used only for the metadata-filter demo.

The real assignment says "your existing app already indexes the v2 pages".
This is a from-scratch practice project, so there is no real v2 index to
reuse -- these two chunks stand in for it. They are NOT part of the six v3
pages being evaluated anywhere else in this project; they only ever appear
in the filter-demo retriever built in pipeline.py.
"""

from models import Chunk


def build_legacy_v2_chunks():
    return [
        Chunk(
            chunk_id="client_v2::legacy::0",
            text=(
                "In the legacy v2 SDK, Client.send() accepts a retry_backoff_ms "
                "parameter. The default value of retry_backoff_ms in v2 is 500 "
                "milliseconds between retries."
            ),
            source_file="client_v2_legacy.md",
            page_id="client_v2",
            sdk_version="v2",
            page_type="reference",
            anchor="Client.send() (v2) > retry_backoff_ms",
            strategy="legacy_v2",
        ),
        Chunk(
            chunk_id="client_v2::legacy::1",
            text=(
                "v2 Client.send() also supports a timeout_ms parameter, "
                "defaulting to 20000 milliseconds, and is now superseded by the "
                "v3 Client documented on the client reference page."
            ),
            source_file="client_v2_legacy.md",
            page_id="client_v2",
            sdk_version="v2",
            page_type="reference",
            anchor="Client.send() (v2) > timeout_ms",
            strategy="legacy_v2",
        ),
    ]
