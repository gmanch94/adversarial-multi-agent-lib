"""
Workflow 1 — Idea Discovery (ARIS §4.1)

Three phases:
  1. Literature survey  — executor summarises relevant prior work
  2. Novelty check      — reviewer flags overlap with known work
  3. Proposal           — executor produces a refined research proposal

The proposal feeds into AutoReviewLoop for iterative refinement.
"""
from __future__ import annotations

from typing import Any

from ...core.wiki import EntryKind
from ...core.workflow import BaseWorkflow, WorkflowResult

SURVEY_PROMPT = """\
You are conducting a focused literature survey on the following topic.

### Topic
{topic}

### Instructions
- Summarise the 5-10 most relevant recent works (2020–present).
- For each work: authors, year, key contribution, limitation.
- Identify open problems and under-explored directions.
- End with a section "## Candidate Directions" listing 3–5 concrete research ideas.

Base your survey on your training knowledge. Cite papers as accurately as possible.
"""

NOVELTY_CHECK_PROMPT = """\
You are a senior reviewer evaluating the novelty of research directions.

### Topic
{topic}

### Candidate directions from literature survey
{directions}

### Instructions
For each direction, answer:
1. Is this direction substantially covered by existing work? (yes/no + brief justification)
2. What is the most closely related paper?
3. What gap remains if the direction is pursued?

End with a ranked list "## Ranked Directions" (most novel first).
Return your assessment as structured text following the format above.
"""

PROPOSAL_PROMPT = """\
You are writing a one-page research proposal.

### Topic
{topic}

### Novelty assessment
{novelty}

### Wiki context
{wiki_context}

### Instructions
Write a structured proposal covering:
- **Motivation** — why this matters now
- **Hypothesis** — the central testable claim
- **Method** — how you would test it (2-3 concrete steps)
- **Expected contribution** — what success looks like
- **Risks** — two main failure modes

Be specific. Avoid generic phrases. This will feed into a full auto-review loop.
"""


class IdeaDiscovery(BaseWorkflow):
    """
    Discovers and refines research ideas for a given topic.

    Returns a WorkflowResult whose `output` is a one-page research proposal.
    The `metadata` dict contains the raw survey and novelty assessment.
    """

    async def run(  # type: ignore[override]
        self,
        topic: str,
        **_: Any,
    ) -> WorkflowResult:
        # Phase 1: literature survey
        survey = await self.executor.run(SURVEY_PROMPT.format(topic=topic))
        self.wiki.add(EntryKind.LITERATURE, f"Survey: {topic}", survey, tags=["survey"])

        directions = self._extract_section(survey, "## Candidate Directions")

        # Phase 2: novelty check (reviewer acts as adversarial evaluator)
        novelty_prompt = NOVELTY_CHECK_PROMPT.format(topic=topic, directions=directions)
        novelty = await self.reviewer.run(novelty_prompt)
        self.wiki.add(EntryKind.NOTE, f"Novelty check: {topic}", novelty, tags=["novelty"])

        # Phase 3: proposal
        wiki_ctx = self.wiki.context_for_round(0)
        proposal_prompt = PROPOSAL_PROMPT.format(
            topic=topic,
            novelty=novelty,
            wiki_context=wiki_ctx,
        )
        proposal = await self.executor.run(proposal_prompt)
        self.wiki.add(
            EntryKind.HYPOTHESIS,
            f"Proposal: {topic}",
            proposal,
            tags=["proposal"],
        )

        return WorkflowResult(
            output=proposal,
            rounds=3,
            final_score=0.0,   # scored by downstream AutoReviewLoop
            converged=True,
            metadata={"survey": survey, "novelty": novelty},
        )

    @staticmethod
    def _extract_section(text: str, header: str) -> str:
        if header not in text:
            return text
        after = text.split(header, 1)[1]
        # Stop at the next ## section if present
        next_section = after.find("\n##")
        return after[:next_section].strip() if next_section != -1 else after.strip()
