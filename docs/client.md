---
page_id: client
sdk_version: v3
page_type: reference
source_file: client.md
---

# Client

The `Client` is the main entry point for the Acme SDK. Every request to the
Acme API is made through a `Client` instance. A client holds your
authentication credentials and default settings, and exposes methods such as
`send()` and `stream()` for talking to the API.

## Client.send()

`Client.send()` sends a single message to the Acme API and waits for a
response. Use it for simple, non-streaming calls where you want the full
reply before continuing.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| timeout_ms | integer | 30000 | false |
| retry_backoff_ms | integer | 1000 | false |
| max_retries | integer | 3 | false |

`message` is the text payload sent to the API. `timeout_ms` controls how long
the client waits before giving up on a single attempt. `retry_backoff_ms` is
the base delay used between retry attempts after a failed call.
`max_retries` caps how many times the client will retry before raising an
error.

### Example

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")

response = client.send(
    message="hello",
    timeout_ms=5000,
    retry_backoff_ms=2000,
)

print(response.body)
```

In this example the caller overrides both `timeout_ms` and
`retry_backoff_ms`, passing `retry_backoff_ms=2000` instead of relying on the
default of `1000`.

## Client.close()

`Client.close()` releases the underlying network connection pool. Call it
when you are done using a client, for example at the end of a script or in a
`finally` block. It takes no parameters and returns nothing.
