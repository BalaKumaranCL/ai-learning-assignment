---
page_id: errors
sdk_version: v3
page_type: reference
source_file: errors.md
---

# Errors

The Acme SDK raises typed exceptions instead of returning error codes for
failure cases. All SDK exceptions inherit from `AcmeError`.

## Exception table

| Exception | Raised when | Retryable |
|---|---|---|
| TimeoutError | `timeout_ms` is exceeded before the server replies | true |
| RateLimitError | the account has exceeded its request quota | true |
| AuthError | the `api_key` is missing or invalid | false |
| ValidationError | a required parameter is missing or malformed | false |

`TimeoutError` is raised by `Client.send()` when the configured
`timeout_ms` elapses before a response is received; the client will
automatically retry using `retry_backoff_ms` up to `max_retries` times before
letting the `TimeoutError` propagate to your code. `RateLimitError` and
`TimeoutError` are both safe to retry. `AuthError` and `ValidationError` are
not retryable because retrying with the same bad input will always fail
again.

### Example

```python
from acme_sdk import Client, TimeoutError

client = Client(api_key="sk_live_example")

try:
    client.send(message="hello", timeout_ms=100)
except TimeoutError:
    print("the request timed out")
```

## Handling AcmeError generically

If you don't need to distinguish between exception types, catch the base
`AcmeError` class instead of each subclass individually.
