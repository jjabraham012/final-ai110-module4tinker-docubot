"""
Gemini client wrapper used by DocuBot.

Handles:
- Configuring the Gemini client from the GEMINI_API_KEY environment variable
- Naive "generation only" answers over the full docs corpus (Phase 0)
- RAG style answers that use only retrieved snippets (Phase 2)
- Agentic helpers: query reformulation and answer self-checking (capstone)

Experiment with:
- Prompt wording
- Refusal conditions
- How strictly the model is instructed to use only the provided context
"""

import os
from google import genai

# Central place to update the model name if needed.
# You can swap this for a different Gemini model in the future.
GEMINI_MODEL_NAME = "gemini-flash-lite-latest"


class GeminiClient:
    """
    Simple wrapper around the Gemini model.

    Usage:
        client = GeminiClient()
        answer = client.naive_answer_over_full_docs(query, all_text)
        # or
        answer = client.answer_from_snippets(query, snippets)
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY environment variable. "
                "Set it in your shell or .env file to enable LLM features."
            )

        self.client = genai.Client(api_key=api_key)

    # -----------------------------------------------------------
    # Phase 0: naive generation over full docs
    # -----------------------------------------------------------

    def naive_answer_over_full_docs(self, query, all_text):
        # We ignore all_text and send a generic prompt instead
        prompt = f"""
    You are a documentation assistant. 
    Answer this developer question: {query}
    """
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt
            )
            return (response.text or "").strip()
        except Exception as e:
            return f"Unable to generate an answer. ({type(e).__name__}: {e})"

    # -----------------------------------------------------------
    # Phase 2: RAG style generation over retrieved snippets
    # -----------------------------------------------------------

    def answer_from_snippets(self, query, snippets):
        """
        Phase 2:
        Generate an answer using only the retrieved snippets.

        snippets: list of (filename, text) tuples selected by DocuBot.retrieve

        The prompt:
        - Shows each snippet with its filename
        - Instructs the model to rely only on these snippets
        - Requires an explicit "I do not know" refusal when needed
        """

        if not snippets:
            return "I do not know based on the docs I have."

        context_blocks = []
        for filename, text in snippets:
            block = f"File: {filename}\n{text}\n"
            context_blocks.append(block)

        context = "\n\n".join(context_blocks)

        prompt = f"""
You are a cautious documentation assistant helping developers understand a codebase.

You will receive:
- A developer question
- A small set of snippets from project files

Your job:
- Answer the question using only the information in the snippets.
- If the snippets do not provide enough evidence, refuse to guess.

Snippets:
{context}

Developer question:
{query}

Rules:
- Use only the information in the snippets. Do not invent new functions,
  endpoints, or configuration values.
- If the snippets are not enough to answer confidently, reply exactly:
  "I do not know based on the docs I have."
- When you do answer, briefly mention which files you relied on.
"""

        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt
            )
            return (response.text or "").strip()
        except Exception as e:
            return f"API error — could not generate answer. ({type(e).__name__}: {e})"

    # -----------------------------------------------------------
    # Agentic helper: query reformulation
    # -----------------------------------------------------------

    def reformulate_query(self, original_query, attempt_number, previous_attempts=None):
        """
        Agentic step: when retrieval finds nothing useful, ask Gemini to
        rephrase the question using different keywords/synonyms that are
        more likely to match how the documentation is actually worded.

        previous_attempts: optional list of query strings already tried in
        this run (including the original). Passed back to the model so it
        doesn't suggest the same rephrasing twice — without this, Gemini
        tends to converge on the same "obvious" rewording every time.

        Returns a single reformulated query string (no explanation, no
        quotes) so it can be fed straight back into DocuBot.retrieve().
        Falls back to the original query if the API call fails, so the
        agent loop can keep going instead of crashing.
        """
        previous_attempts = previous_attempts or []
        already_tried_block = ""
        if previous_attempts:
            tried_list = "\n".join(f'- "{q}"' for q in previous_attempts)
            already_tried_block = f"""
These phrasings have already been tried and did NOT find a good answer.
Do not repeat any of them — suggest something genuinely different:
{tried_list}
"""

        prompt = f"""
You are helping a documentation search tool find better keywords.

The original developer question is:
"{original_query}"
{already_tried_block}
Suggest ONE alternative way to phrase this same question using different
but related keywords/synonyms that might appear in technical
documentation (for example "auth token" -> "access token", "database" ->
"connection string").

Reply with ONLY the reformulated question. No quotes, no explanation,
no numbering.
"""
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt
            )
            reformulated = (response.text or "").strip()
            return reformulated if reformulated else original_query
        except Exception:
            return original_query

    # -----------------------------------------------------------
    # Agentic helper: self-check a draft answer against the evidence
    # -----------------------------------------------------------

    def check_answer_supported(self, query, snippets, draft_answer):
        """
        Agentic step: after generating a draft answer, ask Gemini to verify
        the answer is actually supported by the retrieved snippets, rather
        than trusting the first draft blindly.

        Returns (is_supported: bool, reasoning: str). If the check itself
        fails (e.g. API error), fails safe by returning False so the agent
        falls back to a refusal instead of risking a hallucination.
        """
        context_blocks = []
        for filename, text in snippets:
            context_blocks.append(f"File: {filename}\n{text}\n")
        context = "\n\n".join(context_blocks)

        prompt = f"""
You are fact-checking an AI-generated answer against source documentation.

Question:
{query}

Source snippets:
{context}

Draft answer to check:
{draft_answer}

Does the draft answer rely ONLY on information present in the source
snippets above, with no invented details (no made-up functions, endpoints,
config values, or facts not stated in the snippets)?

Reply in exactly this format:
VERDICT: YES or NO
REASON: one short sentence
"""
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL_NAME,
                contents=prompt
            )
            text = (response.text or "").strip()

            verdict = ""
            reason = ""
            for line in text.splitlines():
                if line.upper().startswith("VERDICT:"):
                    verdict = line.split(":", 1)[1].strip().upper()
                elif line.upper().startswith("REASON:"):
                    reason = line.split(":", 1)[1].strip()

            is_supported = verdict.startswith("YES")
            return is_supported, (reason or text)
        except Exception as e:
            return False, f"Self-check failed due to error: {type(e).__name__}"