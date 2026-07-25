"""
Workflow — HCT/P Regulatory-Tier Classification Review (Lifesciences · Advanced
Therapies / CGT, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the 361-vs-351
classification of a human cell/tissue product: executor argues the lower-burden
361 HCT/P tier; reviewer (cross-model per ARIS §2.1) challenges more-than-minimal
manipulation, non-homologous use, a disqualifying combination, or a systemic
effect that forces the product into the 351 biologic tier (a BLA), with the power
to VETO when a 351 biologic is asserted as a 361 HCT/P.

A 361 HCT/P must satisfy ALL FOUR 21 CFR 1271.10(a) prongs conjunctively:
(1) minimal manipulation, (2) homologous use, (3) not combined with another
article (except water / crystalloids / a sterilizing-preserving-storage agent),
and (4) no systemic effect and not dependent on the metabolic activity of living
cells — unless autologous / first-or-second-degree-relative / reproductive use.

Scenario scoping (D-LIFESCI-7): the 361 argument is only live for
minimally-manipulated cellular / structural-tissue products; genetically-modified
cells and viral-vector gene therapies are categorically 351 and must not be
authored as 361-candidate scenarios.

Veto gate (D-LIFESCI-8): fires when a 351 biologic is asserted as a 361 HCT/P
(more-than-minimal manipulation, non-homologous use, disqualifying combination, or
systemic effect present) — a classification that would bypass the BLA and
misrepresent the product's regulatory status.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Cell/tissue-processing manufacturing-execution system — the manufacturing
       steps should resolve against the controlled MES, not caller-pasted text.
    2. 21 CFR 1271 tissue-reference / decision-tree engine — the four-prong
       determination should reconcile against the controlled decision-tree engine.
    3. Regulatory-precedent database — prior Request-for-Designation / untitled-
       letter precedents should resolve against the controlled precedent archive.
    4. Qualified RA approver gate — every AI-suggested tier conclusion must be
       confirmed by a qualified Regulatory Affairs lead (CBER pathway). Output is
       never a filed classification position.
    5. Dedicated third-model classification auditor — production should use a
       separately configured auditor model for tier-inflation bias detection.
       See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated HCT/P regulatory-tier classification is "
    "decision-support, not a regulatory determination and not legal advice. A "
    "qualified Regulatory Affairs lead (CBER pathway) must independently confirm "
    "the four 21 CFR 1271.10(a) prongs before any classification position is "
    "taken. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "product is a 351 biologic, not a 361 HCT/P; asserting the 361 tier would "
    "bypass the BLA and misrepresent the product's regulatory status. See "
    "metadata['veto_reason']. Escalate to Regulatory Affairs (CBER pathway)."
)

_FLAG_HEADERS = ("MINIMAL-MANIPULATION FLAGS:", "HOMOLOGOUS-USE FLAGS:", "TIER-CLASSIFICATION FLAGS:")

_HCTP_REVIEW_CRITERIA = """\
Evaluate this HCT/P regulatory-tier classification on five dimensions. Score each 0–10.
A 361 HCT/P must satisfy ALL FOUR 21 CFR 1271.10(a) prongs; assess each.

1. MINIMAL MANIPULATION — prong (1) (30%) — CRITICAL
   Does processing keep the cells/tissue minimally manipulated (relevant
   biological characteristics unaltered for structural tissue; relevant
   characteristics unaltered for cells)? Penalise processing that alters the
   relevant characteristics. Flag under MINIMAL-MANIPULATION FLAGS:.

2. HOMOLOGOUS USE — prong (2) (25%) — CRITICAL
   Is the intended use homologous to the tissue's original basic function?
   Penalise a non-homologous intended use. Flag under HOMOLOGOUS-USE FLAGS:.

3. TIER CLASSIFICATION — prongs (3) and (4) plus the overall call (25%) — CRITICAL
   Prong (3): is the product NOT combined with another article (except water,
   crystalloids, or a sterilizing / preserving / storage agent)? Prong (4): is
   there NO systemic effect and NO dependence on the metabolic activity of living
   cells (unless autologous / first- or second-degree relative / reproductive
   use)? Does the overall 361-vs-351 call follow from all four prongs? Penalise a
   disqualifying combination, a systemic effect, or a 361 call that ignores a
   failed prong. Flag under TIER-CLASSIFICATION FLAGS:.

