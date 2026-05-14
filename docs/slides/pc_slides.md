---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Specialized B2B P&C Insurance
## Adversarial Multi-Agent across 7 P&C Workflows

Foundational + Specialty · Technical · Design · Safety Reference

&nbsp;

*Domain application of the adv-multi-agent library*
*Product & Engineering Leadership · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# 1. Problem Context

*Why adversarial multi-agent for specialized commercial P&C?*

---

## The Three Properties

Specialized commercial P&C concentrates the three properties ARIS targets:

| Property | P&C manifestation |
|---|---|
| **Irreversibility** | Bound policy, set reserve, paid claim — each crystallises a $-figure or coverage decision that can only be revised at cost |
| **Regulator audit-trail** | NAIC market-conduct exams; SOX reserve-adequacy reviews; state DOI rate filings; EPA / CERCLA enforcement; state AG worker-classification audits — all leave durable records |
| **Asymmetric information** | Insured knows site history / control maturity / classification posture better than underwriter; claimant knows loss scope better than adjuster |

Echo-chamber risk is concrete: precedent-bias in claims/underwriting + same-family LLM replication of that bias = systematic under- or over-reserving, mis-categorised binds, mis-attested controls.

> Cross-family reviewer is the safeguard.

---

## The Scale & Stakes Problem

P&C specialty decisions are lower-volume than retail but higher-stake per decision:

| Decision | Frequency | Per-instance stake |
|---|---|---|
| Claims reserve (per bodily-injury / property loss) | Per claim (~$M scale) | SOX restatement; NAIC exam |
| Coverage / bad-faith decision | Per disputed claim | Punitive damages; class-rep exposure |
| Complex commercial bind | Per renewal | $50k–$10M premium; aggregate cap |
| Cyber bind | Per renewal | $1M–$25M tower; systemic-event correlated loss |
| Environmental claim/bind | Per site | Long-tail 10-30 yr; NRD; CERCLA |
| Parametric crop cover | Per crop season | Basis-risk producer litigation |
| Gig-platform bind | Per renewal | Class-action; misclassification audit |

A confident-but-wrong LLM at this scale produces SOX-restatement-class errors, bad-faith liability, retroactive coverage exposure, and silent producer-disclosure violations.

> Human review of every recommendation is required — but auditing the *recommendation engine* improves the human's leverage.

---

## The Cross-Model Solution

Two models from different families propose and challenge the same recommendation. Failures correlated within a model family are caught by the other:

```
pc.*Request   (7 workflow variants across 2 tracks)
  │
  ▼
Executor (Claude Opus 4.7, adaptive thinking)
  │  produces evidence-grounded advisory brief
  ▼
Reviewer (GPT-4o — different family, multi-mandate)
  │  1. Quality audit                   (score 0–10)
  │  2. Domain audit                    (2–3 flag classes per workflow)
  │  3. Reviewer veto                   (4 workflows — irreversible-decision gate)
  ▼
score ≥ threshold AND zero domain flags AND no veto?
  YES → converged, return output
  NO  → executor revises (critique + flags injected)
         repeat until convergence or MAX_REVIEW_ROUNDS
```

**Convergence is a conjunction** — quality gate *and* every domain-flag class clear *and* (for veto-using workflows) no veto.

---

<!-- _class: section -->

# 2. Two Tracks

*Foundational + Specialty — D-PC-6*

---

## Foundational (mainstream commercial)

The shapes broadly applicable across commercial P&C:

| # | Workflow | Pattern | Veto? |
|---|---|---|---|
| 1 | `ClaimsReserveWorkflow` | triple-flag (RESERVE / PRECEDENT / LITIGATION) | ✅ |
| 2 | `CoverageDecisionWorkflow` | dual-flag (WORDING / CASE-LAW) | ✅ |
| 3 | `CommercialUnderwritingWorkflow` | triple-flag (LOSS-COST / EXCLUSION / CAPACITY) | ❌ |
| 4 | `CyberUnderwritingWorkflow` | triple-flag (CONTROL-GAP / SUB-LIMIT / AGGREGATION) | ❌ |

Veto criteria: SOX-restatement risk on reserve, bad-faith exposure on coverage decision. Underwriting binds are reversible at renewal — capacity discipline is the gate, not life-safety halt.

---

## Specialty (niche commercial)

Per D-PC-6 — the markets industry usage means by *specialized* P&C:

