---
page_id: responses
sdk_version: v3
page_type: reference
source_file: responses.md
---

# Responses

`Client.send()` returns a `Response` object once the API has replied. The
`Response` object gives you access to the status code, the parsed body, and
any headers the server sent back.

## Response object

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

### Example

```python
response = client.send(message="hello")

if response.status_code == 200:
    print(response.body)
```

## Checking for errors

A `status_code` of 200 means success. Any other status code means the call
did not succeed; see the Errors page for which exception the SDK raises for
each case.
