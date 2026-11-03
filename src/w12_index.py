"""Week 12: the integrated RAG index -- the Week 3-4 pipeline (loader ->
structure-aware chunker -> TF-IDF + BM25 -> RRF) with VERSION as a metadata
filter that CODE enforces, not words inside a chunk.

What is new on top of Weeks 3-4 (seams S5, S2):
  * every chunk carries valid_from / valid_to (a version RANGE, not just 'v2'),
    read from `<!-- valid: 2.2-2.4 -->` lines in the pages and `# acme-sdk: 2.2-2.4`
    headers in the samples; a section inherits its parent heading's range.
  * one RRF index per major version (v2 / v3). A v2.4 caller's search never
    even SEES a v3 chunk; the 3.0 migration guide is the one deliberate
    cross-over (page_type 'migration', shown to v2 callers as upgrade info
    and cited as "3.0").
  * a range filter after ranking (a 2.4 caller never gets a section added in
    2.6) and `assert_scoped`, a guard that raises VersionLeak if anything
    out of range gets through -- so a bug here is loud, not a wrong snippet.
  * Stack Overflow answers are tagged v1 and live in their OWN index. They are
    never returned as content to a v2/v3 caller. Their one job: the question
    phrasings people really type ("hangs forever") map to the symbol the answer
    was about, and that symbol is added to the query -- recall without ever
    emitting the dead API. The README measures what dropping them would cost.

`mode='lenient'` is the Week-9 behaviour ("no version = search everything",
S2), kept as a switch so the BEFORE can be measured.
"""

import dataclasses
import json
import os
import re
from dataclasses import dataclass, field

import w12_symbols as sym
from w12_text import stem, stem_text  # noqa: F401  (re-exported)
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

from chunkers import StructureAwareChunker
from fusion_retriever import RRFRetriever
from loader import _parse_frontmatter
from models import Chunk, Page
from w12_versions import fmt, in_range, major_tag, parse, parse_exact, parse_range

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_DIR = os.path.join(BASE_DIR, "corpus")
DOCS_V3_DIR = os.path.join(BASE_DIR, "docs")          # Week 3's six pages ARE the 3.0 reference
DOCS_HOST = "https://docs.acme-sdk.example"           # stand-in host (.example is reserved; not a real site)

DEFAULT_RANGE = {"v2": ("2.0", "2.99"), "v3": ("3.0", "3.99"), "v1": ("1.0", "1.99")}
VALID_RE = re.compile(r"<!--\s*valid:\s*(\d+\.\d+)-(\d+\.\d+)\s*-->")
SO_MIN_SIMILARITY = 0.12      # below this the SO phrasing is not a real match; no expansion


class VersionLeak(Exception):
    """A chunk outside the caller's version scope was about to be returned."""


@dataclass
class VChunk(Chunk):
    valid_from: str = "2.0"
    valid_to: str = "2.99"
    url: str = ""
    version_label: str = ""
    symbols: list = field(default_factory=list)
    maps_to: list = field(default_factory=list)   # SO chunks only: symbols the answer was about


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _label(sdk_version):
    return {"v2": "2.x", "v3": "3.0", "v1": "1.x (Stack Overflow)"}[sdk_version]


def _url(sdk_version, chunk):
    if chunk.page_type == "stackoverflow":
        return f"https://stackoverflow.example/q/{chunk.chunk_id.split(':')[-1]}"
    if chunk.page_type == "sample":
        return f"{DOCS_HOST}/{_label(sdk_version)}/samples/{chunk.source_file}"
    anchor = _slug(chunk.anchor.split(" > ")[-1]) if chunk.anchor else ""
    return f"{DOCS_HOST}/{_label(sdk_version)}/{chunk.page_id}" + (f"#{anchor}" if anchor else "")


def _finish(c, sdk_version, lo, hi):
    c.chunk_id = f"{sdk_version}:{c.chunk_id}"        # page_ids repeat across versions ('client' is in both)
    c.valid_from, c.valid_to = lo, hi
    c.version_label = _label(sdk_version)
    c.url = _url(sdk_version, c)
    c.symbols = [h["id"] for h in sym.extract_symbols(c.text) if h["status_kind"] == "known"]
    return c


