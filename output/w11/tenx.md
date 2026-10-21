# tenx.md

**At 10x volume the API rate limit breaks first: today's busiest minute (2026-10-13 10:03) is 7 requests/min, so 10x is 70 requests/min against an assumed 50/min limit (it would hit the limit at 7.1x).**

## Numbers behind it (all from last week's logs, replayed under the shipped `docs_v2`)

| What | Today | At 10x | Limit (ASSUMED) | Breaks at | Breaks at 10x? |
|---|---:|---:|---:|---:|---|
| Peak requests/min (2026-10-13 10:03) | 7 | 70 | 50 | 7.1x | **YES** |
| Peak generation tokens/min (2026-10-18 10:00) | 4,476 | 44,760 | 50,000 | 11.2x | no |
| Monthly cost (798 req/week x 4.345 x $0.000558) | $1.93 | $19.33 | $100 | 52x | no |
| p99 latency (modelled) | 3218 ms | 3218 ms* | 2500 ms | n/a* | already over today (not a volume effect) |

\* Latency is modelled per request from span constants, with no shared queue, so it does not grow with volume by construction. In reality it is the second thing to go: once requests exceed the rate limit they get HTTP 429s and retries, and p99 latency then includes the retry wait. This model cannot show that number, so it is not claimed.

Separate finding: modelled p99 (3218 ms) is ALREADY over the assumed 2500 ms target at today's volume. It comes from the modelled slow-provider tail (1.2% of generations x3.5), not from load, so it is reported here but is not the answer to "what breaks at 10x".

## Assumptions you must replace with your real contract

- Generation model limit: **50 requests/min and 50,000 tokens/min** (a low-tier assumption; check your actual account limits -- the verdict flips if your limit is >= 70 requests/min).
- p99 SLO 2500 ms; monthly budget $100.
- Per-minute peaks use the clock minute of each request's `ts`; the traffic is synthetic (seeded) with a 10:00 stand-up burst, so the peak is realistic in shape but is not a measured production peak.
- The first thing to break is chosen by the smallest break-multiplier above: **API rate limit (requests/min)** at 7.1x.
