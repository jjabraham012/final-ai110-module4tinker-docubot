# Applied AI System: Agentic DocuBot

## Original Project

This project is an extension of **DocuBot**, originally built for the Module 4 "Tinker" activity (`ai110-module4tinker-docubot-starter`). The original DocuBot was a lightweight retrieval-augmented documentation assistant with three modes: naive LLM generation over a full doc corpus, a self-built keyword retrieval system with no LLM involved, and a RAG mode that combined the two. Its original goal was to demonstrate, side by side, why grounding an LLM's answers in retrieved evidence produces more reliable results than letting it generate freely.

## What This Project Does and Why It Matters

This capstone extends DocuBot into a fourth, **agentic** mode. Instead of retrieving once and generating once, Agentic DocuBot plans, acts, and checks its own work: it retrieves evidence, drafts an answer, verifies that the draft is actually supported by that evidence, and — if it isn't — rephrases the question and tries again, up to three times, before honestly admitting it doesn't know.

This matters because real documentation is messy and incomplete. A tool that always sounds confident, even when it's guessing, is actively dangerous for developers trying to understand a live codebase. Agentic DocuBot is built around the opposite instinct: it would rather retry, and ultimately refuse, than hand a developer a fabricated answer.

## Architecture Overview

The full system diagram is in [`diagrams/architecture.mmd`](diagrams/architecture.mmd) (Mermaid source).

At a high level:

- **`DocuBot`** (retriever) indexes the docs folder into paragraph-level chunks and scores them against a query using keyword overlap, with a minimum-relevance guardrail.
- **`AnswerAgent`** (the new agentic layer) wraps the retriever and the LLM in a loop: retrieve → draft an answer → self-check the draft against the retrieved evidence → if unsupported, reformulate the query (avoiding phrasings already tried) and retry.
- **`GeminiClient`** handles all LLM calls: naive generation, RAG generation, query reformulation, and the self-check verdict.
- **`evaluation.py`** automatically tests retrieval quality against a fixed set of sample queries with known expected sources.
- **`agent_log.txt`** records every attempt, reformulation, and self-check verdict, so a human can audit exactly why the agent answered — or refused to answer — the way it did.

The key design idea: retrieval finding *some* keyword match doesn't mean it found the *right* answer. The agent only trusts a draft once the self-check confirms it, not just because a chunk happened to share a word with the question.

## Setup Instructions

1. Clone this repo and enter the folder:
   ```bash
   git clone https://github.com/jjabraham012/applied-ai-system-application.git
   cd applied-ai-system-application
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up your environment variables. Copy `.env.example` to `.env` and add your Gemini key:
   ```bash
   GEMINI_API_KEY=your_api_key_here
   ```
   Retrieval-only mode works without a key. Naive, RAG, and Agentic modes require it.

4. Run the program:
   ```bash
   python main.py
   ```

5. Choose a mode (1–4) and either use the built-in sample queries or type your own question.

Optional: run the retrieval evaluation harness directly with:
```bash
python evaluation.py
```

## Sample Interactions

**1. A question the docs answer clearly (agent succeeds on the first attempt)**

> **Q:** Where is the auth token generated?
>
> **A:** *(answered correctly on attempt 1, self-check: supported=True, citing AUTH.md)*

**2. A question the docs don't actually answer, despite keyword overlap (agent retries, then honestly refuses)**

> **Q:** How do I get a session credential from the login API?
>
> Attempt 1 matched 5 snippets on keywords like "login," but the draft answer was a refusal — the self-check correctly flagged this as unsupported rather than accepting the refusal at face value. The agent reformulated to "How to retrieve an authentication token from the sign-in endpoint," tried again, and after 3 attempts still had no real answer:
>
> **A:** *"I do not know based on these docs. I tried rephrasing the question a few different ways and still couldn't find evidence that actually answers it."*

**3. An off-topic question with no relevant documentation (agent refuses appropriately)**

> **Q:** What color scheme does the frontend use?
>
> **A:** *"I do not know based on these docs."* — correctly refused; the docs never mention a frontend at all.

## Design Decisions and Trade-offs

- **Reformulation triggers on a failed self-check, not just empty retrieval.** An early version only retried when retrieval returned zero snippets. In testing, this almost never happened — keyword-overlap retrieval nearly always finds *something*, even when it's not actually relevant. Moving the retry trigger to "the self-check says this draft isn't supported" caught far more real failure cases.
- **A refusal draft is treated as a failed attempt, not a valid answer.** The self-check step verifies a draft is *consistent* with the snippets — and a refusal is trivially consistent with anything. Without a special case, the agent would accept its own refusal as "supported" and stop retrying on attempt 1 every time. This was found and fixed during testing (see Testing Summary).
- **Reformulation is given a memory of past attempts within a single run.** Without this, the LLM tended to suggest the same rephrasing twice on later attempts. Passing in the list of already-tried phrasings pushes it toward genuinely different wording each retry.
- **Trade-off — simplicity over robustness in retrieval itself.** Retrieval is still simple keyword-overlap scoring, not TF-IDF or embeddings. This keeps the system easy to understand end to end, at the cost of retrieval sometimes matching on generic overlap. The agentic layer exists specifically to compensate for that weakness rather than requiring a smarter retriever.
- **Every attempt is logged, not just the final answer.** `agent_log.txt` records the full reasoning trace so a developer can see *why* the agent refused, not just that it did — this is the project's main reliability/guardrail mechanism.

## Testing Summary

Testing the agent loop directly on real sample queries surfaced two real bugs, both fixed:

1. **Bug: reformulation never triggered.** Initial testing showed that even clearly out-of-scope questions ("frontend color scheme," "connect to the storage layer") were getting an answer or refusal on attempt 1, with reformulation never running. Root cause: the retry condition checked for *zero* snippets, but retrieval almost always returns at least one loosely-matching snippet.
2. **Bug: refusals were being accepted as "supported."** After fixing (1), the agent still stopped after attempt 1 on unanswerable questions. Root cause: the self-check judges whether a draft is consistent with the evidence, and a refusal is always trivially consistent — so it was being marked "supported" and returned immediately instead of triggering a retry.

What worked well: on questions the docs genuinely answer, the agent succeeds on attempt 1 with a correct self-check. On genuinely unanswerable questions, the agent now makes 2–3 real attempts with different phrasings before refusing — an honest refusal rather than an early or fabricated answer.

What I learned: retrieval "finding something" and retrieval "finding the answer" are very different signals, and an agentic system is only as reliable as the check that distinguishes them.

## Reflection

Building the agentic layer taught me that the interesting design work isn't the "happy path" — it's deciding exactly when the system should distrust itself and try again. The two bugs above only showed up by actually running real questions through the system and reading the log traces line by line, not by reasoning about the code in the abstract.