def _chunk_pages(directory, only_page_ids=None):
    chunker = StructureAwareChunker()
    out = []
    for fn in sorted(f for f in os.listdir(directory) if f.endswith(".md")):
        with open(os.path.join(directory, fn), "r", encoding="utf-8") as fh:
            meta, body = _parse_frontmatter(fh.read())
        page = Page(page_id=meta["page_id"], sdk_version=meta["sdk_version"], page_type=meta["page_type"],
                    source_file=meta.get("source_file", fn), body=body)
        sdk = page.sdk_version
        default = DEFAULT_RANGE[sdk]
        stack = []   # (depth, (lo, hi)): a directive applies to its heading and everything beneath it
        for raw in chunker.chunk_page(page):
            depth = len(raw.anchor.split(" > ")) if raw.anchor else 1
            while stack and stack[-1][0] >= depth:
                stack.pop()
            m = VALID_RE.search(raw.text)
            if m:
                stack.append((depth, (m.group(1), m.group(2))))
            lo, hi = stack[-1][1] if stack else default
            if page.page_type == "migration":
                lo, hi = "2.0", "3.99"      # upgrade info: relevant to anyone on 2.x planning the move, and to 3.0
            c = VChunk(**{k: getattr(raw, k) for k in ("chunk_id", "text", "source_file", "page_id", "sdk_version", "page_type", "anchor", "strategy")})
            out.append(_finish(c, sdk, lo, hi))
    return out


def _load_samples():
    out = []
    for sdk in ("v2", "v3"):
        d = os.path.join(CORPUS_DIR, "samples", sdk)
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".py"):
                continue
            with open(os.path.join(d, fn), "r", encoding="utf-8") as fh:
                raw = fh.read()
            title = re.search(r"# title: (.*)", raw).group(1).strip()
            rng = re.search(r"# acme-sdk: (\S+)", raw).group(1)
            topic = re.search(r"# topic: (\S+)", raw).group(1)
            tags = re.search(r"# tags: (.*)", raw).group(1).strip()
            code = "\n".join(l for l in raw.splitlines() if not re.match(r"# (title|acme-sdk|topic|tags):", l)).strip() + "\n"
            lo, hi = rng.split("-")
            text = f"Sample: {title}\nTags: {tags}\n\n```python\n{code}```\n"    # the tags are indexed: 'paginate' is in no sample's code
            c = VChunk(chunk_id=f"sample::{fn[:-3]}", text=text, source_file=fn, page_id=f"sample_{topic}", sdk_version=sdk,
                       page_type="sample", anchor=f"Samples > {title}", strategy="w12_sample")
            out.append(_finish(c, sdk, lo, hi))
    return out