4. PRECEDENT CONSISTENCY (10%)
   Is the tier consistent with cited regulatory precedent for comparable products?
   Penalise a call inconsistent with precedent.

5. ACTIONABILITY (10%)
   Is each finding specific enough for RA to resolve (which prong, which
   processing step, which use)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 351 biologic is asserted as a 361 HCT/P — more-than-minimal
manipulation, non-homologous use, a disqualifying combination, or a systemic
effect is present — such that the 361 call would bypass the BLA and misrepresent
regulatory status.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero MINIMAL-MANIPULATION FLAGS AND zero HOMOLOGOUS-USE FLAGS AND
zero TIER-CLASSIFICATION FLAGS AND no VETO: ready for Regulatory Affairs sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  MINIMAL-MANIPULATION FLAGS: [bullet list, or "None detected"]
  HOMOLOGOUS-USE FLAGS: [bullet list, or "None detected"]
  TIER-CLASSIFICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are classifying a human cell/tissue product as a 361 HCT/P (no premarket
approval) or a 351 biologic (requires a BLA) for a qualified Regulatory Affairs
lead. You have no stake in the outcome. Apply ALL FOUR 21 CFR 1271.10(a) prongs —
minimal manipulation, homologous use, not-combined-with-another-article, and no
systemic effect / no dependence on metabolic activity — grounded only in the data
supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

HCT/P CLASSIFICATION DATA:
{request_text}

{wiki_context}

Produce a structured classification with exactly these sections:

## Minimal manipulation (prong 1)
State whether processing keeps the product minimally manipulated; identify any
step that alters the relevant biological characteristics.

## Homologous use (prong 2)
State whether the intended use is homologous to the tissue's original basic
function; identify any non-homologous use.

## Combination and systemic effect (prongs 3 and 4)
State whether the product is combined with another article (beyond the allowed
exceptions) and whether it has a systemic effect or depends on the metabolic
activity of living cells.

## Tier conclusion
State whether the product is a 361 HCT/P or a 351 biologic, following from all
four prongs.

