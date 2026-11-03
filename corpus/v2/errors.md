---
page_id: errors
sdk_version: v2
page_type: reference
source_file: errors_v2.md
---

# Errors (Acme SDK 2.x)

The Acme SDK raises typed exceptions instead of returning error codes for
failure cases. All SDK exceptions inherit from `AcmeError`.

## Exception table
<!-- valid: 2.0-2.99 -->

| Exception | Raised when | Retryable |
|---|---|---|
| TimeoutError | `timeout_ms` is exceeded before the server replies | true |
| RateLimitError | the account has exceeded its request quota | true |
| AuthError | the key is missing or invalid | false |
| ValidationError | a required parameter is missing or malformed | false |

`TimeoutError` is raised by `Client.send()` when the configured `timeout_ms`
(default 20000 ms in 2.x) elapses before a response is received; the client
retries using `retry_backoff_ms` before letting the `TimeoutError` propagate
to your code. `RateLimitError` and `TimeoutError` are both safe to retry.
`AuthError` and `ValidationError` are not retryable because retrying with the
same bad input will always fail again.

### Example (2.0 and 2.1)
<!-- valid: 2.0-2.1 -->

```python
from acme_sdk import Client, AuthConfig, TimeoutError

client = Client(auth=AuthConfig(token="sk_live_example"))

try:
    client.sendMessage("hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
```

### Example (2.2 to 2.4)
<!-- valid: 2.2-2.4 -->

```python
from acme_sdk import Client, AuthConfig, TimeoutError

client = Client(auth=AuthConfig(token="sk_live_example"))

try:
    client.send(message="hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
```

### Example (2.5 and later)
<!-- valid: 2.5-2.99 -->

```python
from acme_sdk import Client, TimeoutError

client = Client(api_key="sk_live_example")

try:
    client.send(message="hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
```

## Handling AcmeError generically
<!-- valid: 2.0-2.99 -->

If you don't need to distinguish between exception types, catch the base
`AcmeError` class instead of each subclass individually.
