# Week 9 -- error_before_after.md

Same failing call both times: `Search the docs for a Client.send example on sdk v4.` -> `search_docs(sdk_version="v4")`. There is no v4 doc set; the only change between runs is the server's docstring + error text (`DOCS_SERVER_STYLE=legacy|prompt`, `mcp_servers/docs_search_server.py`). Agent code is identical in both runs.

> The model in this repo is the deterministic stand-in `src/mcp_llm_sim.py` (no live LLM anywhere in this project). Its AFTER behavior (read a `retry_with:` hint and retry) is real code reacting to the real server text. Its BEFORE behavior on an opaque `Error N` (fall back on a stale v2-era sample) is MODELLED on the failure the brief names, not observed from a real model -- read it as an illustration of what the rewrite prevents.

## BEFORE -- terse docstring, opaque error

tools/list description the model saw: `Search docs.`

```
  lap 1: tools/call docs-search::search_docs({"query": "Search the docs for a Client.send example on sdk v4.", "sdk_version": "v4"}) -> ERROR
      Error executing tool search_docs: Error 3
  FINAL ANSWER:
      Here is a sample based on what I remember of the SDK:
          client = Client(AuthConfig(token=TOKEN))
          reply = client.sendMessage(prompt)
      (No source consulted.)
```

## AFTER -- docstring written as a prompt, recoverable diagnostic

tools/list description the model saw:

```
Search the Acme SDK prose documentation (guides, reference pages, usage examples) and return the best-matching passages.

WHEN TO USE: the user wants to know how a feature works or wants an example. Phrase `query` as a natural-language search.
WHEN NOT TO USE: for the exact parameter list of a named endpoint use get_openapi_spec; for package release dates or deprecation of a package version use the package/registry tools if you have them.
`sdk_version` is optional and must be one of v2, v3; omit it to search everything. The latest published docs are v3.
IF YOU GET AN ERROR: it starts with a KIND. UNSUPPORTED_VERSION means that version has no docs -- read the message, it names the latest published version and a retry_with value; retry once with that value and tell the user which version the answer is actually for. Never answer from memory of an older SDK version.
```

```
  lap 1: tools/call docs-search::search_docs({"query": "Search the docs for a Client.send example on sdk v4.", "sdk_version": "v4"}) -> ERROR
      Error executing tool search_docs: UNSUPPORTED_VERSION: no docs for v4 -- latest published is v3 (also available: v2, deprecated). Renamed/deprecated v2 methods and their v3 replacements are listed in resource docs://version-support-matrix. The docs service itself is up; v4 does not exist yet. retry_with: sdk_version=v3
  lap 2: tools/call docs-search::search_docs({"query": "Search the docs for a Client.send example on sdk v4.", "sdk_version": "v3"}) -> ok
      [client.md > Client]
      # Client
      
      The `Client` is the main entry point for the Acme SDK. Every request to the
      Acme API is made through a `Client` instance. A client holds your
      authentication credentials and default settings, and exposes methods such as
      `send()` and `stream()` for talking to the API.
      
      [client.md > Client > Client.send() > Example]
      ### Example
      
      ```python
      from acme_sdk import Client
      
      client = Client(api_key="sk_live_example")
      
      response = client.send(
          message="hello",
          t
  FINAL ANSWER:
      Note: my first call failed (Error executing tool search_docs: UNSUPPORTED_VERSION: no docs for v4 -- latest published is v3 (also available: v2, deprecated).); I retried with {'sdk_version': 'v3'}, so this answer is for that, not for what was originally asked.
      [client.md > Client]
      # Client
      
      The `Client` is the main entry point for the Acme SDK. Every request to the
      Acme API is made through a `Client` instance. A client holds your
      authentication credentials and default settings, and exposes methods such as
      `send()` and `stream()` for talking to the API.
      
      [client.md > Client > Client.send() > Example]
      ### Example
      
      ```pytho
```

## What moved

| | before | after |
|---|---|---|
| tool calls | 1 (failed) | 2 (1 failed, 1 recovered) |
| model can tell 'v4 does not exist' from 'service down' | no (`Error 3`) | yes (`UNSUPPORTED_VERSION`, 'service itself is up') |
| answer cites a source | no | yes |
| answer uses deprecated v2 `sendMessage` | yes | no |
| answer tells the user which version it is really for | no | yes |
