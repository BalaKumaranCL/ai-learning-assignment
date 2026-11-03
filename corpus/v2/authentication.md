---
page_id: authentication
sdk_version: v2
page_type: reference
source_file: authentication_v2.md
---

# Authentication (Acme SDK 2.x)

The Acme SDK authenticates using a secret key issued from your Acme dashboard.
You configure authentication by constructing a `Client` with an `AuthConfig`.

## AuthConfig with token
<!-- valid: 2.0-2.4 -->

Up to 2.4, `AuthConfig` takes your secret as `token`.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| token | string | — | true |
| region | string | "us" | false |

`token` is the secret issued from your Acme dashboard and is always required;
the client will refuse to start without it. `region` selects which regional
API endpoint to talk to.

### Example

```python
from acme_sdk import Client, AuthConfig

auth = AuthConfig(token="sk_live_example", region="eu")
client = Client(auth=auth)
```

## AuthConfig with api_key
<!-- valid: 2.5-2.99 -->

From 2.5, `AuthConfig` takes `api_key`, and you can pass `api_key` straight to
`Client()`. **`AuthConfig(token=...)` is deprecated in 2.5 and removed in 3.0**;
`api_key` is the same required string field under its new name.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| api_key | string | — | true |
| region | string | "us" | false |

### Example

```python
from acme_sdk import Client, AuthConfig

auth = AuthConfig(api_key="sk_live_example", region="eu")
client = Client(auth=auth)
```

## Rotating keys
<!-- valid: 2.0-2.99 -->

If a key is compromised, revoke it from the Acme dashboard and issue a new
one. The SDK does not cache keys to disk, so rotating a key only requires
restarting your process with the new key value.
