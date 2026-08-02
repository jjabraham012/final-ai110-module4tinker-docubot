# DocuBot Model Card

This model card is a short reflection on your DocuBot system. Fill it out after you have implemented retrieval and experimented with all three modes:

1. Naive LLM over full docs  
2. Retrieval only  
3. RAG (retrieval plus LLM)

Use clear, honest descriptions. It is fine if your system is imperfect.

---

## 1. System Overview

**What is DocuBot trying to do?**  
Describe the overall goal in 2 to 3 sentences.

    DocuBot is a question-answering assistant that helps developers find information within a small set of project documentation files. It reads markdown docs from a folder, breaks them into small chunks, and retrieves the most relevant pieces to answer a user's question. Optionally, it can pass those chunks to an LLM to generate a polished, natural-language answer.

**What inputs does DocuBot take?**  
For example: user question, docs in folder, environment variables.

    DocuBot takes a natural-language question from the user, a folder of .md and .txt documentation files, and optionally a GEMINI_API_KEY environment variable to enable LLM-powered modes. It also reads AUTH_SECRET_KEY and DATABASE_URL from the environment if the underlying app needs them, but DocuBot itself only requires the docs folder and the user's query.

**What outputs does DocuBot produce?**

    In retrieval-only mode, it returns labeled raw text snippets from the most relevant chunks (e.g. "[AUTH.md > Token Generation] Tokens are created by..."). In RAG mode, it returns a generated natural-language answer that synthesizes the retrieved chunks. In naive LLM mode, it returns a generated answer based on the entire doc corpus with no retrieval step. In all modes, if the system lacks useful evidence, it returns a refusal message.

---

## 2. Retrieval Design

**How does your retrieval system work?**  
Describe your choices for indexing and scoring.

- How do you turn documents into an index?
- How do you score relevance for a query?
- How do you choose top snippets?

    Each document is split into paragraph-level chunks by first splitting at markdown headings, then splitting within each section at blank lines. Each chunk gets a label like "AUTH.md > Token Generation" so the user knows where it came from. Then I tokenize each chunk into lowercase words, remove stop words, and build an inverted index mapping each meaningful word to the set of chunk indices that contain it.
    The query is tokenized and stop-word-filtered the same way. For each candidate chunk, I count how many times each query word appears in the chunk's text and sum those counts into a single score. A chunk that mentions "token" five times scores higher than one that mentions it once.
    The index narrows the search to only chunks that share at least one meaningful word with the query. Those candidates are scored, sorted by score descending, and any chunk below a minimum relevance threshold of 2 is dropped. The top 3 surviving chunks are returned.


**What tradeoffs did you make?**  
For example: speed vs precision, simplicity vs accuracy.

    I chose simplicity over accuracy. Raw word counting treats all non-stop words equally — "database" and "run" get the same weight even though "database" is far more specific. A TF-IDF approach would fix this by weighting rare words higher, but it adds complexity I didn't need for four small docs. I also chose paragraph-level chunking over sentence-level because paragraphs keep enough surrounding context to be readable, while sentences can be too fragmented to be useful on their own.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**  
Briefly describe how each mode behaves.

- Naive LLM mode:
- Retrieval only mode:
- RAG mode:

    Naive LLM mode: Concatenates all documents into one big string and sends it to Gemini along with the query. No retrieval happens. The LLM sees everything and generates an answer. This mode always calls the LLM.
    Retrieval only mode: Uses the inverted index and scoring to find the top chunks, then returns them as raw text. The LLM is never called. This is pure keyword matching.
    RAG mode: First runs retrieval to find the top chunks, then sends only those chunks to Gemini with instructions to answer using only the provided evidence. The LLM is called only after retrieval succeeds. If retrieval finds nothing above the threshold, the LLM is never called and DocuBot refuses directly.

**What instructions do you give the LLM to keep it grounded?**  
Summarize the rules from your prompt. For example: only use snippets, say "I do not know" when needed, cite files.

    The LLM client's prompt tells Gemini to answer using only the provided snippets, to cite which file each piece of information comes from, and to say "I do not know based on these docs" if the snippets do not contain the answer. It is explicitly told not to use outside knowledge or make assumptions beyond what the snippets say.

---

## 4. Experiments and Comparisons

Run the **same set of queries** in all three modes. Fill in the table with short notes.

You can reuse or adapt the queries from `dataset.py`.

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |

| Where is the auth token generated? | Helpful / correctly says auth_utils.py, but may add unsupported detail about internal? | Helpful / returns the Token Generation paragraph from AUTH.md | Helpful / clean answer citing AUTH.md, sticks to what's written	| All three get this right; RAG is cleanest |

| How do I connect to the database?	| Helpful but risky / may fabricate connection code that isn't in the docs | Helpful / returns the Connection Configuration chunk from DATABASE.md | Helpful / summarizes the DATABASE_URL setup clearly with source | Naive mode invented a code example that doesn't exist in the docs |

