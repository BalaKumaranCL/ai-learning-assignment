---
page_id: streaming
sdk_version: v2
page_type: reference
source_file: streaming_v2.md
---

# Streaming (Acme SDK 2.x)

## Client.pollStream()
<!-- valid: 2.0-2.99 -->

`Client.pollStream()` is the original way to get a reply piece by piece: it
returns a poller that you ask for the next piece in a loop until it reports
`done`. **Deprecated in 2.4 and removed in 3.0** - use `Client.stream()`
instead (available since 2.4).

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| poll_interval_ms | integer | 250 | false |

### Example

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
stream = client.pollStream("hello")
while not stream.done:
    print(stream.next().text, end="")
```

## Client.stream()
<!-- valid: 2.4-2.99 -->

`Client.stream()` sends a message the same way `Client.send()` does, but
instead of waiting for the full reply it returns an iterator that yields
`StreamChunk` objects as they arrive from the server. Use it when you want to
show partial output to a user as soon as it is available. It replaces
`Client.pollStream()` (added in 2.4).

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| timeout_ms | integer | 20000 | false |
| chunk_size | integer | 512 | false |

### Example (2.4)
<!-- valid: 2.4-2.4 -->

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
```

### Example (2.5 and later)
<!-- valid: 2.5-2.99 -->

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")
for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
```

## StreamChunk
<!-- valid: 2.4-2.99 -->

Each `StreamChunk` yielded by `Client.stream()` has a `text` field holding
the partial text for that chunk, and an `is_final` boolean that is `true` on
the last chunk of the stream.
