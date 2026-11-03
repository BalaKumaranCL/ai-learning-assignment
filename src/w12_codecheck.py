"""Week 12 (and its bonus): "stop judging code, start executing the check".

For one code sample and one SDK version, answer four questions with a parser
and a symbol table -- no model, no opinion:

  1. does it PARSE?                          (ast.parse)
  2. do its IMPORTS resolve in that version? (`from acme_sdk import X`: X must
                                              exist there; only stdlib + acme_sdk allowed)
  3. does every METHOD / ARGUMENT / ATTRIBUTE it uses exist in that version?
                                             (corpus/symbols.json, see w12_symbols.py)
  4. does it actually RUN against a stub of that version's SDK?
                                             (no network; a call that does not exist
                                              raises AttributeError / TypeError exactly
                                              as the real package would)

`check_code(code, "2.4")` -> {ok, problems[], warnings[], symbols_used[]}.
A DEPRECATED symbol is a warning (it still runs); a REMOVED / not-yet-added /
unknown one is a problem. `ok` means: parses, imports resolve, symbols exist,
and it ran.

The stub is generated from the same manifest the static check reads, so the
two layers can disagree only if the code does something the static pass cannot
type (that disagreement is itself reported by run_w12.py's bonus section).

SAFETY: samples come from this repo's own corpus (or the engine's own output),
and run with a restricted `__import__` and no `open`/`eval`/`exec`. It is not a
hardened sandbox -- do not feed it code from strangers.
"""

import ast
import builtins
import re
import sys
import types

import w12_symbols as sym
from w12_versions import fmt, parse

CODE_FENCE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)
STDLIB = set(getattr(sys, "stdlib_module_names", ())) or {"time", "json", "os", "typing", "math", "logging"}
EXEC_ALLOWED_IMPORTS = {"time", "json", "typing", "math", "logging", "itertools", "functools", "collections"}
CLIENT_NAME_GUESSES = {"client", "cli"}


def extract_code_blocks(markdown):
    return CODE_FENCE_RE.findall(markdown or "")


def _ver(version):
    v = parse(version) if not isinstance(version, tuple) else version
    return (v[0], v[1] if v[1] is not None else 0)


