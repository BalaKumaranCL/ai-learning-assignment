---
page_id: client
sdk_version: v2
page_type: reference
source_file: client_v2.md
---

# Client (Acme SDK 2.x)

The `Client` is the main entry point for the Acme SDK 2.x. Every request to the
Acme API is made through a `Client` instance. A client holds your
authentication credentials and default settings, and exposes methods such as
`send()` and `stream()` for talking to the API.

## Client.sendMessage()
<!-- valid: 2.0-2.99 -->

`Client.sendMessage()` sends a single message to the Acme API and waits for the
reply. It is the original name of the call. **Deprecated in 2.4 and removed in
3.0** - use `Client.send()` instead (available since 2.2). The request shape is
unchanged.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| timeout_ms | integer | 20000 | false |

### Example

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
reply = client.sendMessage("hello")
print(reply.body)
```

## Client.send()
<!-- valid: 2.2-2.99 -->

`Client.send()` sends a single message to the Acme API and waits for a
response. Use it for simple, non-streaming calls where you want the full
reply before continuing. It replaces `Client.sendMessage()` (added in 2.2).

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| message | string | — | true |
| timeout_ms | integer | 20000 | false |
| retry_backoff_ms | integer | 500 | false |

`message` is the text payload sent to the API. `timeout_ms` controls how long
the client waits before giving up on a single attempt (default 20000 ms in
2.x). `retry_backoff_ms` is the base delay between retry attempts after a
failed call (default 500 ms in 2.x).

### Example (2.2 to 2.4)
<!-- valid: 2.2-2.4 -->

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
response = client.send(message="hello", timeout_ms=5000, retry_backoff_ms=2000)
print(response.body)
```

### Example (2.5 and later)
<!-- valid: 2.5-2.99 -->

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")
response = client.send(message="hello", timeout_ms=5000, retry_backoff_ms=2000)
print(response.body)
```

## Client.close()
<!-- valid: 2.0-2.99 -->

`Client.close()` releases the underlying network connection pool. Call it
when you are done using a client, for example at the end of a script or in a
`finally` block. It takes no parameters and returns nothing.
