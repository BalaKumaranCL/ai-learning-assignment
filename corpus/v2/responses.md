---
page_id: responses
sdk_version: v2
page_type: reference
source_file: responses_v2.md
---

# Responses (Acme SDK 2.x)

`Client.send()` and `Client.sendMessage()` return a `Response` object once the
API has replied. The `Response` object gives you access to the status code, the
parsed body, and any headers the server sent back.

## Response object
<!-- valid: 2.0-2.99 -->

### Fields

| Name | Type | Default | Required |
|---|---|---|---|
| status_code | integer | — | true |
| body | dict | — | true |
| headers | dict | {} | false |

`status_code` is the HTTP status code returned by the Acme API and is always
present. `body` holds the parsed JSON payload and is always present, even if
it is an empty object. `headers` holds any response headers and defaults to
an empty dict when the server sends none.

### Example (2.2 to 2.4)
<!-- valid: 2.2-2.4 -->

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))
response = client.send(message="hello")

if response.status_code == 200:
    print(response.body)
```

### Example (2.5 and later)
<!-- valid: 2.5-2.99 -->

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")
response = client.send(message="hello")

if response.status_code == 200:
    print(response.body)
```

## Checking for errors
<!-- valid: 2.0-2.99 -->

A `status_code` of 200 means success. Any other status code means the call
did not succeed; see the Errors page for which exception the SDK raises for
each case.
