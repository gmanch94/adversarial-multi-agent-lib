"""
5-pass scientific editing pipeline (ARIS §4.3).

Pass 1 — Clutter removal:       eliminate filler, hedge stacking, redundancy
Pass 2 — Active voice:          passive → active where appropriate
Pass 3 — Sentence structure:    vary length, fix run-ons, clarify ambiguous antecedents
Pass 4 — Terminology:           enforce consistent use of defined terms
Pass 5 — Numerical consistency: verify all numbers, percentages, dates are self-consistent

Each pass is an independent executor call; the reviewer spot-checks after pass 5.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core._internal import parse_first_json_or
from ..core.agents import ExecutorAgent, ReviewerAgent
from ..core.config import Config

# Rough upper bound to keep pass prompts inside the 1M-token context window
# with comfortable headroom. ~4 chars/token → 200K chars ≈ 50K tokens per pass.
_MAX_INPUT_CHARS = 200_000

PASS_PROMPTS: dict[int, str] = {
    1: """\
Pass 1 — Clutter removal.

Remove:
- Filler phrases ("it is worth noting that", "in order to", "the fact that")
- Stacked hedges ("it might possibly be the case")
- Redundant pairs ("each and every", "first and foremost")
- Throat-clearing introductions

Return ONLY the revised text. Do not explain changes.

### Text
{text}
""",
    2: """\
Pass 2 — Active voice.

Convert passive constructions to active where the subject is known and active voice
is clearer. Preserve passive when the subject is unknown or when passive is conventional
in the discipline (e.g., "participants were randomly assigned").

Return ONLY the revised text.

### Text
{text}
""",
    3: """\
Pass 3 — Sentence structure.

- Break sentences longer than 40 words into two.
- Fix comma splices and run-on sentences.
- Resolve ambiguous pronoun antecedents.
- Vary sentence length: avoid three+ consecutive sentences of the same length.

Return ONLY the revised text.

### Text
{text}
""",
    4: """\
Pass 4 — Terminology consistency.

- Identify all technical terms and abbreviations introduced in the text.
- Ensure each term is used identically throughout (no synonym switching for key concepts).
- Ensure every abbreviation is defined on first use.
- Flag any term used before it is defined with [UNDEFINED: term].

Return ONLY the revised text.

### Text
{text}
""",
    5: """\
Pass 5 — Numerical consistency.

- Identify all numbers, percentages, dates, and statistics.
- Check that every number mentioned more than once is identical across occurrences.
- Flag mismatches as [MISMATCH: "X% in para 2 vs Y% in para 5"].
- Do NOT change values — only flag inconsistencies for human review.

Return ONLY the revised text with any [MISMATCH: ...] annotations.

### Text
{text}
""",
}

SPOT_CHECK_PROMPT = """\
You are reviewing a 5-pass edited scientific text.

### Edited text
{text}

### Original text
{original}

Check for:
1. Any introduced errors not in the original.
2. Any [UNDEFINED: ...] or [MISMATCH: ...] flags that need human resolution.
3. Overall readability improvement (yes/no).

Return JSON:
{{
  "introduced_errors": ["..."],
  "flags_needing_attention": ["..."],
  "readability_improved": true|false,
  "notes": "..."
}}
"""


@dataclass
class EditingReport:
    original: str
    final: str
    pass_outputs: dict[int, str] = field(default_factory=dict)
    introduced_errors: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    readability_improved: bool = True
    notes: str = ""


class ScientificEditor:
    """
    Runs the 5-pass editing pipeline on a piece of text.

    Usage:
        editor = ScientificEditor(config)
        report = await editor.edit(text)
        print(report.final)
    """

    def __init__(
        self,
        config: Config,
        executor: ExecutorAgent | None = None,
        reviewer: ReviewerAgent | None = None,
    ) -> None:
        self.config = config
        self.executor = executor or ExecutorAgent(config)
        self.reviewer = reviewer or ReviewerAgent(config)

    async def edit(self, text: str) -> EditingReport:
        if not isinstance(text, str):
            raise TypeError(f"edit() expected str, got {type(text).__name__}")
        if len(text) > _MAX_INPUT_CHARS:
            raise ValueError(
                f"input length {len(text)} exceeds max {_MAX_INPUT_CHARS} chars; "
                "chunk the document before editing"
            )

        original = text
        current = text
        pass_outputs: dict[int, str] = {}

        for pass_num in range(1, 6):
            prompt = PASS_PROMPTS[pass_num].format(text=current)
            current = await self.executor.run(prompt)
            pass_outputs[pass_num] = current

        # Spot-check by reviewer
        spot_check_raw = await self.reviewer.run(
            SPOT_CHECK_PROMPT.format(text=current, original=original)
        )
        spot = self._parse_spot_check(spot_check_raw)

        return EditingReport(
            original=original,
            final=current,
            pass_outputs=pass_outputs,
            introduced_errors=self._as_str_list(spot.get("introduced_errors")),
            flags=self._as_str_list(spot.get("flags_needing_attention")),
            readability_improved=bool(spot.get("readability_improved", True)),
            notes=str(spot.get("notes") or ""),
        )

    @staticmethod
    def _parse_spot_check(raw: str) -> dict[str, Any]:
        data = parse_first_json_or(raw, default={})
        if not isinstance(data, dict):
            return {
                "introduced_errors": [],
                "flags_needing_attention": [],
                "readability_improved": True,
                "notes": raw[:200],
            }
        return data

    @staticmethod
    def _as_str_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(v) for v in value]
