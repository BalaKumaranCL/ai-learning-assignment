---
page_id: authentication
sdk_version: v3
page_type: reference
source_file: authentication.md
---

# Authentication

The Acme SDK authenticates using an API key. You configure authentication by
constructing a `Client` with an `AuthConfig`, or by passing `api_key`
directly to `Client()`.

## AuthConfig

`AuthConfig` describes how the client should authenticate its requests.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| api_key | string | — | true |
| region | string | "us" | false |
| token_refresh_ms | integer | 3600000 | false |

`api_key` is the secret key issued from your Acme dashboard and is always
required; the client will refuse to start without it. `region` selects which
regional API endpoint to talk to. `token_refresh_ms` controls how often a
temporary session token is refreshed in the background.

### Example

```python
from acme_sdk import Client, AuthConfig

auth = AuthConfig(api_key="sk_live_example", region="eu")
client = Client(auth=auth)
```

## Rotating keys

If a key is compromised, revoke it from the Acme dashboard and issue a new
one. The SDK does not cache keys to disk, so rotating a key only requires
restarting your process with the new `api_key` value.
