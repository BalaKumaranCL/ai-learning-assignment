# Foreign-client transcript (reviewer_client.py)

Connected to server **acme-sdk-docs**.

## 1. tools/list (nothing assumed)

- `search_docs(query, sdk_version, kind, top_k, trace_id, parent_span_id)` - Search the Acme SDK documentation for ONE caller's SDK version and return the best-matching passages.
- `lookup_deprecation(symbol, sdk_version, trace_id, parent_span_id)` - Changelog lookup for ONE method, class or argument (for example "Client.sendMessage" or "AuthConfig.token"): when it was introduced, deprecated and removed, and what replaces it (and since which version the replacement exists).
- `symbol_exists(symbol, sdk_version, trace_id, parent_span_id)` - Symbol check: does ONE named method, class or argument exist in ONE SDK version? Returns exactly one of current, deprecated, removed, not_yet or unknown, plus the nearest real names when it is not current.

## 2. search_docs for a 2.4 caller

**call** `search_docs({"query": "how do I paginate through my messages", "sdk_version": "2.4", "trace_id": "reviewer-trace-0001"})` -> ok
scope: `major v2 and range 2.4`; version applied: `2.4`
- v2:pagination::structure::0  (v2, valid 2.0-2.99, reference)  <https://docs.acme-sdk.example/2.x/pagination#pagination-acme-sdk-2-x>
- v2:client::structure::2  (v2, valid 2.0-2.99, reference)  <https://docs.acme-sdk.example/2.x/client#parameters>
- v2:streaming::structure::2  (v2, valid 2.0-2.99, reference)  <https://docs.acme-sdk.example/2.x/streaming#parameters>
server span: trace_id=`reviewer-trace-0001` latency=59.58 ms (the trace id we sent came back)

## 3. the same question for a 3.0 caller (must return different pages)

**call** `search_docs({"query": "how do I paginate through my messages", "sdk_version": "3.0", "trace_id": "reviewer-trace-0001"})` -> ok
- v3:pagination::structure::0  (v3, valid 3.0-3.99)
- v3:streaming::structure::2  (v3, valid 3.0-3.99)
- v3:client::structure::2  (v3, valid 3.0-3.99)

## 4. no version at all (the server must refuse, not guess)

**call** `search_docs({"query": "how do I paginate through my messages"})` -> ERROR
isError=True: Error executing tool search_docs: VERSION_REQUIRED: search_docs needs the caller's SDK version in `sdk_version` (for example '2.4' or '3.0'). 2.x and 3.0 are both live and have different APIs, so I will not guess one. Resolve the version first (pip show acme-s

## 5. a method that never existed, and one that was removed

**call** `symbol_exists({"symbol": "Client.query", "sdk_version": "3.0"})` -> ok
`Client.query` in 3.0: **unknown**; nearest real names: ['Client.send', 'Client.close', 'Client.stream']
**call** `symbol_exists({"symbol": "Client.pollStream", "sdk_version": "3.0"})` -> ok
`Client.pollStream` in 3.0: **removed**; nearest real names: ['Client.stream', 'Client.close', 'Client.send']

## 6. lifecycle of a deprecated method

**call** `lookup_deprecation({"symbol": "Client.sendMessage", "sdk_version": "2.4"})` -> ok
`Client.sendMessage` on 2.4: **deprecated**, deprecated 2.4, removed 3.0, replacement `Client.send` (since 2.2)
