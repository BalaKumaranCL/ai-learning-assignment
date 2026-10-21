# cost_by_stage.md -- cost per query for the incident request

Request: trace `t_b3efb0c1df` (user u-0417, slack-bot, 2026-10-15T14:37:12): "give me a code sample for sending a message with the client", no sdk_version_filter.

Before = the logged request, served by `docs_v1`. After = the SAME request re-run through the shipped service under `docs_v2`. Stage = the `stage` field on each span in `trace.json`.

| Stage | calls (before) | tokens | $ per query | share | calls (after) | tokens | $ per query | share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Retrieval | 1 | 15 | $0.00000430 | 1.0% | 1 | 15 | $0.00000430 | 0.6% |
| Generation | 1 | 302 | $0.00041440 | 99.0% | 1 | 581 | $0.00067600 | 92.6% |
| Tools | 0 | 0 | $0.00000000 | 0.0% | 1 | 0 | $0.00005000 | 6.8% |
| **Total** | | 317 | **$0.00041870** | 100% | | 596 | **$0.00073030** | 100% |

Cost moved by **+74.4%** per query ($+0.00031160). Where it moved, by stage: retrieval $+0.00000000, generation $+0.00026160, tools $+0.00005000.

## Same split over all of last week's traffic

Replaying all 798 requests from 2026-10-12..18 under each version (answers under `docs_v1` match the logs exactly):

| Stage | docs_v1 $/query | docs_v2 $/query |
|---|---:|---:|
| Retrieval | $0.00000427 | $0.00000427 |
| Generation | $0.00044993 | $0.00054080 |
| Tools | $0.00000000 | $0.00001247 |
| **Total** | **$0.00045420** | **$0.00055754** |

## What these dollars are (read this before quoting them)

- **Generation** = tokens x the Week-7 Haiku-class price assumption ($0.0008/1K in, $0.004/1K out). Tokens are estimated as chars/4, not tokenised.
- **Retrieval** = query embedding ($2e-05/1K tokens) + one vector-store read ($4e-06). The repo's real retriever is local TF-IDF/BM25 and costs nothing; this is what a hosted index would charge. An assumption.
- **Tools** = $5e-05 per hosted `check_deprecation` call. An assumption. `docs_v1` makes no tool calls at all, so its tools cost is exactly $0.
- None of this is billing data. Change the constants at the top of `src/w11_service.py` and every number here moves with them.

Retrieval is 0.8% of spend under `docs_v2`, generation 97.0%: the fix did not touch the expensive stage, it added a (cheap) tool stage and a deeper retrieval for code samples.
