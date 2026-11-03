"""Week 12 tests. Units first (fast, no MCP), then the integrated system through a live MCP server (skipped without `mcp`)."""

import json
import os
import re

import pytest

import w12_codecheck as cc
import w12_guards as G
import w12_index as ix
import w12_redact as red
import w12_symbols as sym
import w12_versions as V

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "output", "w12")


def _json(*parts):
    with open(os.path.join(BASE, *parts), "r", encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ versions
@pytest.mark.parametrize("q,meta,want,source", [
    ("How do I paginate?", "2.4.1", "2.4", "request_metadata"),
    ("pip freeze shows acme-sdk==2.4.1. How do I stream?", None, "2.4", "pinned_in_text"),
    ("I'm on 2.6 and want to loop through messages. How?", None, "2.6", "stated_in_text"),
    ("I'm on v2. How do I send a message?", None, "2.0", "stated_in_text"),          # a sentence-ending period must not hide "v2"
    ("AttributeError: 'Client' object has no attribute 'sendMessage'", None, "3.0", "inferred_from_error"),
    ("TypeError: unexpected keyword argument 'api_key'", None, "2.0", "inferred_from_error"),
])
def test_resolver_sources(q, meta, want, source):
    r = V.resolve_version(q, meta)
    assert (r["version"], r["source"]) == (want, source)


def test_resolver_never_guesses():
    assert V.resolve_version("How do I send a message?")["version"] is None
    # api_key= works on 2.5+ AND on 3.0: it narrows nothing, so the resolver must stay silent
    assert V.resolve_version("AuthConfig(api_key='x') fails")["version"] is None


def test_a_mention_is_not_a_use():
    r = V.resolve_version("Does client.pollStream still work in 3.0?")
    assert r["version"] is None and r["target_version"] == "3.0"           # S9: naming a method says nothing about your version


def test_naive_resolver_defaults_to_latest():
    assert V.resolve_version("How do I send a message?", None, smart=False)["source"] == "defaulted_latest"


# ------------------------------------------------------------------ symbols
def test_lifecycle_of_the_four_renames():
    assert sym.status("Client.sendMessage", "2.3") == "current"
    assert sym.status("Client.sendMessage", "2.4") == "deprecated"
    assert sym.status("Client.sendMessage", "3.0") == "removed"
    assert sym.status("AuthConfig.api_key", "2.4") == "not_yet"
    assert sym.status("Client.query", "3.0") == "unknown"
    assert sym.status("Client.send", "2.1") == "not_yet" and sym.status("Client.send", "2.2") == "current"


def test_reverse_lookup_finds_what_a_name_replaced():
    assert any(x["symbol"] == "Client.pollStream" for x in sym.record("Client.stream", "2.4")["replaces"])


def test_every_week7_changelog_name_is_in_the_new_table_as_removed_in_3_0():
    for e in _json("data", "changelog.json")["deprecations"]:
        assert sym.lifecycle(e["name"]) is not None, e["name"]
        assert sym.lifecycle(e["name"])["removed"] == "3.0"


def test_extract_symbols_ignores_english():
    assert not sym.extract_symbols("Use the client. It works. We call c. Then stop.")
    assert any(h["id"] == "Client.query" and h["status_kind"] == "unknown" for h in sym.extract_symbols("how do I use client.query() here"))


# ------------------------------------------------------------------ redaction
@pytest.mark.parametrize("secret", [
    "sk_live_9aXk2Qm7LpR4tZ3vB8nC", "postgres://admin:hunter2Pass@db.internal:5432/prod",
    "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyMSJ9.c2lnbmF0dXJlMTIz", "dev.person@example.org", "AKIAABCDEFGHIJKLMNOP",
])
def test_redact_removes_secrets(secret):
    clean, found = red.redact(f"my thing is {secret} ok")
    assert secret not in clean and found


def test_redact_keeps_documentation_placeholders():
    assert red.redact('AuthConfig(token="sk_live_example")')[0] == 'AuthConfig(token="sk_live_example")'


def test_redact_deep_and_strip_markers():
    rec = red.redact_deep({"a": ["x sk_live_AAAAAAAAAA y"], "b": {"c": "postgres://u:p@h/db"}})
    assert "sk_live_AAAAAAAAAA" not in json.dumps(rec) and "u:p@h" not in json.dumps(rec)
    assert "[REDACTED" not in red.strip_markers("I use [REDACTED:connection_string] and want to paginate")


# ------------------------------------------------------------------ the code checker (the bonus)
V2_OK = 'from acme_sdk import Client, AuthConfig\nclient = Client(auth=AuthConfig(token="k"))\nclient.send(message="hi")\n'
V3_SNIPPET = 'from acme_sdk import Client\nclient = Client(api_key="k")\nclient.send(message="hi")\n'


def test_code_checker_accepts_the_right_version_and_rejects_the_wrong_one():
    assert cc.check_code(V2_OK, "2.4")["ok"]
    bad = cc.check_code(V3_SNIPPET, "2.4")                 # imports cleanly, fails in the caller's app
    assert not bad["ok"] and any("api_key" in p["detail"] for p in bad["problems"])
    assert cc.check_code(V3_SNIPPET, "3.0")["ok"]


def test_code_checker_removed_unknown_and_deprecated():
    removed = cc.check_code(V2_OK.replace("send(message", "sendMessage(message"), "3.0")
    assert not removed["ok"]
    unknown = cc.check_code('from acme_sdk import Client\nc = Client(api_key="k")\nc.query("x")\n', "3.0")
    assert any("does not exist in any" in p["detail"] for p in unknown["problems"])
    dep = cc.check_code('from acme_sdk import Client, AuthConfig\nclient = Client(auth=AuthConfig(token="k"))\nclient.sendMessage("x")\n', "2.4")
    assert dep["ok"] and any(w["symbol"] == "Client.sendMessage" for w in dep["warnings"])


def test_every_dead_stack_overflow_sample_fails_the_check():
    for line in open(os.path.join(BASE, "corpus", "stackoverflow.jsonl"), encoding="utf-8"):
        rec = json.loads(line)
        for b in cc.extract_code_blocks(rec["body"]):
            assert not cc.check_code(b, "2.4")["ok"], rec["id"]


def test_syntax_error_and_unresolvable_import():
    assert cc.check_code("def (:\n", "2.4")["problems"][0]["kind"] == "syntax"
    assert cc.check_code("import acme\n", "2.4")["problems"][0]["kind"] == "import"


# ------------------------------------------------------------------ the index
@pytest.fixture(scope="module")
def index():
    return ix.ScopedIndex()


@pytest.mark.parametrize("version", [(2, m) for m in range(10)] + [(3, 0)])
def test_scoped_search_never_leaves_scope(index, version):
    for q in ("how do I paginate", "send a message", "stream a reply", "authenticate", "custom header", "timeout"):
        for kinds in ({"reference", "changelog"}, {"sample"}, {"migration", "changelog"}):
            res, _ = index.search(q, version, top_k=5, page_types=kinds)
            for r in res:
                assert ix.applies(r.chunk, version), (q, version, r.chunk.chunk_id)
                assert r.chunk.page_type != "stackoverflow"


def test_stack_overflow_is_never_served_in_strict_mode_but_is_in_the_naive_union(index):
    res, _ = index.search("how to send a text message with the acme python lib", (2, 4), top_k=8, page_types={"reference", "sample", "changelog"})
    assert not any(r.chunk.page_type == "stackoverflow" for r in res)
    lenient, info = index.search("how to send a text message with the acme python lib", None, top_k=3, mode="lenient", bridge=False)
    assert "ALL VERSIONS" in info["scope"] and any(r.chunk.page_type == "stackoverflow" for r in lenient)


def test_the_guard_raises_if_a_chunk_leaks(index):
    res, _ = index.search("paginate", (3, 0), top_k=2, page_types={"reference"})
    with pytest.raises(ix.VersionLeak):
        ix.assert_scoped(res, (2, 4))


def test_the_stemmer_joins_what_tfidf_cannot():
    for a, b in [("retries", "retry"), ("paginate", "pagination"), ("authenticate", "authentication"), ("attempts", "attempt")]:
        assert ix.stem(a) == ix.stem(b)


def test_section_ranges_inherit_and_override(index):
    c = {x.chunk_id: x for x in index.chunks}
    assert (c["v2:client::structure::4"].valid_from, c["v2:client::structure::4"].valid_to) == ("2.2", "2.99")      # Client.send()
    assert (c["v2:client::structure::6"].valid_from, c["v2:client::structure::6"].valid_to) == ("2.2", "2.4")      # its 2.2-2.4 example
    assert c["v2:client::structure::5"].valid_from == "2.2"                                                        # Parameters inherits


def test_corpus_is_clean_and_guards_pass():
    ok1, d1 = G.corpus_code_lint()
    ok2, d2 = G.changelog_covers_table()
    assert ok1, d1
    assert ok2, d2


def test_guard_g02_goes_red_when_the_symbol_table_moves_and_the_docs_do_not(tmp_path, monkeypatch):
    raw = _json("corpus", "symbols.json")
    for m in raw["members"]:
        if m["id"] == "Client.close":
            m["deprecated"], m["replacement"] = "3.1", "Client.shutdown"
    raw["latest"]["3"] = "3.1"
    p = tmp_path / "symbols_3_1.json"
    p.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("W12_MANIFEST", str(p))
    ok, detail = G.changelog_covers_table()
    assert not ok and "Client.close" in detail


# ------------------------------------------------------------------ the data files
def test_case_files_meet_the_brief():
    cases = _json("data", "w12", "eval_cases.json")["cases"]
    assert 25 <= len(cases) + 2 <= 40                                   # + 2 guards
    assert len({c["id"] for c in cases}) == len(cases)
    assert {c["id"] for c in cases if c["expect"].get("xfail")} == {"C07", "C34"}
    assert any(c["expect"].get("canaries") for c in cases) and any(c["category"] == "unknown_symbol" for c in cases)
    assert len(_json("data", "w12", "trajectory_cases.json")["cases"]) >= 10
    labels = {l["id"] for l in _json("data", "w12", "hand_labels.json")["labels"]}
    assert labels == {c["id"] for c in cases}
    ids = {c["id"] for c in cases}
    assert all(t["eval_case"] in ids for t in _json("data", "w12", "trajectory_cases.json")["cases"])


def test_agent_and_composer_hardcode_no_mcp_tool_names():
    for f in ("w12_agent.py", "w12_answer.py", "w12_engine.py"):
        text = open(os.path.join(BASE, "src", f), encoding="utf-8").read()
        for name in ("search_docs", "lookup_deprecation", "symbol_exists"):
            assert name not in text, f"{f} mentions the MCP tool {name!r}: tools must be discovered, not hardcoded"


def test_hand_written_deliverables_exist_and_are_honest():
    for f in ("seams.md", "weaknesses.md", "architecture.md", "demo_script.md", "fresh_eyes.md"):
        assert os.path.exists(os.path.join(OUT, f)), f
    seams = open(os.path.join(OUT, "seams.md"), encoding="utf-8").read()
    assert len(re.findall(r"^Status: \*\*(fixed|accepted|ran-out-of-time)\*\*", seams, re.M)) >= 20
    assert "open  <!--" not in seams                                    # no seam left unmarked
    weak = open(os.path.join(OUT, "weaknesses.md"), encoding="utf-8").read()
    assert len(re.findall(r"^## [123]\. ", weak, re.M)) == 3 and "2026-11-02" in weak
    assert "OPEN" in open(os.path.join(OUT, "fresh_eyes.md"), encoding="utf-8").read()    # we do not pretend a person did it
    assert len(open(os.path.join(OUT, "demo_script.md"), encoding="utf-8").read().split("## ")) >= 5
