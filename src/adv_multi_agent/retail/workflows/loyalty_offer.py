"""
Workflow — Loyalty / Personalization Offer (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for retail loyalty-offer
design. Executor drafts a segment-targeted offer; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges fairness,
margin, and gaming risk.

Mirrors the parole bias-gate (D9) applied to a commercial decision:
segment criteria must derive only from allowlisted customer attributes;
any derivation from a denylisted attribute (or known proxy) is a
FAIRNESS FLAG.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Customer-data platform integration — segment criteria are free-text;
       production requires a CDP query with field-level lineage so the
       allowlist / denylist can be enforced at query time, not by LLM
       inspection.
    2. Margin model — margin_floor + projected lift are caller-supplied;
       production should compute contribution margin from actual basket
       data including cannibalization across the household.
    3. Legal sign-off gate — segment definitions touching protected-class
       proxies must be reviewed by legal before any campaign launches.
    4. Gaming-detection telemetry — actual exploit-path discovery comes
       from post-launch transaction monitoring, not pre-launch LLM
       hypothesising. Treat the GAMING FLAGS output as a *prompt for
       analyst review*, not as a complete inventory.
    5. Dedicated third-model fairness auditor — this workflow folds the
       fairness audit into the same reviewer that scores quality. Production
       should run a separately configured model (different family from
       BOTH executor and reviewer) whose only job is protected-class-proxy
       detection against a maintained denylist. See ARIS §3.1.
    6. Approval store — every approved offer should write to an append-only
       audit log naming the human approver, the allowed/disallowed lists in
       force at approval time, and the projected margin curve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt, truncate_flag_display
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated offer is not a launch-ready "
    "campaign. Legal must review segment criteria for protected-class "
    "proxies; finance must confirm margin math; ops must stress-test the "
    "gaming paths against actual customer behaviour. AI output must never "
    "trigger an automated campaign launch."
)

_OFFER_REVIEW_CRITERIA = """\
Evaluate this loyalty offer on five dimensions. Score each 0–10.

1. FAIRNESS (30%) — CRITICAL
   Does the segment criterion derive ONLY from fields on the stated
   allowed_attributes list? Flag every criterion derived from a field on
   the disallowed_attributes list — or from a known proxy for one. Common
   proxies to challenge: ZIP code → race/income; language preference →
   ethnicity/national origin; first-name n-grams → gender/ethnicity;
   household composition inferred from basket → family status; device or
   payment-method patterns → income. Flag under FAIRNESS FLAGS:.

2. MARGIN (25%)
   Does the projected per-unit contribution margin stay at or above the
   stated margin_floor AFTER accounting for: discount depth, expected
   cannibalization, fulfilment cost lift (if applicable), and free-rider
   redemption by customers who would have purchased anyway? Flag every
   case where margin math leaves the floor under MARGIN FLAGS:.

3. GAMING RISK (20%)
   Is there a structural exploit a material fraction of customers could
   take to redeem disproportionate value (basket-splitting, multi-account,
   threshold-bumping returns, gift-card laundering)? Flag plausible paths
   under GAMING FLAGS:.

4. SEGMENT REACH (15%)
   Is the segment large enough to matter and small enough to be defensible?
   Is the size estimate traceable to an allowed attribute?

5. ACTIONABILITY (10%)
   Is the offer specific: discount mechanism, redemption window, channels,
   exclusions, success metric, kill criteria?

Overall score = weighted average.
Score ≥ 7.5 AND zero FAIRNESS FLAGS AND zero MARGIN FLAGS AND zero
GAMING FLAGS: offer is ready for legal + finance review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  FAIRNESS FLAGS: [bullet list, or "None detected"]
  MARGIN FLAGS: [bullet list, or "None detected"]
  GAMING FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are designing a loyalty / personalization offer for a human CMO + legal
review. You have no marketing-volume incentive — your job is to design an
offer that is provably fair, margin-positive, and exploit-resistant.

BASE THE SEGMENT DEFINITION STRICTLY ON THE ALLOWED ATTRIBUTES BELOW. Do
NOT define the segment using any disallowed attribute or known proxy for
one. State explicitly which allowed attribute each segment criterion
derives from.

OFFER REQUEST:
{request_text}

{wiki_context}

Produce a structured offer design with exactly these sections:

## Segment Definition
Describe who qualifies. For each segment criterion, name the ALLOWED
attribute it derives from. If any criterion cannot be traced to an
allowed attribute, REMOVE it — do not paraphrase.

## Offer Mechanics
Discount mechanism, threshold (if any), redemption window, channels,
exclusions, max uses per customer.

## Margin Math
Per-unit contribution margin before and after the offer. Account for:
discount depth, cannibalization, fulfilment cost lift, free-rider
redemption. State each assumption explicitly.

## Gaming Paths Considered
Enumerate at least three plausible exploit paths and the mitigation for
each. If a path has no mitigation, say so.

## Success Metric + Kill Criteria
What metric defines success (margin-positive uplift vs control)? What
threshold or window triggers an early kill?

## Evidence Gaps
Information missing from the inputs that materially affects fairness,
margin, or gaming assessment.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this loyalty offer. Address EVERY issue in the reviewer's critique,
especially any FAIRNESS / MARGIN / GAMING flags.

