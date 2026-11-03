# Fresh-eyes note — STATUS: OPEN (a person has not done this yet)

The brief asks for: *who from which squad ran it, where they stumbled, what you changed.* **Nobody from another squad has run this.** I am not going to invent a reviewer. This file has (A) what I did instead, which is NOT a substitute, and (B) the protocol and the form for the real one.

## A. What I did instead: a self-run "stranger" test (2026-11-02) — by me, so it proves less than it looks

I copied the repo (without `.git`, without my venv) into an empty folder, built a clean venv with the same interpreter, ran **only** `pip install -r requirements.txt`, then the README's commands.

| Step | Result |
|---|---|
| `pip install -r requirements.txt` in a folder under a very long path | **Failed**: `[WinError 206] The filename or extension is too long` inside `pywin32` (pulled in by `mcp`). Not a bug in the repo — a Windows 260-character path limit; I had put the test copy deep inside a temp folder. **Changed:** README now says to keep the path short on Windows. |
| Same, under a short path | OK, 70 s. |
| `python run_w12.py ask "Does client.pollStream still work in 3.0?" --version 2.4` | OK, answer as expected. |
| `python run_w12.py` (everything) | OK, 117 s, exit 0, **identical numbers** to my working copy (so the run is deterministic). |
| `python run_w12.py` on the machine's default Python (no scikit-learn, no mcp) | Prints a one-line fix and exits 1 instead of a traceback. (It used to be a traceback: seam S1.) |

What this does **not** tell me: whether the README is *clear*, whether the numbers are *understood*, whether someone who didn't write the code would trust them. Only a person who didn't build it can say.

## B. For the real reviewer (someone from another squad) — 20 minutes

1. Clone. Read **only** `README-w12-capstone-e.md`. Start a stopwatch. Don't ask me anything.
2. Follow "Run it". Write down the minute at which you saw `RESULT: GREEN` (or got stuck, and where).
3. Run `python reviewer_client.py "how do I paginate through my messages" 2.4` — **this is the MCP call from a client that isn't mine.** Tell me if you needed anything from this repo to do it (you shouldn't: it imports only `mcp`).
4. Ask three questions of your own with `python run_w12.py ask "..." --version <your version>`. Include one with a version nobody would guess (2.7, 2.9) and one with a method name that doesn't exist.
5. Open `output/w12/EVAL_REPORT.md`. Without help, can you say in one sentence what number moved and what the suite does *not* measure?

| Field | |
|---|---|
| Reviewer name | |
| Squad | |
| Date | |
| Minutes from clone to `RESULT:` line | |
| Where they stumbled (verbatim) | |
| Question they asked that I had not tried; did it work? | |
| Could they state the headline number + the non-coverage in one sentence? | |
| What I changed because of it | |

**Until this table is filled in by someone else, the submission checklist item "Fresh-eyes note" is not done.**
