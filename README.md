# DocuBot — Solution

This is the **reference solution** for the AI110 Module 4 Tinker *DocuBot*. The three stubbed
retrieval methods are implemented, documents are chunked into paragraphs (Part 3), and a refusal
guardrail is in place, so you can compare it against the retriever you built. It is one reasonable
solution — a deliberately simple keyword retriever whose limits are part of the lesson.

> Starter repo: [`ai110-module4tinker-docubot-starter`](https://github.com/codepath/ai110-module4tinker-docubot-starter)

**What's implemented in `docubot.py`:** `build_index` (inverted index), `score_document`
(stopword-filtered, whole-token keyword overlap), and `retrieve` (scores paragraph chunks, returns
the top 3, and refuses when nothing clears a confidence threshold). See `model_card.md` for the
full write-up, including honest failure cases.

**Verifying without a Gemini key:** Mode 2 (retrieval only) and `python evaluation.py` need no API
key. The evaluation harness reports a hit rate of ~0.62; "Where is the auth token generated?"
correctly retrieves `AUTH.md`, and "payment processing" is correctly refused.

---

DocuBot is a small documentation assistant that helps answer developer questions about a codebase.  
It can operate in three different modes:

1. **Naive LLM mode**  
   Sends the entire documentation corpus to a Gemini model and asks it to answer the question.

2. **Retrieval only mode**  
   Uses a simple indexing and scoring system to retrieve relevant snippets without calling an LLM.

3. **RAG mode (Retrieval Augmented Generation)**  
   Retrieves relevant snippets, then asks Gemini to answer using only those snippets.

The docs folder contains realistic developer documents (API reference, authentication notes, database notes), but these files are **just text**. They support retrieval experiments and do not require students to set up any backend systems.

---

## Setup

### 1. Install Python dependencies

    pip install -r requirements.txt

### 2. Configure environment variables

Copy the example file:

    cp .env.example .env

Then edit `.env` to include your Gemini API key:

    GEMINI_API_KEY=your_api_key_here

If you do not set a Gemini key, you can still run retrieval only mode.

---

## Running DocuBot

Start the program:

    python main.py

Choose a mode:

- **1**: Naive LLM (Gemini reads the full docs)  
- **2**: Retrieval only (no LLM)  
- **3**: RAG (retrieval + Gemini)

You can use built in sample queries or type your own.

---

## Running Retrieval Evaluation (optional)

    python evaluation.py

This prints simple retrieval hit rates for sample queries.

---

## Modifying the Project

You will primarily work in:

- `docubot.py`  
  Implement or improve the retrieval index, scoring, and snippet selection.

- `llm_client.py`  
  Adjust the prompts and behavior of LLM responses.

- `dataset.py`  
  Add or change sample queries for testing.

---

## Requirements

- Python 3.9+
- A Gemini API key for LLM features (only needed for modes 1 and 3)
- No database, no server setup, no external services besides LLM calls