| # | Workflow | Pattern | Veto? |
|---|---|---|---|
| 5 | `EnvironmentalImpairmentWorkflow` | triple-flag (KNOWN-CONDITION / TAIL / REGULATORY-OVERLAP) | ✅ |
| 6 | `ParametricCropWorkflow` | triple-flag (PERIL-MATCH / BASIS / ATTACHMENT) | ❌ |
| 7 | `GigPlatformLiabilityWorkflow` | triple-flag (CLASSIFICATION / COVERAGE-GAP / REGULATORY-PATCHWORK) | ✅ |

**Deferred specialty** (per D-PC-6): group captive allocation, equine mortality. Build only on concrete user need.

Veto criteria: prior-knowledge on PLL form; bind survives classification audit by accident with unpriced retroactive reclass exposure. Parametric covers settle by-design on trigger — discipline is up-front, no veto needed.

---

<!-- _class: section -->

# 3. Foundational Workflows

*Reserve · Coverage · Commercial UW · Cyber UW*

---

## ClaimsReserveWorkflow

**Anchor PR; veto + triple-flag.** Direct SOX / NAIC audit surface.

**Request fields:** loss_event, injury_or_damage, coverage_summary, comparable_cases, venue, defense_posture, medical_or_repair_estimate, regulatory_exposure, current_reserve_proposal.

**Flag classes:**
- `RESERVE FLAGS` — indemnity / defence / IBNR methodology gaps
- `PRECEDENT FLAGS` — venue-inappropriate / stale / selection-biased comparables
- `LITIGATION FLAGS` — venue posture, class-action signal, regulator-defence reserve

**Veto criteria:** catastrophic-injury with sub-$500k reserve; class-action signal without aggregate provision; state AG inquiry without regulatory-defence reserve; below-median reserve in plaintiff-friendly venue without defence-cost.

**Skill templates (5):** `reserve_comparable_search`, `reserve_ibnr_calculation`, `reserve_venue_adjustment`, `reserve_defense_cost_estimate`, `reserve_regulatory_screen`.

---

## CoverageDecisionWorkflow

**Veto + dual-flag.** Coverage / bad-faith analysis with case-law verification.

**Request fields:** claim_summary, policy_wording (verbatim), factual_disputes, state_law, bad_faith_exposure, proposed_decision.

**Flag classes:**
- `WORDING FLAGS` — clause-vs-loss mechanism map, ambiguity, contra proferentem, reasonable expectations
- `CASE-LAW FLAGS` — wrong-jurisdiction / overruled / distinguishable precedent

**Veto criteria:** proposed denial when reasonable interpretation supports coverage; bad-faith pattern (delay / lowball / reliance) on denial; class-rep pattern-of-conduct; cited authority overruled / abrogated; ignored reasonable-expectations doctrine.

**Skill templates (4):** `coverage_wording_map`, `coverage_case_law_check`, `coverage_bad_faith_screen`, `coverage_decision_letter_draft`.

---

## CommercialUnderwritingWorkflow

**Triple-flag, no veto.** Bind discipline for complex commercial accounts.

**Request fields:** insured_summary, prior_loss_history, hazard_grade, requested_coverage, proposed_terms, regulatory_context, capacity_constraint.

**Flag classes:**
- `LOSS-COST FLAGS` — ISO loss-cost × LCM defensibility; filed deviation availability
- `EXCLUSION FLAGS` — class-specific (mold/silica/asbestos/abuse/pollution/cyber) missing or contradicted
- `CAPACITY FLAGS` — LOB aggregate, treaty cession, cat-zone concentration, common-vendor systemic risk

No veto — bind is reversible at renewal; capacity discipline is the gate.

**Skill templates (4):** `underwriting_loss_cost_check`, `underwriting_exclusion_audit`, `underwriting_capacity_check`, `underwriting_authority_routing`.

---

## CyberUnderwritingWorkflow

**Triple-flag, no veto.** Standalone cyber; attestation-vs-evidence + sub-limit calibration + portfolio aggregation.

**Request fields:** applicant_summary, control_attestations, control_evidence, requested_coverage, proposed_terms, aggregation_context.

**Flag classes:**
- `CONTROL-GAP FLAGS` — attestation contradicted by scan evidence; missing industry-baseline control
- `SUB-LIMIT FLAGS` — ransomware vs backup-immutability gap; regulatory-defence sizing; war/cyber-terrorism (LMA5564) wording currency
- `AGGREGATION FLAGS` — industry / cloud-provider / common-vendor (SolarWinds-class / CrowdStrike) concentration

