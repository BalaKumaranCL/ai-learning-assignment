---
page_id: pagination
sdk_version: v3
page_type: reference
source_file: pagination.md
---

# Pagination

`Client.list_messages()` returns one page of your stored messages at a time.
In 3.0 paging is cursor-based only.

## Client.list_messages()

### Parameters

| Name | Type | Default | Required |
|---|---|---|---|
| limit | integer | 50 | false |
| cursor | string | None | false |

`limit` is the number of items per page. `cursor` is the `next_cursor` value
from the previous result; leave it out for the first page. `next_cursor` is
`None` on the last page. The 2.x arguments `page` and `per_page` were removed
in 3.0, and so were the result's `page` and `total_pages` fields.

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
