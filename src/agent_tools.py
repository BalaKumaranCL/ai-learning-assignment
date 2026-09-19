"""The three tools available to both the agent and the fixed workflow --
each backed by real data (docs/*.md, data/openapi_spec.json,
data/changelog.json) and each scoped to exactly one job, so a tool-calling
model (real or simulated -- see llm_sim.py) is never left guessing which of
two similar-sounding tools to call.

search_docs         -- prose guides and examples (docs/*.md + legacy v2 text)
get_openapi_spec    -- the authoritative parameter schema for one named
                        endpoint/object, for one SDK version
check_deprecation   -- deprecation status + replacement name for one named
                        endpoint/method/parameter, for one SDK version (the
                        third tool required by this week's task)

No two of these ever answer the same question: search_docs never returns a
parameter schema, get_openapi_spec never mentions deprecation, and
check_deprecation never returns a parameter list.
"""

import json
import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from fusion_retriever import RRFRetriever
from legacy_v2 import build_legacy_v2_chunks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(BASE_DIR, "data")

API_VERSIONS = ("v2", "v3")


def _load_json(name):
    with open(os.path.join(DATA_DIR, name), "r", encoding="utf-8") as fh:
        return json.load(fh)


_OPENAPI_SPEC = _load_json("openapi_spec.json")
_CHANGELOG = _load_json("changelog.json")["deprecations"]
_CHANGELOG_BY_NAME = {entry["name"]: entry for entry in _CHANGELOG}


def _build_search_index():
    """v3 pages via the structure-aware chunker (the winning strategy from
    Week 3/4) plus the two simulated v2 legacy chunks, so search_docs can
    answer both current-docs and migration-flavored prose questions."""

    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    chunks = chunks + build_legacy_v2_chunks()
    return RRFRetriever(chunks)


_SEARCH_INDEX = _build_search_index()


TOOLS = [
    {
        "name": "search_docs",
        "description": (
            "Search the prose documentation (conceptual guides, reference pages, and "
            "usage examples) for how a feature, class, or parameter is described and "
            "used in practice. Returns the best-matching passages, ranked by "
            "relevance. Do not use this to get the authoritative parameter schema of "
            "a named endpoint -- use get_openapi_spec for that. Do not use this to "
            "check whether a name is deprecated or find its replacement -- use "
            "check_deprecation for that."
        ),
        "parameters": {
            "query": {"type": "string", "required": True, "description": "Natural-language search text."},
            "sdk_version": {
                "type": "string",
                "enum": list(API_VERSIONS),
                "required": False,
                "description": "Restrict results to one SDK version's pages.",
            },
        },
    },
    {
        "name": "get_openapi_spec",
        "description": (
            "Look up the exact, authoritative parameter schema -- names, types, "
            "defaults, and which are required -- for one named endpoint or config "
            "object, straight from the OpenAPI spec for one SDK version. Do not use "
            "this for prose explanations or usage examples -- use search_docs for "
            "that. Do not use this to check deprecation status or find a replacement "
            "name -- use check_deprecation for that."
        ),
        "parameters": {
            "endpoint": {
                "type": "string",
                "required": True,
                "description": "Exact endpoint/object name, e.g. 'Client.send' or 'AuthConfig'.",
            },
            "api_version": {"type": "string", "enum": list(API_VERSIONS), "required": True},
        },
    },
    {
        "name": "check_deprecation",
        "description": (
            "Check whether one exact named endpoint, method, or parameter is "
            "deprecated as of a given SDK version, and if so, return only the "
            "replacement's name and a one-line reason. Do not use this to fetch a "
            "parameter schema -- use get_openapi_spec for that. Do not use this to "
            "search prose documentation -- use search_docs for that."
        ),
        "parameters": {
            "name": {
                "type": "string",
                "required": True,
                "description": "Exact dotted name, e.g. 'Client.sendMessage' or 'AuthConfig.token'.",
            },
            "api_version": {"type": "string", "enum": list(API_VERSIONS), "required": True},
        },
    },
]

TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def search_docs(query, sdk_version=None):
    if sdk_version is not None and sdk_version not in API_VERSIONS:
        raise ValueError(f"sdk_version must be one of {API_VERSIONS}, got {sdk_version!r}")
    results = _SEARCH_INDEX.search(query, top_k=3, sdk_version=sdk_version)
    return {
        "query": query,
        "sdk_version": sdk_version,
        "results": [
            {"source_file": r.chunk.source_file, "anchor": r.chunk.anchor, "text": r.chunk.text}
            for r in results
        ],
    }


def get_openapi_spec(endpoint, api_version):
    if api_version not in API_VERSIONS:
        raise ValueError(f"api_version must be one of {API_VERSIONS}, got {api_version!r}")
    entry = _OPENAPI_SPEC[api_version].get(endpoint)
    if entry is None:
        return {"endpoint": endpoint, "api_version": api_version, "found": False, "parameters": []}
    return {"endpoint": endpoint, "api_version": api_version, "found": True, "parameters": entry["parameters"]}


def check_deprecation(name, api_version):
    if api_version not in API_VERSIONS:
        raise ValueError(f"api_version must be one of {API_VERSIONS}, got {api_version!r}")
    entry = _CHANGELOG_BY_NAME.get(name)
    if entry is None or entry["deprecated_in"] != api_version:
        return {
            "name": name,
            "api_version": api_version,
            "deprecated": False,
            "replacement": None,
            "lookup_key": None,
            "note": None,
        }
    return {
        "name": name,
        "api_version": api_version,
        "deprecated": True,
        "replacement": entry["replacement"],
        "lookup_key": entry["lookup_key"],
        "note": entry["note"],
    }


CALLABLES = {
    "search_docs": search_docs,
    "get_openapi_spec": get_openapi_spec,
    "check_deprecation": check_deprecation,
}


def call_tool(name, arguments):
    fn = CALLABLES.get(name)
    if fn is None:
        raise ValueError(f"unknown tool {name!r}")
    return fn(**arguments)
