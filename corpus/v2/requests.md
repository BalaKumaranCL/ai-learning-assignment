---
page_id: requests
sdk_version: v2
page_type: reference
source_file: requests_v2.md
---

# Requests (Acme SDK 2.x)

Every call made through `Client.send()` or `Client.stream()` is built into a
`Request` under the hood. Most users never construct a `Request` directly,
but you can pass a `RequestOptions` object to customize low-level behavior.
`RequestOptions` can only be passed to `Client.send()`, so everything on this
page needs 2.2 or later.
<!-- valid: 2.2-2.99 -->

## RequestOptions with custom_headers
<!-- valid: 2.2-2.4 -->

Up to 2.4, extra HTTP headers are passed as `custom_headers`.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| custom_headers | dict | {} | false |
| query_params | dict | {} | false |

`custom_headers` lets you add or override HTTP headers for a single call.
`query_params` adds query-string parameters to the request URL.

### Example
<!-- valid: 2.2-2.4 -->

```python
from acme_sdk import Client, AuthConfig, RequestOptions

client = Client(auth=AuthConfig(token="sk_live_example"))
options = RequestOptions(custom_headers={"X-Trace-Id": "abc123"})
response = client.send(message="hello", options=options)
```

## RequestOptions with headers
<!-- valid: 2.5-2.99 -->

From 2.5 the argument is called `headers`. **`custom_headers` is deprecated in
2.5 and removed in 3.0**; `headers` is the same dict type and default.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| headers | dict | {} | false |
| query_params | dict | {} | false |

### Example

```python
from acme_sdk import Client, RequestOptions

client = Client(api_key="sk_live_example")
options = RequestOptions(headers={"X-Trace-Id": "abc123"})
response = client.send(message="hello", options=options)
```

## Idempotency
<!-- valid: 2.2-2.99 -->

Passing the same `X-Idempotency-Key` header on two calls to `Client.send()`
guarantees the second call will not be processed twice, even if the first
response was lost due to a network error.
