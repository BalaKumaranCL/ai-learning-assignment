---
page_id: migration
sdk_version: v3
page_type: migration
source_file: migration_v2_to_v3.md
---

# Migrating from 2.x to 3.0

Acme SDK 3.0 removes every method and argument that 2.x had already marked
deprecated. Code that imports cleanly on 3.0 can still fail at runtime if it
calls one of them, so check this page before you upgrade. Each replacement
below already exists in the 2.x version noted, so you can switch **before**
upgrading.

## What was removed in 3.0

| Removed in 3.0 | Use instead | Replacement available since |
|---|---|---|
| Client.sendMessage() | Client.send() | 2.2 |
| Client.pollStream() | Client.stream() | 2.4 |
| AuthConfig(token=...) | AuthConfig(api_key=...) | 2.5 |
| RequestOptions(custom_headers=...) | RequestOptions(headers=...) | 2.5 |
| Client.list_messages(page=..., per_page=...) | Client.list_messages(limit=..., cursor=...) | 2.6 |
| ListResult.page and ListResult.total_pages | ListResult.next_cursor | 2.6 |

## Sending a message

`Client.sendMessage()` no longer exists in 3.0. Rename the call to
`Client.send()`; the request shape is unchanged.

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")
reply = client.send(message="hello")
print(reply.body)
```

## Streaming a reply

`Client.pollStream()` no longer exists in 3.0. The manual poll-in-a-loop
pattern is replaced by `Client.stream()`, an iterator you can `for` over.

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")
for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
```

## Authenticating

`AuthConfig(token=...)` no longer exists in 3.0. Pass the same string as
`api_key`.

## Paging through results

Page-number paging was removed in 3.0. Use `limit` and the `next_cursor` of
the previous result.

## Defaults that changed

| Setting | 2.x default | 3.0 default |
|---|---|---|
| Client.send() timeout_ms | 20000 | 30000 |
| Client.send() retry_backoff_ms | 500 | 1000 |
| Client.send() max_retries | not available | 3 |
