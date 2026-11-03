---
page_id: pagination
sdk_version: v2
page_type: reference
source_file: pagination_v2.md
---

# Pagination (Acme SDK 2.x)

`Client.list_messages()` returns one page of your stored messages at a time.

## Paging with page and per_page
<!-- valid: 2.0-2.5 -->

Up to 2.5, you ask for a page number. The result has `items`, the current
`page` and `total_pages`.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| page | integer | 1 | false |
| per_page | integer | 50 | false |

### Example (2.0 to 2.4)
<!-- valid: 2.0-2.4 -->

```python
from acme_sdk import Client, AuthConfig

client = Client(auth=AuthConfig(token="sk_live_example"))

page = 1
while True:
    result = client.list_messages(page=page, per_page=50)
    for item in result.items:
        print(item)
    if page >= result.total_pages:
        break
    page += 1
```

### Example (2.5)
<!-- valid: 2.5-2.5 -->

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")

page = 1
while True:
    result = client.list_messages(page=page, per_page=50)
    for item in result.items:
        print(item)
    if page >= result.total_pages:
        break
    page += 1
```

## Paging with limit and cursor
<!-- valid: 2.6-2.99 -->

From 2.6 you can page with a cursor: pass `limit` and the `cursor` from the
previous result's `next_cursor`. **`page` and `per_page` are deprecated in 2.6
and removed in 3.0**; `limit` replaces `per_page` and `cursor` replaces `page`.
`next_cursor` is `None` on the last page.

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| limit | integer | 50 | false |
| cursor | string | None | false |

### Example

```python
from acme_sdk import Client

client = Client(api_key="sk_live_example")

cursor = None
while True:
    result = client.list_messages(limit=50, cursor=cursor)
    for item in result.items:
        print(item)
    cursor = result.next_cursor
    if cursor is None:
        break
```