No veto — emerging-risk line; capacity + control discipline is the gate.

**Skill templates (4):** `cyber_control_maturity_audit`, `cyber_sub_limit_calibration`, `cyber_aggregation_check`, `cyber_ir_vendor_panel`.

---

<!-- _class: section -->

# 4. Specialty Workflows

*Environmental · Parametric Crop · Gig Platform*

---

## EnvironmentalImpairmentWorkflow

**Veto + triple-flag.** PLL / CPL / EIL; long-tail + EPA/CERCLA/state-DEP overlap.

**Request fields:** site_summary, site_history (Phase I/II ESA + regulator filings), pollution_condition, policy_form (PLL form + known-condition clause), governing_state (trigger doctrine), regulator_status, co_insurer_history, proposed_decision_or_reserve.

**Flag classes:**
- `KNOWN-CONDITION FLAGS` — Phase I REC → policy known-condition clause map; CERCLA / Superfund disclosure
- `TAIL FLAGS` — trigger doctrine (exposure / manifestation / continuous / injury-in-fact); policy-period attribution
- `REGULATORY-OVERLAP FLAGS` — EPA, RCRA, CWA, OPA-90, TSCA, state Superfund, Brownfields, NRD

**Veto criteria:** prior-knowledge on PLL despite Phase I REC; NPL site treated as unknown background; denial when sudden-and-accidental carve-out supports coverage; co-insurer notification missed.

**Skill templates (4):** `environmental_phase_one_audit`, `environmental_trigger_doctrine`, `environmental_regulatory_overlap`, `environmental_long_tail_reserve`.

---

## ParametricCropWorkflow

**Triple-flag, no veto.** Specialty agricultural; MPCI / crop-hail / parametric weather (rainfall index / degree-day / NDVI).

**Request fields:** producer_summary, crop_and_yield_history (APH), loss_history (cause-by-cause), proposed_cover_type, data_source (station / grid / satellite product ID), climate_baseline (20-yr back-test + trend), reinsurance_context (SRA group or commercial retro).

**Flag classes:**
- `PERIL-MATCH FLAGS` — trigger variable vs dominant loss pathway (rainfall-only misses heat-stress)
- `BASIS FLAGS` — spatial (station-to-farm distance), resolution (grid size), statistical (R² historical), data-source reliability
- `ATTACHMENT FLAGS` — climate-baseline back-test, trend-creep treatment, out-of-sample validation

No veto — parametric covers settle by-design on trigger fire; discipline is up-front design + producer disclosure, not after-the-fact halt.

**Skill templates (4):** `crop_peril_match_check`, `crop_basis_risk_quantification`, `crop_climate_baseline_backtest`, `crop_producer_disclosure_draft`.

---

## GigPlatformLiabilityWorkflow

**Veto + triple-flag.** Specialty platform liability; state-by-state regulatory patchwork.

**Request fields:** platform_summary, workforce_classification, coverage_stack (commercial GL/TNC, EPLI, occ-acc, contingent-WC), personal_policy_context (commercial-use exclusion, platform-on/off telemetry), state_regulatory_posture (AB5 / Prop 22 / state TNC / NLRB), pending_litigation (class action / AG / DOL / NLRB), proposed_bind_or_decision.

**Flag classes:**
- `CLASSIFICATION FLAGS` — state-specific test result (ABC / IRS 20-factor / state-TNC carve-out)
- `COVERAGE-GAP FLAGS` — personal-vs-platform seam during platform-on; bridge-endorsement availability
- `REGULATORY-PATCHWORK FLAGS` — multi-state TNC / classification statutes; state AG / DOL audit posture; NLRB joint-employer

**Veto criteria:** bind survives classification audit by accident with unpriced retroactive reclass exposure; personal-policy carve-out unbridged in platform-on window; pending multi-state classification dispute treated as settled; occ-acc substitution invalid in state.

**Skill templates (4):** `gig_classification_test`, `gig_coverage_seam_map`, `gig_state_patchwork_audit`, `gig_telemetry_evidence_check`.

---

<!-- _class: section -->

# 5. Convergence Patterns

*Triple-flag · Reviewer-veto · Audit-trail-first*

---

## Triple-flag gate (5 of 7 workflows)

Five workflows use a uniform dict-iteration pattern:

