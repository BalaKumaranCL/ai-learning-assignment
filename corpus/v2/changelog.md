---
page_id: changelog
sdk_version: v2
page_type: changelog
source_file: CHANGELOG_2x.md
---

# CHANGELOG (Acme SDK 2.x)

## 2.6.0
<!-- valid: 2.6-2.99 -->

Added `limit` and `cursor` to `Client.list_messages()`, and `next_cursor` on
its result. **Deprecated:** `page` and `per_page` on `Client.list_messages()`
(removal in 3.0, use `limit` and `cursor`).

## 2.5.0
<!-- valid: 2.5-2.99 -->

Added `AuthConfig(api_key=...)`, `Client(api_key=...)` and
`RequestOptions(headers=...)`. **Deprecated:** `AuthConfig(token=...)` (removal
in 3.0, use `api_key`) and `RequestOptions(custom_headers=...)` (removal in 3.0,
use `headers`).

## 2.4.0
<!-- valid: 2.4-2.99 -->

Added `Client.stream()` and `StreamChunk`. **Deprecated:** `Client.sendMessage()`
(removal in 3.0, use `Client.send()`) and `Client.pollStream()` (removal in 3.0,
use `Client.stream()`).

## 2.2.0
<!-- valid: 2.2-2.99 -->

Added `Client.send()` as the new name for `Client.sendMessage()`, with a
`retry_backoff_ms` argument.
