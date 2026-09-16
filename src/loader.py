"""Loads the six v3 SDK reference pages from docs/ into Page objects.

Each page starts with a small YAML-style frontmatter block delimited by
"---" lines, e.g.:

    ---
    page_id: client
    sdk_version: v3
    page_type: reference
    source_file: client.md
    ---
    # Client
    ...

We only ever ingest the files in docs/ (exactly six pages) -- this loader
never walks a whole documentation site.
"""

import os
import re

from models import Page

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)


def _parse_frontmatter(raw_text):
    match = FRONTMATTER_RE.match(raw_text)
    if not match:
        raise ValueError("page is missing a frontmatter block")

    header_block, body = match.group(1), match.group(2)

    metadata = {}
    for line in header_block.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata, body.strip() + "\n"


def load_pages(docs_dir):
    """Load every .md file directly inside docs_dir into a list of Page."""

    pages = []
    filenames = sorted(f for f in os.listdir(docs_dir) if f.endswith(".md"))

    for filename in filenames:
        path = os.path.join(docs_dir, filename)
        with open(path, "r", encoding="utf-8") as fh:
            raw_text = fh.read()

        metadata, body = _parse_frontmatter(raw_text)

        page = Page(
            page_id=metadata["page_id"],
            sdk_version=metadata["sdk_version"],
            page_type=metadata["page_type"],
            source_file=metadata.get("source_file", filename),
            body=body,
        )
        pages.append(page)

    return pages
