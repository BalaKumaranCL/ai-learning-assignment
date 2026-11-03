---
page_id: changelog
sdk_version: v3
page_type: changelog
source_file: CHANGELOG_3x.md
---

# CHANGELOG (Acme SDK 3.x)

## 3.0.0

**Removed:** `Client.sendMessage()`, `Client.pollStream()`,
`AuthConfig(token=...)`, `RequestOptions(custom_headers=...)`, and the
`page` / `per_page` arguments of `Client.list_messages()` with the result's
`page` and `total_pages` fields. See the migration guide for the replacements.

**Changed:** `Client.send()` default `timeout_ms` is now 30000 (was 20000) and
`retry_backoff_ms` is now 1000 (was 500).

**Added:** `max_retries` on `Client.send()` (default 3), `token_refresh_ms` on
`AuthConfig`, and `body_encoding` on `RequestOptions`.