```python
_FLAG_HEADERS: tuple[str, ...] = (
    "LOSS-COST FLAGS:",
    "EXCLUSION FLAGS:",
    "CAPACITY FLAGS:",
)

current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}

for round_num in range(1, max_rounds + 1):
    ...
    for header in _FLAG_HEADERS:
        current[header] = extract_flags(critique, header)        # REASSIGN per round
        accumulated[header].extend(current[header])              # audit-trail accrues

    if review.approved and not any(current.values()):            # convergence gate
        converged = True
        break
```

- `current` is **reassigned** per round → no cross-round leakage.
- `accumulated` is **appended** → audit-trail keeps every flag ever raised.
- `any(current.values())` returns False iff every per-header list is empty → conjunction-gate.

---

## Reviewer-veto pattern (4 of 7 workflows)

Veto-using workflows extend the gate with an independent halt channel:

```python
# Audit-trail writes happen BEFORE the veto check.
self.wiki.add_feedback(
    sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
    round_num=round_num,
    score=score,
)

veto_reason = self._extract_veto(review.critique, max_wiki_chars)
if veto_reason is not None:
    break        # halt before convergence check

if review.approved and not any(current.values()):
    converged = True
    break
```

**Audit-trail before veto break** — a vetoed round still writes the reviewer critique to the wiki + claims to the ledger. The human authority sees what was vetoed and why.

**Veto banner inserted into output** — output is `draft + VETO_BANNER + DISCLAIMER`. The draft is **not replaced** so the human can review what the executor proposed.

---

## Veto-criteria specificity

Each veto-using workflow's `REVIEWER VETO:` criteria are domain-specific and life-or-license-cost:

| Workflow | Veto trigger examples |
|---|---|
| `ClaimsReserveWorkflow` | Catastrophic-injury under-reserve · class-action without aggregate · state AG inquiry · plaintiff-friendly venue with no defence-cost reserve |
| `CoverageDecisionWorkflow` | Reasonable-coverage interpretation against proposed denial · bad-faith delay/lowball/reliance pattern · class-rep exposure · cited authority overruled |
| `EnvironmentalImpairmentWorkflow` | Phase I REC matches loss + policy excludes known conditions · NPL site treated as unknown · denial when sudden-and-accidental supports coverage · co-insurer notification missed |
| `GigPlatformLiabilityWorkflow` | Operating model fails classification test with unpriced retroactive reclass · personal-policy commercial-use carve-out unbridged · multi-state classification dispute treated as settled · occ-acc / WC substitution invalid |

---

<!-- _class: section -->

# 6. Security Model

*Audit findings + shared-helper remediation*

---

## Post-sweep audit (2026-05-14)

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | 0 |
| MEDIUM | **1** (M-PC-1) |
| LOW | 5 (L-PC-1..5) |
| INFO / CLEAN | 15 validations confirmed |
| **VERDICT** | requires-fix-before-merge → ALL CLOSED 2026-05-14 |

Report: `docs/security-audits/2026-05-14-pc-sweep.md`.

---

## M-PC-1 — Veto-parser substring containment

**Vector.** All 4 PC veto-using workflows + retail recall_scope had byte-identical `_extract_veto` static methods using `critique.split("REVIEWER VETO:", 1)[1]`. A reviewer quoting the criteria block in prose (`"Per the REVIEWER VETO: criteria above..."`) mis-anchors the split at the first substring occurrence.

**Impact.** False-positive veto (halt on non-veto critique) **and** false-negative veto (real life-safety / SOX directive silently dropped). Same shape as the previously-closed M1 finding for `extract_flags`, applied to the strongest convergence gate.

**Remediation.** Hoisted to `core/_internal.extract_veto_directive` with line-anchored regex:

```python
match = re.search(rf"(?m)^[ \t]*{re.escape(marker)}[ \t]*(.*)$", critique)
```

5 byte-identical clones collapsed to thin staticmethod wrappers. Convention-level error compounding closed: any future veto-using workflow inherits the hardening automatically.

22 regression tests in `tests/unit/test_extract_veto_directive.py`.

---

## L-PC-2 / L-PC-3 / L-PC-4 / L-PC-5 — Defence-in-depth

| Finding | Fix |
|---|---|
| **L-PC-2** veto continuation stop-list false-negatives | FORMAT NOTE added to VETO CRITERIA block in 4 PC workflows |
| **L-PC-3** per-field truncation budget implicit | `_MAX_FIELD_CHARS = 1500` in each of 7 PC workflows; `to_prompt_text` slices every field before concatenation |
| **L-PC-4** skill template `{xyz}` smuggling | `_BRACE_CHARS_RE` strip in `Skill.render` (cross-domain — affects all skill templates) |
| **L-PC-5** worst-case flag re-injection volume | Shared `truncate_flag_display(flags)` helper in `core/_internal.py`; caps at 16 entries; applied in 7 PC `_format_flag_section` |

