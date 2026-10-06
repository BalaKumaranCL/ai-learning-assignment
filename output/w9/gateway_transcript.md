# Week 9 bonus -- gateway + token scoping

Agent connects to ONE server (`gateway`); it discovered 5 tools through it: search_docs, get_openapi_spec, list_package_versions, get_package_version, get_deprecation_notice.

## read-only token (get_deprecation_notice denied)

Q: When was acme-sdk 3.1.0 released?
```
  lap 1: tools/call gateway::get_package_version({"package": "acme-sdk", "version": "3.1.0"}) -> ok
      acme-sdk 3.1.0 was released on 2025-06-02. Latest published is 3.2.0.
  FINAL ANSWER:
      acme-sdk 3.1.0 was released on 2025-06-02. Latest published is 3.2.0.
```

Q: Is acme-sdk 2.9.1 deprecated?
```
  lap 1: tools/call gateway::get_deprecation_notice({"package": "acme-sdk", "version": "2.9.1"}) -> ERROR
      SCOPE_DENIED: this token (docs-assistant-readonly) is not allowed to call get_deprecation_notice. The tool exists and the servers are up; this is a permission limit, not an outage. Allowed tools: search_docs, get_openapi_spec, list_package_versions, get_package_version. Tell the user the get_deprecation_notice information is unavailable to you. alternative_tool: get_package_version
  lap 2: tools/call gateway::get_package_version({"package": "acme-sdk", "version": "2.9.1"}) -> ok
      acme-sdk 2.9.1 was released on 2024-03-12. Latest published is 3.2.0.
  FINAL ANSWER:
      Note: get_deprecation_notice was refused (SCOPE_DENIED: this token (docs-assistant-readonly) is not allowed to call get_deprecation_notice.) so this does NOT cover that part.
      acme-sdk 2.9.1 was released on 2024-03-12. Latest published is 3.2.0.
```

## full token

Q: When was acme-sdk 3.1.0 released?
```
  lap 1: tools/call gateway::get_package_version({"package": "acme-sdk", "version": "3.1.0"}) -> ok
      acme-sdk 3.1.0 was released on 2025-06-02. Latest published is 3.2.0.
  FINAL ANSWER:
      acme-sdk 3.1.0 was released on 2025-06-02. Latest published is 3.2.0.
```

Q: Is acme-sdk 2.9.1 deprecated?
```
  lap 1: tools/call gateway::get_deprecation_notice({"package": "acme-sdk", "version": "2.9.1"}) -> ok
      acme-sdk 2.9.1 is DEPRECATED since 2025-01-20: 2.x is end-of-life. Client.sendMessage, Client.pollStream, AuthConfig.token and RequestOptions.custom_headers were renamed in 3.0.0; upgrade to 3.x. Upgrade to 3.2.0.
  FINAL ANSWER:
      acme-sdk 2.9.1 is DEPRECATED since 2025-01-20: 2.x is end-of-life. Client.sendMessage, Client.pollStream, AuthConfig.token and RequestOptions.custom_headers were renamed in 3.0.0; upgrade to 3.x. Upgrade to 3.2.0.
```

## gateway_audit.log (one line per tools/call: caller, tool, package@version)

```
2026-10-06T08:00:27+00:00 caller=docs-assistant-readonly tool=get_package_version package@version=acme-sdk@3.1.0 decision=ALLOW
2026-10-06T08:00:27+00:00 caller=docs-assistant-readonly tool=get_deprecation_notice package@version=acme-sdk@2.9.1 decision=DENY reason=SCOPE_DENIED
2026-10-06T08:00:27+00:00 caller=docs-assistant-readonly tool=get_package_version package@version=acme-sdk@2.9.1 decision=ALLOW
2026-10-06T08:00:31+00:00 caller=docs-assistant-full tool=get_package_version package@version=acme-sdk@3.1.0 decision=ALLOW
2026-10-06T08:00:31+00:00 caller=docs-assistant-full tool=get_deprecation_notice package@version=acme-sdk@2.9.1 decision=ALLOW
```