## Precedent
State whether the tier is consistent with cited regulatory precedent.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this HCT/P tier classification. Address EVERY issue in the reviewer's
critique, especially any MINIMAL-MANIPULATION FLAGS, HOMOLOGOUS-USE FLAGS, or
TIER-CLASSIFICATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any MINIMAL-MANIPULATION flag: show processing keeps the relevant
characteristics unaltered, or acknowledge more-than-minimal manipulation (351).
⚠️  For any HOMOLOGOUS-USE flag: show the use is homologous, or acknowledge
non-homologous use (351).
⚠️  For any TIER-CLASSIFICATION flag: resolve the combination / systemic-effect
prong, or acknowledge the product is a 351 biologic.
"""


@dataclass
class HCTPClassificationRequest:
    """Structured input for the HCT/P regulatory-tier classification review."""

    product_description: str
    """Generic product category (e.g. a minimally-processed structural-tissue allograft)."""

    cellular_tissue_source: str
    """Source: autologous / allogeneic; tissue type."""

    manufacturing_steps: str
    """Processing steps applied to the cells/tissue."""

    minimal_manipulation_rationale: str
    """Rationale for why processing is (or is not) minimal manipulation."""

    intended_use_homology: str
    """Intended use and whether it is homologous to the tissue's original function."""

    combination_with_another_article: str
    """Whether the product is combined with another article (drug/device/other)."""

    systemic_effect_or_metabolic_dependence: str
    """Whether the product has a systemic effect or depends on living-cell metabolism."""

    proposed_regulatory_tier: str
    """The proposed tier (361 HCT/P or 351 biologic)."""

    precedent_determinations: str
    """Cited regulatory precedent for comparable products."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Cellular / tissue source: {self.cellular_tissue_source[:cap]}",
            f"Manufacturing steps: {self.manufacturing_steps[:cap]}",
            f"Minimal-manipulation rationale: {self.minimal_manipulation_rationale[:cap]}",
            f"Intended use / homology: {self.intended_use_homology[:cap]}",
            f"Combination with another article: {self.combination_with_another_article[:cap]}",
            f"Systemic effect / metabolic dependence: {self.systemic_effect_or_metabolic_dependence[:cap]}",
            f"Proposed regulatory tier: {self.proposed_regulatory_tier[:cap]}",
            f"Precedent determinations: {self.precedent_determinations[:cap]}",
        ])


class HCTPClassificationWorkflow(BaseWorkflow):
    """
    Adversarial HCT/P regulatory-tier classification: executor argues the 361 tier
    → reviewer challenges more-than-minimal manipulation, non-homologous use, a
    disqualifying combination, or a systemic effect that forces 351, with the
    power to VETO → iterate.

    Convergence gate (D-LIFESCI-8):
        score ≥ threshold (8.0)
        AND zero MINIMAL-MANIPULATION FLAGS
        AND zero HOMOLOGOUS-USE FLAGS
        AND zero TIER-CLASSIFICATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the wiki.
    The verbatim veto directive is recorded in metadata['veto_reason'];
    metadata['first_draft'] captures the clean executor draft from the vetoed round.
    """

    async def run(  # type: ignore[override]
        self,
        request: HCTPClassificationRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        veto_reason: str | None = None
        max_wiki_chars = config.max_wiki_body_chars

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = self._format_flag_section(current)
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_HCTP_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        hctp_checklist = self._build_hctp_checklist(request, accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "minimal_manipulation_flags": list(
                dict.fromkeys(accumulated["MINIMAL-MANIPULATION FLAGS:"])
            ),
            "homologous_use_flags": list(dict.fromkeys(accumulated["HOMOLOGOUS-USE FLAGS:"])),
            "tier_classification_flags": list(
                dict.fromkeys(accumulated["TIER-CLASSIFICATION FLAGS:"])
            ),
            "hctp_checklist": hctp_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            metadata["first_draft"] = output

        return WorkflowResult(
            output=output_with_banner,
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata=metadata,
        )

    @staticmethod
    def _extract_veto(critique: str, max_chars: int) -> str | None:
        """Thin delegate to `core._internal.extract_veto_directive` (M-PC-1)."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "MINIMAL-MANIPULATION FLAGS:": (
                "⚠️  MINIMAL-MANIPULATION FLAGS (show processing keeps the relevant "
                "characteristics unaltered, or acknowledge 351):"
            ),
            "HOMOLOGOUS-USE FLAGS:": (
                "⚠️  HOMOLOGOUS-USE FLAGS (show the use is homologous, or acknowledge "
                "non-homologous use / 351):"
            ),
            "TIER-CLASSIFICATION FLAGS:": (
                "⚠️  TIER-CLASSIFICATION FLAGS (resolve the combination / "
                "systemic-effect prong, or acknowledge the product is a 351 biologic):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            flags = current[header]
            if not flags:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(flags)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return (
            f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
            f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
        )

    @staticmethod
    def _build_hctp_checklist(
        request: HCTPClassificationRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Regulatory Affairs Lead (CBER pathway)]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not assert the 361 HCT/P tier; escalate to "
                "Regulatory Affairs (CBER pathway) and pursue the BLA (351) path"
            )
        mm_flags = accumulated.get("MINIMAL-MANIPULATION FLAGS:", [])
        hu_flags = accumulated.get("HOMOLOGOUS-USE FLAGS:", [])
        tier_flags = accumulated.get("TIER-CLASSIFICATION FLAGS:", [])
        if mm_flags:
            checklist.append(
                f"[ ] ⚠️  MINIMAL-MANIPULATION FLAGS ({len(mm_flags)}) — confirm "
                "processing keeps the relevant characteristics unaltered"
            )
        if hu_flags:
            checklist.append(
                f"[ ] ⚠️  HOMOLOGOUS-USE FLAGS ({len(hu_flags)}) — confirm the intended "
                "use is homologous to the original basic function"
            )
        if tier_flags:
            checklist.append(
                f"[ ] ⚠️  TIER-CLASSIFICATION FLAGS ({len(tier_flags)}) — resolve the "
                "combination / systemic-effect prong before any 361 call"
            )
        checklist.extend([
            "[ ] Confirm all four 1271.10(a) prongs are satisfied before a 361 call",
            "[ ] Confirm the intended use is homologous",
            "[ ] Confirm no disqualifying combination or systemic effect",
            "[ ] Obtain Regulatory Affairs sign-off before any classification position",
        ])
        return checklist
