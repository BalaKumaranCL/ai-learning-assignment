---
page_id: streaming
sdk_version: v3
page_type: reference
source_file: streaming.md
---

# Streaming

## Client.stream()

`Client.stream()` sends a message the same way `Client.send()` does, but
instead of waiting for the full reply it returns an iterator that yields
`StreamChunk` objects as they arrive from the server. Use it when you want to
show partial output to a user as soon as it is available, instead of
blocking until the entire response is ready.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| timeout_ms | integer | 30000 | false |
| chunk_size | integer | 512 | false |

`message` and `timeout_ms` behave the same as they do on `Client.send()`.
`chunk_size` controls the maximum number of bytes delivered per
`StreamChunk`.

### Example

```python
client = Client(api_key="sk_live_example")

for chunk in client.stream(message="hello"):
    print(chunk.text, end="")
```

## StreamChunk

Each `StreamChunk` yielded by `Client.stream()` has a `text` field holding
the partial text for that chunk, and a `is_final` boolean that is `true` on
the last chunk of the stream.
