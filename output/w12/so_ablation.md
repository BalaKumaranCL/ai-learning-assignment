# Stack Overflow: what it buys and what it costs (hostile question 3)

**n = 12 colloquial questions** with the doc pages a correct top-3 should contain, written before the run. Three retrievers over the same questions:

| Retriever | hit@3 | Notes |
|---|---:|---|
| A. scoped by version, Stack Overflow used **as phrasing only** (shipped) | **91.7%** | bridge fired on 5 of 12; an SO answer was returned as content 0 times |
| B. scoped by version, Stack Overflow **dropped** | **91.7%** | the "just delete them" fix |
| C. Stack Overflow indexed **as ordinary docs**, no version filter (first wiring) | 83.3% | a dead v1 answer is in the top 3 for **9 of 12** questions and is the TOP result for **9 of 12** |

**Both numbers the question asks for:** dropping Stack Overflow costs **0.0% of hit@3** here (91.7% with the bridge vs 91.7% without, n=12). Keeping it as ordinary content would put a dead API at rank 1 for 9 of 12 questions.

So on this set the bridge **has not earned its place**: it fires, and nothing changes. What actually protects the answers is keeping the v1 pages out of the served index (version filter) — not anything clever about them. With n=12 this cannot show a small gain either; I would not delete the bridge on this evidence, and I would not claim it helps.

| Query | Version | A | B | C | SO in C's top 3? |
|---|---|:-:|:-:|:-:|:-:|
| my call just hangs forever and never returns | 2.4 | hit | hit | miss | yes |
| the request just freezes when the network is slow | 2.4 | hit | hit | hit | yes |
| got a 429 too many requests how do I back off | 3.0 | miss | miss | miss | yes |
| where does my key go, getting 401 | 3.0 | hit | hit | hit | yes |
| how do I get the next page of results | 3.0 | hit | hit | hit |  |
| how can I stop leaking connections | 2.4 | hit | hit | hit | yes |
| add an extra HTTP header to every call | 2.4 | hit | hit | hit |  |
| read the status from the reply | 3.0 | hit | hit | hit | yes |
| stream the answer bit by bit | 2.4 | hit | hit | hit | yes |
| retry automatically when it fails | 3.0 | hit | hit | hit | yes |
| what error do I get for a bad parameter | 3.0 | hit | hit | hit |  |
| how do I rotate my key | 3.0 | hit | hit | hit | yes |
