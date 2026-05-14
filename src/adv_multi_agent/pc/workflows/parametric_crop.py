"""
Workflow — Parametric Crop Insurance (Specialty P&C Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to specialty
agricultural underwriting: Multi-Peril Crop Insurance (MPCI), crop-hail,
and parametric weather covers (rainfall index, temperature degree-day,
NDVI-based pasture / rangeland).

This is the **specialty-lines** track of the P&C domain (see D-PC-6):
agricultural risks with USDA-RMA federal-program overlay, where basis
risk (gap between parametric trigger and actual on-farm loss) is the
dominant economic concern and trigger calibration is path-dependent on
climate baselines.

Triple-flag gate (D-PC-4): PERIL-MATCH FLAGS, BASIS FLAGS,
ATTACHMENT FLAGS. **No reviewer veto** — parametric covers are by-design
irrevocable on trigger; the discipline is in the up-front design, not in
a halt directive after trigger.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. RMA / USDA program-rule integration — MPCI is a federally
       reinsured program with prescribed policy terms; production must
       integrate the current Crop Insurance Handbook + Special
       Provisions, not paraphrase.
    2. Authoritative weather-data feed — parametric covers settle on
       data from a specific authoritative source (NOAA, station ID,
       satellite product). Production must lock the source contractually
       and verify station-of-record uptime history.
    3. Yield-history database — APH (Actual Production History) yields
       must be sourced from FSA / RMA records, not declared by the
       producer.
    4. NDVI / remote-sensing pipeline — vegetation-index products
       require structured ingestion (MODIS, Sentinel-2, commercial
       providers); production cannot rely on prose.
    5. Climate-baseline back-test — trigger calibration assumes the
       historical climate distribution; production must back-test against
       at least 20 years of weather data with explicit trend treatment.
    6. Reinsurance (RMA SRA or commercial retro) integration — production
       must reflect Standard Reinsurance Agreement allocation by RMA
       group / state-county combination.
    7. Append-only audit store + dedicated third-model auditor — see
       ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated parametric / crop design is "
    "not an authorised quote or bind. A credentialed agricultural "
    "underwriter and the RMA-approved actuarial review (if MPCI / federal "
    "program) must verify peril match, basis-risk magnitude, and trigger "
    "attachment before any bind is issued."
)

_CROP_REVIEW_CRITERIA = """\
Evaluate this parametric / crop cover design on four dimensions.
Score each 0–10.

1. PERIL MATCH (35%) — CRITICAL
   Does the proposed cover's named peril (or parametric trigger variable)
   actually correlate with the loss pathway the producer experiences in
   this crop / region? Common mismatches: rainfall-index where the loss
   driver is heat stress; degree-day where the loss is from late frost;
   NDVI where the loss is from hail. Flag every peril-vs-loss-pathway
   mismatch under PERIL-MATCH FLAGS:.

2. BASIS RISK (30%) — CRITICAL
   For parametric / index covers, basis risk = gap between trigger
   payout and producer's actual loss. Has it been quantified? Are
   station-of-record vs farm location distance, gridded-product
   resolution, and historical correlation between trigger and yield
   addressed? For MPCI / indemnity, is the APH-vs-RMA-published-yield
   gap acknowledged? Flag every basis-risk gap under BASIS FLAGS:.

3. ATTACHMENT & TERM (25%) — CRITICAL
   Is the attachment point (trigger threshold + retention) calibrated
   against a defensible climate baseline (at least 20-yr back-test, with
   trend treatment)? Is the term aligned with the actual exposure window
   (planting → harvest)? Are scaling parameters (payout-per-unit,
   maximum payout) consistent with insurable interest and not
   over-indemnifying? Flag every attachment / term issue under
   ATTACHMENT FLAGS:.

4. ACTIONABILITY (10%)
   Are bind terms, data-source contract, settlement clause, and producer
   disclosure (especially basis-risk disclosure) specific enough for
   issuance?

Overall score = weighted average.
Score ≥ 7.5 AND zero PERIL-MATCH FLAGS AND zero BASIS FLAGS AND zero
ATTACHMENT FLAGS: cover design is ready for senior agricultural
underwriter review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PERIL-MATCH FLAGS: [bullet list, or "None detected"]
  BASIS FLAGS: [bullet list, or "None detected"]
  ATTACHMENT FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a parametric / crop insurance cover design for a
senior agricultural underwriter to review. You have no stake in the
outcome. Your job is to design a cover whose trigger correlates with
the producer's actual loss pathway, whose basis risk is disclosed and
bounded, and whose attachment is grounded in a defensible climate
baseline.

BASE THE DESIGN ON THE INPUT DATA.

SUBMISSION DATA:
{request_text}

{wiki_context}

Produce a structured cover design with exactly these sections:

## Producer & Crop Summary
Restate the producer, crop / commodity, county / region, acreage, and
APH yield history.

## Peril Identification
The loss pathways the producer faces (drought, freeze, hail, excessive
moisture, heat, named storm, etc.). Rank by historical loss frequency.

## Proposed Cover Structure
Type: MPCI / crop-hail / parametric (rainfall index / degree-day / NDVI /
named storm). Coverage level, attachment, retention, term, payout
scaling, maximum payout. State the data source (authoritative station
ID / satellite product / publication).

## Peril-Match Justification
Map the proposed cover's trigger variable to the dominant loss pathway
identified above. Acknowledge any covered-vs-not-covered loss pathway
explicitly.

## Basis-Risk Quantification
For parametric / index covers: distance from station-of-record to
production location; gridded-product resolution; historical correlation
(R-squared or similar) between trigger and producer's actual yield. For
MPCI / indemnity: APH-vs-RMA-yield gap, T-yield adjustment treatment.