class _Checker(ast.NodeVisitor):
    def __init__(self, version):
        self.v = version
        self.problems, self.warnings, self.used = [], [], []
        self.types = {}          # variable name -> type name
        self.imported = {}       # local name -> acme_sdk export id

    # ---- helpers ----
    def problem(self, kind, detail, node=None):
        line = getattr(node, "lineno", None)
        self.problems.append({"kind": kind, "detail": detail, "line": line})

    def note_symbol(self, sid, node, what):
        """Record a symbol use; deprecated -> warning, anything not usable -> problem."""
        self.used.append(sid)
        st = sym.status(sid, self.v)
        rec = sym.lifecycle(sid) or {}
        if st == "deprecated":
            self.warnings.append({"symbol": sid, "kind": "deprecated", "deprecated": rec.get("deprecated"),
                                  "removed": rec.get("removed"), "replacement": rec.get("replacement"), "line": getattr(node, "lineno", None)})
        elif st == "removed":
            self.problem("symbol", f"{what} was removed in {rec.get('removed')} (not available in {fmt(self.v)})"
                         + (f"; use {rec.get('replacement')}" if rec.get("replacement") else ""), node)
        elif st == "not_yet":
            self.problem("symbol", f"{what} only exists from {rec.get('introduced')} (caller is on {fmt(self.v)})", node)
        elif st == "unknown":
            self.problem("symbol", f"{what} does not exist in any 2.x or 3.0 release", node)
        return st in ("current", "deprecated")

    def type_of(self, node):
        if isinstance(node, ast.Name):
            if node.id in self.types:
                return self.types[node.id]
            if node.id in CLIENT_NAME_GUESSES and node.id not in self.imported:
                return "Client"
            return None
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name) and self.imported.get(f.id) in ("Client", "AuthConfig", "RequestOptions"):
                return self.imported[f.id]
            if isinstance(f, ast.Attribute):
                t = self.type_of(f.value)
                if t:
                    m = sym.member(f"{t}.{f.attr}")
                    if m and m.get("returns"):
                        return m["returns"]
        return None

    # ---- imports ----
    def visit_Import(self, node):
        for a in node.names:
            root = a.name.split(".")[0]
            if root == "acme_sdk":
                self.imported[a.asname or "acme_sdk"] = "acme_sdk"
            elif root not in STDLIB:
                self.problem("import", f"cannot resolve `import {a.name}` (not stdlib, not acme_sdk)", node)

    def visit_ImportFrom(self, node):
        root = (node.module or "").split(".")[0]
        if root == "acme_sdk":
            for a in node.names:
                if a.name == "*":
                    continue
                if self.note_symbol(a.name, node, f"`from acme_sdk import {a.name}`"):
                    self.imported[a.asname or a.name] = a.name
        elif root not in STDLIB:
            self.problem("import", f"cannot resolve `from {node.module} import ...` (not stdlib, not acme_sdk)", node)

    # ---- assignments / loops give variables a type ----
    def visit_Assign(self, node):
        self.visit(node.value)
        t = self.type_of(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name) and t:
                self.types[target.id] = t

    def visit_For(self, node):
        self.visit(node.iter)
        t = self.type_of(node.iter)
        if t == "StreamIter" and isinstance(node.target, ast.Name):
            self.types[node.target.id] = "StreamChunk"
        for child in node.body + node.orelse:
            self.visit(child)

    # ---- calls: constructors and methods ----
    def visit_Call(self, node):
        f = node.func
        member_id = None
        if isinstance(f, ast.Name) and self.imported.get(f.id) in ("Client", "AuthConfig", "RequestOptions"):
            member_id = self.imported[f.id]
        elif isinstance(f, ast.Attribute):
            t = self.type_of(f.value)
            if t in ("Client", "Poller"):
                member_id = f"{t}.{f.attr}"
                if not self.note_symbol(member_id, node, f"`{t.lower() if t == 'Client' else t}.{f.attr}()`"):
                    member_id = None
            elif isinstance(f.value, ast.Name) and f.value.id in self.imported and self.imported[f.value.id] == "acme_sdk":
                self.note_symbol(f.attr, node, f"`acme_sdk.{f.attr}`")
        if member_id:
            self._check_arguments(member_id, node)
        self.generic_visit(node)

    def _check_arguments(self, member_id, node):
        m = sym.member(member_id)
        if not m:
            return
        params = m.get("params", [])
        available = [p for p in params if sym.status(f"{member_id}.{p['name']}", self.v) in ("current", "deprecated")]
        npos = len(node.args)
        if npos > len(available):
            self.problem("param", f"`{member_id}` takes at most {len(available)} positional arguments in {fmt(self.v)}, got {npos}", node)
        passed = {available[i]["name"] for i in range(min(npos, len(available)))}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            pid = f"{member_id}.{kw.arg}"
            if not any(p["name"] == kw.arg for p in params):
                self.problem("param", f"`{member_id}` has no argument `{kw.arg}` in any version", kw)
                continue
            self.note_symbol(pid, kw, f"argument `{kw.arg}` of `{member_id}`")
            passed.add(kw.arg)
        for p in available:
            if p.get("required") and p["name"] not in passed:
                self.problem("param", f"`{member_id}` is missing required argument `{p['name']}`", node)
        for group in m.get("one_of", []):
            usable = [g for g in group if sym.status(f"{member_id}.{g}", self.v) in ("current", "deprecated")]
            if usable and not (set(usable) & passed):
                self.problem("param", f"`{member_id}` needs one of {usable} in {fmt(self.v)}", node)

    # ---- attribute reads on typed values ----
    def visit_Attribute(self, node):
        self.generic_visit(node)
        t = self.type_of(node.value)
        if t and t not in ("Client", "AuthConfig", "RequestOptions"):
            attrs = sym.type_attrs(t)
            if attrs and any(a["name"] == node.attr for a in attrs):
                self.note_symbol(f"{t}.{node.attr}", node, f"`.{node.attr}` on a {t}")
            elif attrs and t in ("Response", "StreamChunk", "PollChunk", "ListResult", "Poller"):
                self.problem("symbol", f"`.{node.attr}` does not exist on a {t} in any 2.x or 3.0 release", node)