Convention-level helpers hoisted to `core/_internal.py` close the gap that next-workflow drift would re-open. Metadata audit-trail (`accumulated[header]`, `metadata['*_flags']`) keeps full lists; only re-injection is bounded.

---

## What an audit-defensible deployment looks like

The library is teaching-grade by stated posture. Hardening for production requires (from `PRODUCTION_GAPS` in each module docstring):

1. **Authoritative integration feeds** — ClaimCenter, PolicyCenter, ISO/Verisk, NAIC Schedule P, USDA-RMA, EPA ECHO, Westlaw, BitSight, state DOL feeds. Replace free-text inputs.
2. **Loss-development triangles** — actuarial baseline; LLM advises the residual, not the base estimate.
3. **Tamper-evident audit store** — session-local JSON is a teaching simulation; regulator-defensible storage required.
4. **Third-model auditor cascade (ARIS §3.1)** — current reviewer folds quality + domain audit; production needs a separately-configured auditor per high-stakes flag class.
5. **Human approval gate enforced in code** — reserves / denials / binds / regulator notices must not auto-publish.

---

<!-- _class: section -->

# 7. Shared Infrastructure

*Helpers in core/_internal.py*

---

## Shared helpers (cross-workflow contract)

| Helper | Purpose | Used by |
|---|---|---|
| `parse_first_json` | Safe JSON extraction (replaces greedy DOTALL regex) | Reviewer output parsing |
| `sanitize_for_prompt` | Strip control chars + NFC + cap length | Every text injection boundary |
| `extract_flags` | Parse `*FLAGS:` section from critique (M1: line-anchored) | All flag-gated workflows |
| `extract_veto_directive` | Parse `REVIEWER VETO:` directive (M-PC-1: line-anchored) | All 5 veto-using workflows (4 PC + retail) |
| `truncate_flag_display` | Cap re-injection at 16 entries with marker | All 7 PC `_format_flag_section` |
| `coerce_score` | Clamp [0,10], reject NaN/inf | Reviewer score handling |
| `safe_resolve_path` | Path validation under a base | Skill template loading |
| `atomic_write_text` | Tempfile + fsync + replace | Ledger + Wiki persistence |
| `redact_secret` | Fixed-shape API-key redaction | Logging |
| `is_safe_id` | Charset-validate IDs loaded from disk | Claim / WikiEntry deserialization |

Each helper centralises an invariant; convention-level error compounding (D-RETAIL-7 / L-PC-1 lesson) is bounded by hoisting helpers when ≥3 workflows would otherwise re-implement.

---

## BaseWorkflow contract

All 7 PC workflows + 8 retail workflows + parole + research extend `BaseWorkflow`:

```python
class BaseWorkflow(ABC):
    def __init__(self, config, executor=None, reviewer=None,
                 ledger=None, wiki=None) -> None: ...

    @abstractmethod
    async def run(self, **kwargs: Any) -> WorkflowResult: ...

    def _register_claims(self, output: str, round_num: int) -> None:
        # L4: line-anchored `## Claims` split
        # L1: cap at _MAX_CLAIMS_PER_ROUND = 200
        ...
