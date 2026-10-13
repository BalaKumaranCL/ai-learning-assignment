# Week 10 bonus -- a2a_lifecycle.md

## The failed case on the A2A task lifecycle

Case Q6: "Our v2 code calls client.sendMessage(message="hi"). Is that still valid in v3? ..." -- version worker returns 500 on both attempts.

Lifecycle as it should run:

    submitted -> working -> working (version worker 500, retry) -> FAILED   (with a status message and the partial artifact attached)

**It should end `failed`, not `input-required`.** `input-required` means "a human can unblock me by telling me something".
Here the developer already gave the version (v2 code, asking about v3); the missing thing is a healthy worker, and nothing the
developer types fixes a 500. Asking "which SDK version are you on?" would be a made-up question that hides an outage.
`input-required` IS the right state for a different case -- e.g. Q10 ("Is Client.close() deprecated?") with no version stated and
a worker that cannot tell which version to check: there the user's answer genuinely unblocks the task.

What the shipped orchestrator did instead (see failure_case.md): it jumped `working -> completed` with an unverified answer.
Under A2A that is a protocol-visible lie: the task state says `completed` when the version check never happened.

## What A2A buys over a plain REST call to the worker (2 lines)

1. A standard discoverable contract (AgentCard: skills, modes, auth) and a task lifecycle (working / input-required / failed / ...),
   so "worker is down" and "worker needs the SDK version" are protocol states the orchestrator must handle -- not an HTTP 500 it can quietly swallow.
2. Long-running work, streaming/push updates and typed artifacts come standard, so any vendor's worker plugs in without a custom client per worker.