def static_check(code, version):
    v = _ver(version)
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return {"problems": [{"kind": "syntax", "detail": f"does not parse: {e.msg} (line {e.lineno})", "line": e.lineno}],
                "warnings": [], "used": []}
    c = _Checker(v)
    c.visit(tree)

    def dedupe(items):
        seen, out = set(), []
        for it in items:
            key = tuple(sorted((k, str(val)) for k, val in it.items()))
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out

    return {"problems": dedupe(c.problems), "warnings": dedupe(c.warnings), "used": list(dict.fromkeys(c.used))}


# --------------------------------------------------------------------------
# the stub SDK (generated from the same manifest) + restricted exec
# --------------------------------------------------------------------------

class _Budget:
    def __init__(self, n):
        self.n = n

    def tick(self):
        self.n -= 1
        if self.n < 0:
            raise RuntimeError("stub call budget exceeded (possible infinite loop)")


def _guard(type_name, ver, obj, name):
    """Raise AttributeError the way the real package would if `name` is not on `type_name` at `ver`."""
    sid = f"{type_name}.{name}"
    st = sym.status(sid, ver)
    if sym.lifecycle(sid) is not None and st in ("removed", "not_yet"):
        rec = sym.lifecycle(sid)
        why = f"removed in {rec.get('removed')}" if st == "removed" else f"added in {rec.get('introduced')}"
        raise AttributeError(f"'{type_name}' object has no attribute '{name}' ({why}; running as {fmt(ver)})")


def _validate_call(member_id, ver, args, kwargs):
    m = sym.member(member_id)
    if m is None:
        return
    avail = [p for p in m.get("params", []) if sym.status(f"{member_id}.{p['name']}", ver) in ("current", "deprecated")]
    if len(args) > len(avail):
        raise TypeError(f"{member_id}() takes {len(avail)} positional arguments but {len(args)} were given")
    got = {avail[i]["name"] for i in range(len(args))}
    for k in kwargs:
        if not any(p["name"] == k for p in avail):
            raise TypeError(f"{member_id}() got an unexpected keyword argument '{k}' (running as {fmt(ver)})")
        got.add(k)
    for p in avail:
        if p.get("required") and p["name"] not in got:
            raise TypeError(f"{member_id}() missing required argument: '{p['name']}'")
    for group in m.get("one_of", []):
        usable = [g for g in group if any(p["name"] == g for p in avail)]
        if usable and not (set(usable) & got):
            raise TypeError(f"{member_id}() needs one of {usable} (running as {fmt(ver)})")


def make_stub_module(version, budget):
    ver = _ver(version)

    def obj(type_name, **values):
        class _Obj:
            def __getattr__(self, name):
                if name in values:
                    _guard(type_name, ver, self, name)
                    return values[name]
                raise AttributeError(f"'{type_name}' object has no attribute '{name}'")
        _Obj.__name__ = type_name
        return _Obj()

    class _Poller:
        def __init__(self):
            self._left = 3

        @property
        def done(self):
            _guard("Poller", ver, self, "done")
            return self._left <= 0

        def next(self):
            _guard("Poller", ver, self, "next")
            budget.tick()
            self._left -= 1
            return obj("PollChunk", text="hi ")

    class Client:
        def __init__(self, *args, **kwargs):
            _validate_call("Client", ver, args, kwargs)

        def __getattribute__(self, name):
            if not name.startswith("_"):
                _guard("Client", ver, None, name)
            return object.__getattribute__(self, name)

        def sendMessage(self, *a, **k):
            _validate_call("Client.sendMessage", ver, a, k)
            budget.tick()
            return obj("Response", status_code=200, body={"reply": "hi"}, headers={})

        def send(self, *a, **k):
            _validate_call("Client.send", ver, a, k)
            budget.tick()
            return obj("Response", status_code=200, body={"reply": "hi"}, headers={})

        def stream(self, *a, **k):
            _validate_call("Client.stream", ver, a, k)
            budget.tick()
            return iter([obj("StreamChunk", text="hi ", is_final=False), obj("StreamChunk", text="there", is_final=True)])

        def pollStream(self, *a, **k):
            _validate_call("Client.pollStream", ver, a, k)
            budget.tick()
            return _Poller()

        def list_messages(self, *a, **k):
            _validate_call("Client.list_messages", ver, a, k)
            budget.tick()
            if "page" in k or (a and not k):
                page = k.get("page", a[0] if a else 1)
                return obj("ListResult", items=["m1", "m2"], page=page, total_pages=3, next_cursor=None if page >= 3 else f"c{page}")
            cur = k.get("cursor")
            nxt = {None: "c1", "c1": "c2", "c2": None}.get(cur)
            return obj("ListResult", items=["m1", "m2"], page=1, total_pages=3, next_cursor=nxt)

        def close(self):
            _validate_call("Client.close", ver, (), {})

    class _Config:
        _id = ""

        def __init__(self, *a, **k):
            _validate_call(self._id, ver, a, k)

    class AuthConfig(_Config):
        _id = "AuthConfig"

    class RequestOptions(_Config):
        _id = "RequestOptions"

    class AcmeError(Exception):
        pass

    mod = types.ModuleType("acme_sdk")
    classes = {"Client": Client, "AuthConfig": AuthConfig, "RequestOptions": RequestOptions, "AcmeError": AcmeError,
               "TimeoutError": type("TimeoutError", (AcmeError,), {}), "RateLimitError": type("RateLimitError", (AcmeError,), {}),
               "AuthError": type("AuthError", (AcmeError,), {}), "ValidationError": type("ValidationError", (AcmeError,), {}),
               "Response": type("Response", (), {}), "StreamChunk": type("StreamChunk", (), {})}
    for name, cls in classes.items():
        if sym.exists(name, ver) or sym.lifecycle(name) is None:
            setattr(mod, name, cls)
    return mod