```

**No domain base class** (D-RETAIL-2 → D-RETAIL-7 → D-PC-3). 8 retail + 7 PC + 1 parole = 16 workflows surveyed: per-flag-header banner / metadata key / checklist text diverge enough that base-class extraction costs more than it saves.

---

<!-- _class: section -->

# 8. Status

*7 of 7 workflows shipped · all findings closed · 409 tests*

---

## Build status

| Component | Status |
|---|---|
| 4 Foundational workflows + tests + examples + skill templates | ✅ |
| 3 Specialty workflows + tests + examples + skill templates | ✅ |
| 29 P&C skill templates (5 reserve + 4 coverage + 4 underwriting + 4 cyber + 4 environmental + 4 crop + 4 gig) | ✅ |
| Triple-flag pattern (5 of 7) | ✅ |
| Reviewer-veto pattern (4 of 7) | ✅ |
| Shared `extract_veto_directive` + `truncate_flag_display` helpers | ✅ |
| D-PC-1..6 decision rows | ✅ |
| Post-sweep audit (M-PC-1 + L-PC-1..5 all closed) | ✅ |
| Design doc (`docs/superpowers/specs/2026-05-14-pc-domain-design.md`) | ✅ |
| **409 unit + integration tests** | ✅ all passing |
| ruff + mypy clean | ✅ |

---

## Production gaps (PRODUCTION_GAPS — per module)

| Integration | Status |
|---|---|
| ClaimCenter / PolicyCenter / Origami / mainframe | ❌ |
| Loss-development triangles (chain-ladder / BF) | ❌ |
| ISO/Verisk loss-cost + filed-rate library | ❌ |
| NAIC Schedule P + state DOI filings | ❌ |
| USDA-RMA Crop Insurance Handbook + SRA | ❌ |
| NOAA / gridded weather / satellite products | ❌ |
| EPA ECHO / RCRAInfo / state DEP / Phase I-II ESA parser | ❌ |
| Westlaw / Lexis Shepard's citation resolution | ❌ |
| State classification rule engine (AB5 / Prop 22 / TNC) | ❌ |
| Platform-app telemetry feed | ❌ |
| Portfolio aggregation engine | ❌ |
| Reinsurer notification routing | ❌ |
| Tamper-evident audit store | ❌ |
| Third-model auditor cascade (ARIS §3.1) | ❌ |
| Human approval gate enforced in code | ❌ |

The PRODUCTION_GAPS list per workflow makes each integration explicit so a downstream consumer can scope it.

---

## Deferred specialty (per D-PC-6)

| Scenario | Reason |
|---|---|
| Group captive allocation | Build only on concrete user need; member-rating fairness + NAIC RRG Act overlay |
| Equine mortality | Lowest priority; dual-flag + veto on concealment; specialised vet expertise required |

The original audit-scoped expansion (Foundational + Environmental + Crop + Gig) covers the three highest-adversarial-value specialty markets. Group captive and equine can be added with the same recipe in a future batch.

---

## Next actions (in priority order)

| # | Action | Owner |
|---|---|---|
| 1 | Retail-parity batch (L-PC-2/3/5 in 6 retail workflows) | Engineering — ~1 hr |
| 2 | ClaimCenter / PolicyCenter integration adapters | Engineering |
| 3 | Loss-development triangle + actuarial baseline | Actuarial + Data Science |
| 4 | Authoritative regulator + case-law feeds | Coverage / Environmental / Platform-Liability Counsel + Engineering |
| 5 | State classification rule engine | Platform-Liability Counsel + Engineering |
| 6 | Dedicated third-model auditor per high-stakes flag class | Engineering — ARIS §3.1 |
| 7 | Tamper-evident audit store | Engineering + Compliance |
| 8 | Human approval gate in code | Engineering |
| 9 | 90-day shadow pilot per workflow | Claims + Coverage + Underwriting |

---

<!-- _class: section -->

# 9. Who It Is For

*Decision-makers · Engineering · Researchers*

---

## Three audiences

**Carrier P&C teams** evaluating LLM augmentation across the specialty decision surface — claims, coverage, underwriting, cyber, environmental, agricultural, gig-platform. The convergence gates + veto channel + ledger provide a structured audit trail; per-workflow `PRODUCTION_GAPS` checklists name exactly what integration work is required before a pilot.

**Engineering teams** adding a new domain or scenario. P&C is the third reference implementation (after parole + retail) and the first organised into Foundational + Specialty tracks. Recipe locked: per-workflow `*Request` dataclass with `_MAX_FIELD_CHARS` cap, 2-3 domain-flag gates, optional veto via shared `extract_veto_directive`, helper-based flag extraction + claim registration + display truncation, `_DISCLAIMER` banner, approver checklist, skill templates with scenario-noun prefix.

**Researchers** studying cross-model adversarial pairs in irreversible / regulator-audited / asymmetric-info decisions where ground truth is observable: reserve adequacy at claim closure, coverage decisions at settlement / verdict, bind outcomes at renewal / claim emergence, environmental reserves at Schedule-P review, parametric trigger performance at season-end, gig classification at audit outcome.

---

<!-- _class: lead -->

# Thank you

*Reference implementation:* `github.com/gmanch94/adv-multi-agent`

&nbsp;

*Foundational:* claims_reserve · coverage_decision · commercial_underwriting · cyber_underwriting
*Specialty:* environmental_impairment · parametric_crop · gig_platform_liability

&nbsp;

*Adversarial multi-agent collaboration · Cross-family reviewer · Convergence gates · Veto channel*
*Teaching / research — not for production deployment*