## Climate Baseline & Back-Test
20+ year back-test of trigger behaviour against historical weather.
Loss-cost implied by the trigger over the back-test window. Trend
treatment (de-trended vs as-is).

## Reinsurance / SRA Placement
If MPCI: state / county SRA group, fund designation, retention. If
commercial parametric: retro structure.

## Producer Disclosure
Specific disclosure language for basis risk (parametric) or APH
methodology (MPCI). Must be in plain language.

## Evidence Gaps
Information missing from the inputs that materially affects the design.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this parametric / crop cover design. Address EVERY issue in the
reviewer's critique, especially any PERIL-MATCH FLAGS, BASIS FLAGS, or
ATTACHMENT FLAGS.

PREVIOUS DESIGN:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any PERIL-MATCH FLAG: re-map the trigger variable to the actual
loss pathway or change the trigger variable.
⚠️  For any BASIS FLAG: quantify the basis-risk magnitude and either
narrow it (closer station, finer grid, alternative index) or disclose it
prominently to the producer.
⚠️  For any ATTACHMENT FLAG: re-anchor the attachment point against the
back-tested climate baseline with explicit trend treatment.
"""


@dataclass
class ParametricCropRequest:
    """Structured input for the P&C parametric / crop workflow."""

    producer_summary: str
    """Producer name, operation type, state / county, acreage, organic /
    conventional, production history span."""

    crop_and_yield_history: str
    """Crop / commodity; APH yield history (year-by-year); T-yield
    benchmark; pertinent yield-trend information."""

    loss_history: str
    """Documented prior losses with cause; total dollar loss; uncovered
    losses (gaps between past indemnity and actual)."""

    proposed_cover_type: str
    """MPCI / crop-hail / rainfall-index / degree-day / NDVI / named-storm
    parametric; coverage level; attachment / trigger threshold; term."""

    data_source: str
    """For parametric: station / grid / satellite product + ID; data
    publisher; data-quality history. For MPCI: APH source (FSA records,
    producer-declared)."""

    climate_baseline: str
    """20+ year back-test summary; loss-cost implied by the trigger;
    trend treatment (de-trended / as-is); recent extreme-event years
    that materially shifted the baseline."""

    reinsurance_context: str
    """SRA group designation (if MPCI); commercial retro structure (if
    parametric); aggregate / fund headroom."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Producer summary: {self.producer_summary}",
            f"Crop and yield history: {self.crop_and_yield_history}",
            f"Loss history: {self.loss_history}",
            f"Proposed cover type: {self.proposed_cover_type}",
            f"Data source: {self.data_source}",
            f"Climate baseline: {self.climate_baseline}",
            f"Reinsurance context: {self.reinsurance_context}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "PERIL-MATCH FLAGS:",
    "BASIS FLAGS:",
    "ATTACHMENT FLAGS:",
)


class ParametricCropWorkflow(BaseWorkflow):
    """
    Adversarial parametric / crop cover design: executor drafts cover →
    reviewer challenges peril-vs-loss-pathway match, basis-risk
    magnitude, and attachment / climate-baseline defensibility → iterate.

    Convergence gate (D-PC-4):
        score ≥ threshold
        AND zero PERIL-MATCH FLAGS
        AND zero BASIS FLAGS
        AND zero ATTACHMENT FLAGS

    No reviewer veto: parametric covers settle by-design on trigger;
    discipline is in up-front design, not in a halt after-the-fact.
    """

    async def run(  # type: ignore[override]
        self,
        request: ParametricCropRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial parametric / crop design loop."""
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
                criteria=_CROP_REVIEW_CRITERIA,
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
                "producer_summary": request.producer_summary,
                "proposed_cover_type": request.proposed_cover_type,
                "peril_match_flags": list(dict.fromkeys(accumulated["PERIL-MATCH FLAGS:"])),
                "basis_flags": list(dict.fromkeys(accumulated["BASIS FLAGS:"])),
                "attachment_flags": list(dict.fromkeys(accumulated["ATTACHMENT FLAGS:"])),
                "approver_checklist": approver_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "PERIL-MATCH FLAGS:": (
                "⚠️  PERIL-MATCH FLAGS (re-map trigger variable to the actual loss "
                "pathway or change the trigger):"
            ),
            "BASIS FLAGS:": (
                "⚠️  BASIS FLAGS (quantify basis-risk magnitude; narrow it or "
                "disclose it prominently to the producer):"
            ),
            "ATTACHMENT FLAGS:": (
                "⚠️  ATTACHMENT FLAGS (re-anchor against back-tested climate "
                "baseline with explicit trend treatment):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            flags = current[header]
            if not flags:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}" for f in flags
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: ParametricCropRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["PERIL-MATCH FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  PERIL-MATCH FLAGS "
                f"({len(accumulated['PERIL-MATCH FLAGS:'])}) — re-evaluate trigger "
                "variable against on-farm loss pathway"
            )
        if accumulated["BASIS FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  BASIS FLAGS ({len(accumulated['BASIS FLAGS:'])}) — "
                "quantify station / grid / yield basis risk; producer disclosure draft"
            )
        if accumulated["ATTACHMENT FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  ATTACHMENT FLAGS ({len(accumulated['ATTACHMENT FLAGS:'])}) — "
                "rerun 20-yr climate back-test with explicit trend treatment"
            )
        checklist.extend([
            "[ ] Confirm data source contract (station / grid / satellite product + ID)",
            "[ ] Senior agricultural underwriter review",
            f"[ ] Confirm RMA / commercial-retro routing for: {request.proposed_cover_type[:60]}",
            "[ ] Producer basis-risk disclosure in plain language (parametric only)",
            "[ ] Back-test re-run if climate trend changed materially in last 3 yrs",
            "[ ] Issue bind — AI output must not trigger automatic policy issuance",
        ])
        return checklist