PREVIOUS OFFER:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any FAIRNESS FLAG: remove the segment criterion derived from a
disallowed attribute or proxy. Do not rephrase to obscure the derivation.
⚠️  For any MARGIN FLAG: re-do the margin math with the missing factor;
if the floor cannot be held, either narrow the discount or kill the offer.
⚠️  For any GAMING FLAG: add a mitigation, or remove the offer feature
that creates the exploit path.
"""

# Caps on list fields — defence-in-depth on the request boundary so a
# pathological caller cannot push thousands of "attributes" into the
# prompt. Per-element string sanitisation is via sanitize_for_prompt.
_MAX_ATTRIBUTE_ENTRIES = 64
_MAX_ATTRIBUTE_CHARS = 200
# L-PC-3: per-field cap for str fields in to_prompt_text.
_MAX_FIELD_CHARS = 1500


def _render_attribute_list(label: str, items: list[str]) -> str:
    if not items:
        return f"{label}: (none specified)"
    capped = items[:_MAX_ATTRIBUTE_ENTRIES]
    rendered = ", ".join(
        sanitize_for_prompt(item, max_chars=_MAX_ATTRIBUTE_CHARS) for item in capped
    )
    suffix = ""
    if len(items) > _MAX_ATTRIBUTE_ENTRIES:
        suffix = f" (… +{len(items) - _MAX_ATTRIBUTE_ENTRIES} truncated)"
    return f"{label}: {rendered}{suffix}"


@dataclass
class LoyaltyOfferRequest:
    """Structured input for the loyalty-offer workflow."""

    customer_segment: str
    """Name + size + qualitative description of the target segment."""

    offer_proposal: str
    """Discount / bundle / threshold being considered."""

    historical_response: str
    """Past loyalty-program performance for similar offers."""

    margin_floor: str
    """Minimum acceptable per-unit contribution margin (with unit, e.g. '$0.85')."""

    allowed_attributes: list[str] = field(default_factory=list)
    """Allowlist of customer fields the segment may be derived from."""

    disallowed_attributes: list[str] = field(default_factory=list)
    """Denylist of customer fields and known proxies for protected classes."""

    competing_offers: str = ""
    """Concurrent promos or competitor offers that may affect lift / cannibalization."""

    gaming_risk: str = ""
    """Caller-identified gaming paths (do not rely on this alone; reviewer challenges further)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Customer segment: {self.customer_segment[:cap]}",
            f"Offer proposal: {self.offer_proposal[:cap]}",
            f"Historical response: {self.historical_response[:cap]}",
            f"Margin floor: {self.margin_floor[:cap]}",
            _render_attribute_list("Allowed attributes", self.allowed_attributes),
            _render_attribute_list("Disallowed attributes (incl. proxies)", self.disallowed_attributes),
            f"Competing offers: {self.competing_offers[:cap]}",
            f"Known gaming risks: {self.gaming_risk[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = ("FAIRNESS FLAGS:", "MARGIN FLAGS:", "GAMING FLAGS:")


class LoyaltyOfferWorkflow(BaseWorkflow):
    """
    Adversarial loyalty-offer design: executor drafts segment + offer →
    reviewer challenges fairness, margin math, and gaming risk → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero FAIRNESS FLAGS
        AND zero MARGIN FLAGS
        AND zero GAMING FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: LoyaltyOfferRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial offer-design loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=self._format_flag_section(current),
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_OFFER_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not any(current.values()):
                converged = True
                break

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "segment_name": sanitize_for_prompt(
                    request.customer_segment, max_chars=200
                ),
                "fairness_flags": list(dict.fromkeys(accumulated["FAIRNESS FLAGS:"])),
                "margin_flags": list(dict.fromkeys(accumulated["MARGIN FLAGS:"])),
                "gaming_flags": list(dict.fromkeys(accumulated["GAMING FLAGS:"])),
                "approver_checklist": approver_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        parts: list[str] = []
        banner = {
            "FAIRNESS FLAGS:": (
                "⚠️  FAIRNESS FLAGS (remove segment criteria derived from disallowed "
                "attributes or proxies):"
            ),
            "MARGIN FLAGS:": (
                "⚠️  MARGIN FLAGS (re-do margin math; narrow the discount or kill "
                "the offer if floor cannot be held):"
            ),
            "GAMING FLAGS:": (
                "⚠️  GAMING FLAGS (add a mitigation, or remove the feature that creates "
                "the exploit path):"
            ),
        }
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(items)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: LoyaltyOfferRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["FAIRNESS FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  FAIRNESS FLAGS DETECTED ({len(accumulated['FAIRNESS FLAGS:'])}) — "
                "legal review of segment derivation before any campaign launch"
            )
        if accumulated["MARGIN FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  MARGIN FLAGS DETECTED ({len(accumulated['MARGIN FLAGS:'])}) — "
                "finance must reconfirm margin math against actual basket data"
            )
        if accumulated["GAMING FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  GAMING FLAGS DETECTED ({len(accumulated['GAMING FLAGS:'])}) — "
                "ops + risk team must instrument detection for each path"
            )
        checklist.extend([
            f"[ ] Legal review of segment '{request.customer_segment}' against "
            "company protected-class policy AND current denylist",
            f"[ ] Finance sign-off: contribution margin ≥ stated floor ({request.margin_floor}) "
            "across the redemption window",
            "[ ] Ops + risk: instrument gaming-detection telemetry before launch",
            "[ ] CMO approval — AI output must not trigger an automated campaign launch",
            "[ ] Kill-criteria + monitoring window committed to operational runbook",
        ])
        return checklist
