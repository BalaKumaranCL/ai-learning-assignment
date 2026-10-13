# Week 10 -- failure_case.md (Q6)

Case: `Our v2 code calls client.sendMessage(message="hi"). Is that still valid in v3? If not, what should we call instead, and what parameters does it take?`  (target `Client.sendMessage`, v3). The version/deprecation worker is made to return **HTTP 500** (`{"error": "Internal Server Error"}`) for this case only; every other case runs healthy.

## One-line verdict on what the orchestrator actually did

**LIED: retried, then shipped an answer with no version check behind it and no disclosure.** It retried once (2 attempts, both 500), then carried on to the code-sample worker without the version check and wrote a final answer that never mentions the check failed -- so the developer asking "is sendMessage still valid in v3?" gets no answer to that question and no warning.

Orchestrator policy as shipped: retry once on a 5xx; if still failing, continue with whatever the other worker returns. That policy was written plainly before this injection was run and not tuned to look better or worse.

| Run | version attempts | version check present | answer discloses gap | passes judge | tokens | what happened |
|---|:-:|:-:|:-:|:-:|---:|---|
| healthy (baseline) | 1 | yes | no | Y | 1,154 | no failure observed |
| 500 on BOTH attempts (shipped orchestrator policy) | 2 | NO | no | N | 2,346 | LIED: retried, then shipped an answer with no version check behind it and no disclosure |
| 500 on BOTH attempts, orchestrator discloses partial answers (fix) | 2 | NO | yes | N | 2,385 | DEGRADED: retried, then shipped a partial answer that says the version check is missing |
| 500 on the FIRST attempt only (transient) | 2 | yes | no | Y | 1,374 | RETRIED and recovered (version check succeeded on a later attempt) |

## Final answers

**healthy (baseline)**

```
`Client.sendMessage` is deprecated in v3. Use `Client.send` instead (Renamed for consistency with Client.stream(); same request shape, waits for the full reply.).
```

**500 on BOTH attempts (shipped orchestrator policy)**

```
No OpenAPI schema on file for `Client.sendMessage` in v3.

Docs (streaming.md > Streaming > Client.stream()): ## Client.stream()

`Client.stream()` sends a message the same way `Client.send()` does, but
instead of waiting for the full reply it returns an iterator that yields
`StreamChunk` objects as they arrive from the server. Use it when you want to
show partial output to a user as soon as it is available, instead of
blocking until the entire response is ready.

Docs (client.md > Client > Client.send()): ## Clien ...
```

**500 on BOTH attempts, orchestrator discloses partial answers (fix)**

```
[PARTIAL ANSWER: the version/deprecation check was unavailable (worker returned HTTP 500 after retrying), so the deprecation status below is NOT verified.]

No OpenAPI schema on file for `Client.sendMessage` in v3.

Docs (streaming.md > Streaming > Client.stream()): ## Client.stream()

`Client.stream()` sends a message the same way `Client.send()` does, but
instead of waiting for the full reply it returns an iterator that yields
`StreamChunk` objects as they arrive from the server. Use it when you want to
show part ...
```

**500 on the FIRST attempt only (transient)**

```
`Client.sendMessage` is deprecated in v3. Use `Client.send` instead (Renamed for consistency with Client.stream(); same request shape, waits for the full reply.).
```

## Notes

- The failure is not hidden by the metrics: the shipped policy FAILS the judge on this case (squad 9/10 here vs 10/10 healthy), so a failing worker costs a pass, not just tokens. The disclosed-partial fix still fails the keyword judge (the answer really is missing the deprecation fact) but no longer misleads the developer -- honesty, not a pass-rate fix.
- Retrying cost +1,192 tokens vs healthy on this one case. A transient 500 is recovered by the retry (+220 tokens) and the judge passes.
- The single agent has no worker to lose: a failing `check_deprecation` there is one tool error in one loop. More agents means more places a partial failure can hide.