def _load_stackoverflow():
    out = []
    with open(os.path.join(CORPUS_DIR, "stackoverflow.jsonl"), "r", encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            c = VChunk(chunk_id=f"so::{r['id']}", text=f"{r['title']}\n\n{r['body']}", source_file=f"{r['id']}.html",
                       page_id=r["id"], sdk_version="v1", page_type="stackoverflow", anchor=r["title"], strategy="w12_so",
                       maps_to=r["maps_to"])
            out.append(_finish(c, "v1", "1.0", "1.99"))
    return out


def load_corpus():
    chunks = []
    chunks += _chunk_pages(DOCS_V3_DIR)
    chunks += _chunk_pages(os.path.join(CORPUS_DIR, "v3"))
    chunks += _chunk_pages(os.path.join(CORPUS_DIR, "v2"))
    chunks += _load_samples()
    chunks += _load_stackoverflow()
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "duplicate chunk ids"
    return chunks


def applies(chunk, version):
    """Is this chunk legitimately served to a caller on `version` (a (major, minor) tuple)?"""
    if chunk.page_type == "stackoverflow":
        return False
    if chunk.sdk_version != major_tag(version) and chunk.page_type != "migration":
        return False
    lo, hi = parse_exact(chunk.valid_from), parse_exact(chunk.valid_to)
    return in_range(version, lo, hi)


def assert_scoped(results, version):
    """The guard: raise if ANY returned chunk is out of scope for `version`."""
    for r in results:
        if not applies(r.chunk, version):
            raise VersionLeak(f"chunk {r.chunk.chunk_id} (v{r.chunk.sdk_version} {r.chunk.valid_from}-{r.chunk.valid_to}, "
                              f"{r.chunk.page_type}) is not in scope for {fmt(version)}")


class ScopedIndex:
    def __init__(self, chunks=None):
        self.chunks = chunks or load_corpus()
        self.by_id = {c.chunk_id: c for c in self.chunks}
        # the retrievers index STEMMED shadow copies; results are mapped back to the original chunk before anyone sees them
        shadow = {c.chunk_id: dataclasses.replace(c, text=stem_text(c.text)) for c in self.chunks}

        def build(cs):
            return RRFRetriever([shadow[c.chunk_id] for c in cs])

        docs = [c for c in self.chunks if c.page_type != "stackoverflow"]
        self.v2 = build([c for c in docs if c.sdk_version == "v2" or c.page_type == "migration"])
        self.v3 = build([c for c in docs if c.sdk_version == "v3"])
        self.so = build([c for c in self.chunks if c.page_type == "stackoverflow"])
        self.union = build(self.chunks)      # lenient mode: "search everything" (Week 9's behaviour)
        # vocabulary of the DOCS only (the union index also contains the SO chunks, whose words must not count as 'known')
        self.doc_vocab = set(self.v2.tfidf.vectorizer.vocabulary_) | set(self.v3.tfidf.vectorizer.vocabulary_)

    def _orig(self, scored):
        scored.chunk = self.by_id[scored.chunk.chunk_id]
        return scored

    def vocabulary_gap(self, query_stemmed):
        """Content words (already stemmed) the DOCS never use: 'hangs', 'freezes'. A real vocabulary gap."""
        return [t for t in re.findall(r"[a-z]{4,}", query_stemmed)
                if t not in ENGLISH_STOP_WORDS and t not in self.doc_vocab and not any(w.startswith(t[:5]) for w in self.doc_vocab)]

    # -- Stack Overflow phrasing bridge --
    def so_bridge(self, query_stemmed):
        top = self.so.tfidf.search(query_stemmed, top_k=1)
        if not top or top[0].score < SO_MIN_SIMILARITY:
            return None
        so = self.by_id[top[0].chunk.chunk_id]
        names = []
        for sid in so.maps_to:
            last = sid.split(".")[-1]
            if last != "Client" and last not in names:   # bare 'Client' is in every chunk: no signal
                names.append(last)
            m = sym.member(sid)                           # a method's own argument names are what its docs talk about
            for p in (m or {}).get("params", []):
                if p["name"] not in names and sym.exists(f"{sid}.{p['name']}", (2, 4)) and p["name"] not in ("message", "options"):
                    names.append(p["name"])
        return {"so_id": so.chunk_id, "similarity": round(top[0].score, 3), "maps_to": so.maps_to,
                "expansion": " ".join(names[:6])}

    def search(self, query, version=None, top_k=3, mode="strict", minor_filter=True, page_types=None, bridge=True,
               include_upgrade_info=False):
        """-> (results, info). info says what scope was applied -- it goes into the trace."""
        qs = stem_text(query)
        info = {"mode": mode, "version_requested": fmt(version) if version else None, "minor_filter": minor_filter,
                "so_bridge": None, "leak_blocked": 0,
                "prefix_expansion": [f"{w}->{t}" for w, t in zip(re.findall(r"[A-Za-z]{4,}", query), re.findall(r"[a-z]{4,}", qs))
                                     if w.lower() != t][:6]}
        if page_types is None:
            page_types = {"reference", "sample", "changelog"} | ({"migration"} if include_upgrade_info else set())
        q = qs
        if bridge:
            # Reach for Stack Overflow phrasing only when the question uses words the DOCS never use ("hangs",
            # "freezes"): a real vocabulary gap. Raw cosine is too noisy a trigger on tiny chunks -- an SO title
            # that merely shares the word "reply" would hijack "how do I stream a reply".
            gap = self.vocabulary_gap(qs)
            if gap:
                b = self.so_bridge(qs)
                if b:
                    b["vocabulary_gap"] = gap
                    info["so_bridge"] = b
                    q = f"{q} {stem_text(b['expansion'])}"

        if mode == "lenient" and version is None:
            res = self.union.search(q, top_k=len(self.union.chunks))
            info["scope"] = "ALL VERSIONS (no version supplied)"
        else:
            if version is None:
                raise ValueError("strict mode needs a version")
            index = self.v2 if version[0] == 2 else self.v3
            res = index.search(q, top_k=len(index.chunks))
        res = [self._orig(r) for r in res]
        if not (mode == "lenient" and version is None):
            if minor_filter:
                res = [r for r in res if applies(r.chunk, version)]
            else:
                res = [r for r in res if r.chunk.sdk_version == major_tag(version) or r.chunk.page_type == "migration"]
            info["scope"] = f"major {major_tag(version)}" + (f" and range {fmt(version)}" if minor_filter else " only (no minor filter)")
        res = [r for r in res if r.chunk.page_type in page_types or (mode == "lenient" and r.chunk.page_type == "stackoverflow")]
        res = res[:top_k]
        for i, r in enumerate(res, start=1):
            r.rank = i

        if mode == "strict" and minor_filter:
            try:
                assert_scoped(res, version)
            except VersionLeak:
                info["leak_blocked"] = 1
                raise
        return res, info


def chunk_record(sc):
    """One search hit as the plain dict that crosses the MCP boundary."""
    c = sc.chunk
    return {"rank": sc.rank, "score": round(sc.score, 4), "chunk_id": c.chunk_id, "page_id": c.page_id,
            "page_type": c.page_type, "sdk_version": c.sdk_version, "valid_from": c.valid_from, "valid_to": c.valid_to,
            "anchor": c.anchor, "url": c.url, "version_label": c.version_label, "source_file": c.source_file,
            "symbols": c.symbols, "text": c.text}


_cached = None


def get_index():
    global _cached
    if _cached is None:
        _cached = ScopedIndex()
    return _cached
