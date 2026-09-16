---
page_id: requests
sdk_version: v3
page_type: reference
source_file: requests.md
---

# Requests

Every call made through `Client.send()` or `Client.stream()` is built into a
`Request` under the hood. Most users never construct a `Request` directly,
but you can pass a `RequestOptions` object to customize low-level behavior.

## RequestOptions

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| headers | dict | {} | false |
| query_params | dict | {} | false |
| body_encoding | string | "json" | false |

`headers` lets you add or override HTTP headers for a single call.
`query_params` adds query-string parameters to the request URL.
`body_encoding` controls how the request body is serialized; the only other
supported value besides `"json"` is `"form"`.

### Example

```python
from acme_sdk import Client, RequestOptions

client = Client(api_key="sk_live_example")

options = RequestOptions(
    headers={"X-Trace-Id": "abc123"},
    body_encoding="json",
)

response = client.send(message="hello", options=options)
```

## Idempotency

Passing the same `X-Idempotency-Key` header on two calls to `Client.send()`
guarantees the second call will not be processed twice, even if the first
response was lost due to a network error.