def run_in_stub(code, version, max_calls=200):
    """Execute `code` against the stub SDK for `version`. -> (ran_ok, error_text)"""
    budget = _Budget(max_calls)
    module = make_stub_module(version, budget)

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".")[0]
        if root == "acme_sdk":
            for item in fromlist or ():
                if item != "*" and not hasattr(module, item):
                    raise ImportError(f"cannot import name '{item}' from 'acme_sdk' (running as {fmt(_ver(version))})")
            return module
        if root in EXEC_ALLOWED_IMPORTS:
            return builtins.__import__(name, globals, locals, fromlist, level)
        raise ImportError(f"No module named '{name}'")

    safe = {k: v for k, v in vars(builtins).items()
            if k not in ("open", "exec", "eval", "compile", "input", "breakpoint", "exit", "quit", "help", "__import__")}
    safe["__import__"] = guarded_import
    ns = {"__builtins__": safe, "__name__": "__sample__"}
    out = sys.stdout
    try:
        sys.stdout = _Null()
        exec(compile(code, "<sample>", "exec"), ns)
        return True, ""
    except BaseException as e:  # noqa: BLE001 -- we are reporting every failure of the sample, whatever it is
        return False, f"{type(e).__name__}: {e}"
    finally:
        sys.stdout = out


class _Null:
    def write(self, *_):
        return 0

    def flush(self):
        pass


def check_code(code, version, run=True):
    """The one function the rest of the project calls."""
    res = static_check(code, version)
    problems = list(res["problems"])
    ran = None
    if run and not any(p["kind"] in ("syntax", "import") for p in problems):
        ok, err = run_in_stub(code, version)
        ran = ok
        if not ok:
            problems.append({"kind": "exec", "detail": f"fails when run against {fmt(_ver(version))}: {err}", "line": None})
    return {"ok": not problems, "problems": problems, "warnings": res["warnings"],
            "symbols_used": res["used"], "ran": ran, "version": fmt(_ver(version))}


def check_markdown(markdown, version, run=True):
    """Check every ```python block in an answer. -> {ok, blocks, problems, warnings}; ok=True when there are no blocks."""
    blocks = extract_code_blocks(markdown)
    results = [check_code(b, version, run=run) for b in blocks]
    return {
        "ok": all(r["ok"] for r in results),
        "blocks": len(blocks),
        "problems": [dict(p, block=i) for i, r in enumerate(results) for p in r["problems"]],
        "warnings": [dict(w, block=i) for i, r in enumerate(results) for w in r["warnings"]],
        "symbols_used": list(dict.fromkeys(s for r in results for s in r["symbols_used"])),
    }