| Which endpoint lists all users? | Helpful / names GET /api/users correctly | Helpful / returns the exact API_REFERENCE.md section	| Helpful / concise answer with the endpoint and admin-only note | Retrieval-only is harder to scan since it dumps the raw markdown |

**What patterns did you notice?**  

- When does naive LLM look impressive but untrustworthy?  
- When is retrieval only clearly better?  
- When is RAG clearly better than both?

    Naive mode sounds most impressive on broad questions where it can weave together information from across all four docs. But it becomes untrustworthy when the answer isn't actually in the docs — it confidently fabricates details like code examples, function signatures, or technology choices that were never mentioned. It has no mechanism to say "I don't know."
    Retrieval only is better when you need a verifiable, exact quote from the docs and don't want any AI interpretation. It's also the only mode that works without an API key. The downside is that raw markdown chunks can be hard to read, especially when they contain code fences and formatting.
    RAG is clearly better when the answer requires combining information from multiple chunks — for example, understanding the auth flow requires pieces from both AUTH.md and API_REFERENCE.md. RAG merges them into one readable paragraph while still citing sources. It also inherits the retrieval guardrail, so it refuses off-topic questions that naive mode would confidently hallucinate on.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**  
For each one, say:

- What was the question?  
- What did the system do?  
- What should have happened instead?

    I asked "What programming language is the frontend built in?" The naive LLM mode confidently said the frontend uses JavaScript with React, citing no source. None of the docs mention a frontend, JavaScript, or React at all. It should have said it doesn't know. Retrieval-only and RAG correctly refused.

    I asked "What is the default token lifetime?" in retrieval-only mode. It returned the correct paragraph from AUTH.md mentioning TOKEN_LIFETIME_SECONDS defaults to 3600, but it also returned a second chunk from SETUP.md that only tangentially mentions the variable. The second chunk added noise without helping. The system should ideally rank the AUTH.md chunk much higher and either omit the weak second result or clearly indicate it's a lower-confidence match.

**When should DocuBot say “I do not know based on the docs I have”?**  
Give at least two specific situations.

    DocuBot should refuse when the question is about a topic not covered in any of the docs, like frontend frameworks, deployment infrastructure, or pricing. It should also refuse when the question uses terms that don't appear in the documentation at all, meaning no chunk passes the relevance threshold. A third case is when the top-scoring chunk only matches on generic words and doesn't actually contain the specific information being asked about.

**What guardrails did you implement?**  
Examples: refusal rules, thresholds, limits on snippets, safe defaults.

    I implemented three guardrails. First, a stop-word filter removes common English words before indexing and scoring so that matches are based on meaningful terms, not filler. Second, a minimum relevance score threshold (MIN_RELEVANCE_SCORE = 2) means a chunk must match at least two meaningful query words to be considered evidence — single-word coincidences are discarded. Third, if retrieval returns an empty list, both answer_retrieval_only and answer_rag return a clear refusal message instead of passing empty context to the LLM or returning nothing.

---

## 6. Limitations and Future Improvements

**Current limitations**  
List at least three limitations of your DocuBot system.

1. All words are weighted equally. The word "database" should matter more than "run" in a query about databases, but both count the same. TF-IDF or BM25 scoring would fix this.
2. Conflict detection only works on exact time string matches in the scheduler — the retrieval system has no notion of synonyms or related terms. Asking "auth credentials" won't match a chunk that only says "login password."
3. The chunking strategy depends on markdown formatting. Docs without headings or blank-line separation produce fewer, larger chunks, which reduces precision.

**Future improvements**  
List two or three changes that would most improve reliability or usefulness.

1. Add TF-IDF scoring so rare, specific words carry more weight than common ones. This would significantly improve ranking.
2. Add synonym expansion or simple stemming (e.g. "authenticate" and "authentication" should match) to catch more relevant chunks.
3. Return confidence scores alongside each chunk so the user can see how strong the evidence is, not just the raw text.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
Think about wrong answers, missing information, or over trusting the LLM.

> A developer who trusts DocuBot's answers without checking the source could follow incorrect API instructions, misconfigure authentication, or miss a required environment variable. In naive LLM mode especially, the system can fabricate plausible-sounding details — like inventing function parameters or configuration values that don't exist. If someone uses those fabricated details in production code, it could cause security vulnerabilities or application failures.

**What instructions would you give real developers who want to use DocuBot safely?**  
Write 2 to 4 short bullet points.

- Always verify DocuBot's answers against the actual source files before using them in code or configuration. Treat it as a search tool, not an authority.
- Prefer RAG mode over naive LLM mode. RAG grounds answers in retrieved evidence and refuses when it lacks information. Naive mode will guess.
- If DocuBot says "I don't have enough information," trust the refusal. Don't rephrase the question trying to trick it into answering — the information probably isn't in the docs.
- Keep docs up to date. DocuBot can only be as accurate as the files in the docs folder. Outdated or incomplete documentation produces outdated or incomplete answers.

---
