"""
Agentic layer for DocuBot (capstone extension).

Wraps the existing DocuBot retrieval system and GeminiClient generation
system in a small agent loop that can:

  - PLAN : decide whether the current retrieved evidence actually
           supports an answer (not just whether *any* snippet matched).
  - ACT  : retrieve snippets, generate a draft answer, and if the
           self-check finds the draft unsupported, ask the LLM to
           reformulate the query and retry — up to max_attempts times.
  - CHECK: after generating a draft answer, ask the LLM to verify the
           answer is actually supported by the retrieved snippets
           before handing it back to the user.

Design note: a naive version of this loop only reformulates when
retrieval comes back completely empty. That undersells the guardrail —
DocuBot's keyword-overlap retrieval will often return *some* snippet as
long as one word matches (e.g. "login" in "session credential from the
login API"), even when that snippet doesn't actually answer the
question. So the trigger for "try again with different wording" here is
the SELF-CHECK failing, not just an empty snippet list. This gives weak
or off-target matches a real second chance with reformulated phrasing,
while still refusing outright if nothing pans out after max_attempts.

This is intentionally NOT a standalone script. AnswerAgent is meant to
be called from main.py as a fourth mode, so the agentic behavior is
part of the main application logic rather than a side experiment.

Every attempt, reformulation, and self-check result is logged to
agent_log.txt so behavior is transparent and debuggable.
"""

import logging

logging.basicConfig(
    filename="agent_log.txt",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("docubot_agent")


class AnswerAgent:
    """
    Agentic wrapper around a DocuBot instance + GeminiClient.

    Usage:
        agent = AnswerAgent(bot, llm_client)
        answer, trace = agent.answer("Where is the auth token generated?")
    """

    def __init__(self, docubot, llm_client, max_attempts=3, top_k=5):
        if llm_client is None:
            raise RuntimeError(
                "AnswerAgent requires an LLM client. Provide a GeminiClient instance."
            )
        self.bot = docubot
        self.llm_client = llm_client
        self.max_attempts = max_attempts
        self.top_k = top_k

    def answer(self, query):
        """
        Runs the full agentic loop for a single question.

        Returns:
            final_answer (str): the answer to show the user.
            trace (list[dict]): a step-by-step record of what the agent
                did, useful for logging, debugging, or displaying to a
                curious user.
        """
        trace = []
        current_query = query
        tried_queries = [query]

        for attempt in range(1, self.max_attempts + 1):
            snippets = self.bot.retrieve(current_query, top_k=self.top_k)

            step = {
                "attempt": attempt,
                "query_used": current_query,
                "num_snippets": len(snippets),
            }
            logger.info(
                "Attempt %d | query=%r | snippets_found=%d",
                attempt, current_query, len(snippets),
            )

            if not snippets:
                # Nothing matched at all — reformulate (if we still can)
                # and try again rather than jumping straight to generation.
                step["draft_generated"] = False
                trace.append(step)

                if attempt < self.max_attempts:
                    current_query = self.llm_client.reformulate_query(
                        query, attempt, previous_attempts=tried_queries
                    )
                    tried_queries.append(current_query)
                    logger.info("Reformulated query -> %r", current_query)
                    continue
                else:
                    break

            # Snippets exist (even if weak) — generate a draft.
            draft_answer = self.llm_client.answer_from_snippets(query, snippets)

            # A refusal here means the retrieved snippets, despite matching
            # a keyword, didn't actually contain the answer. Treat this as a
            # failed attempt (not a "supported" answer) so it triggers a
            # retry instead of being returned as-is. Without this check, the
            # self-check below would rubber-stamp the refusal as "supported"
            # (it IS consistent with the snippets — it just gives up) and
            # the loop would stop on attempt 1 every time.
            REFUSAL_TEXT = "I do not know based on the docs I have."
            if draft_answer.strip() == REFUSAL_TEXT:
                step["draft_generated"] = True
                step["self_check"] = False
                step["self_check_reasoning"] = (
                    "answer_from_snippets refused to answer using these snippets"
                )
                trace.append(step)
                logger.info(
                    "Draft was a refusal, not a real answer — treating as failed attempt"
                )

                if attempt < self.max_attempts:
                    current_query = self.llm_client.reformulate_query(
                        query, attempt, previous_attempts=tried_queries
                    )
                    tried_queries.append(current_query)
                    logger.info("Reformulated query -> %r", current_query)
                    continue
                else:
                    break

            # Non-refusal draft — let the self-check be the real judge of
            # whether it's actually supported by the evidence.
            is_supported, reasoning = self.llm_client.check_answer_supported(
                query, snippets, draft_answer
            )
            logger.info(
                "Self-check supported=%s | reasoning=%s", is_supported, reasoning
            )

            step["draft_generated"] = True
            step["self_check"] = is_supported
            step["self_check_reasoning"] = reasoning
            trace.append(step)

            if is_supported:
                trace.append({"final_answer": draft_answer})
                return draft_answer, trace

            # Self-check failed: the matched snippets didn't really answer
            # the question. Reformulate and retry if we have attempts left.
            if attempt < self.max_attempts:
                current_query = self.llm_client.reformulate_query(
                    query, attempt, previous_attempts=tried_queries
                )
                tried_queries.append(current_query)
                logger.info("Reformulated query -> %r", current_query)

        final = (
            "I do not know based on these docs. I tried rephrasing the "
            "question a few different ways and still couldn't find "
            "evidence that actually answers it."
        )
        logger.info("Exhausted %d attempts without a supported answer. Refusing.",
                     self.max_attempts)
        trace.append({"final_answer": final})
        return final, trace