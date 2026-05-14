# Specialized B2B P&C Insurance — Design Doc

Last updated: 2026-05-14
Status: **DRAFT — design only, no code.** Anchor: Claims Reserve Estimation. Sweep order TBD post-anchor.

Scope is **specialized commercial Property & Casualty**. Personal lines (auto/home), health, and life are explicitly **out of scope** — adversarial-multi-agent value is highest where decisions are irreversible, regulator-audited, and asymmetric-information-heavy. Commercial P&C concentrates all three.

---

## Why P&C fits the ARIS pattern

| Property | P&C manifestation |
|---|---|
| Irreversibility | Bound policy, set claim reserve, paid claim — each crystallises a $-figure that can only be revised at cost. |
| Regulator audit-trail | NAIC, state DOI (rate-adequacy filings), SOX (reserve adequacy + restatement risk), Schedule P. |
| Echo-chamber risk | Underwriters/claims adjusters develop precedent-bias; same-family LLMs replicate the bias. Cross-family reviewer is the safeguard (D2 rationale). |
| Asymmetric info | Insured knows their exposure better than underwriter; claimant knows the loss-scope better than adjuster. Reviewer represents the "the other side reads this differently" check. |
| Veto class | Under-reserving = SOX restatement; bad-faith claim denial = punitive-damages exposure. Both warrant a reviewer halt independent of score. |

---

## Convention recap (inherited from retail)

Every P&C workflow MUST mirror the retail convention (D-RETAIL-2 → D-RETAIL-7) — there is **no shared P&C base class**:

1. Define a `*Request` dataclass with `to_prompt_text()`.
2. Sanitize all request text via `sanitize_for_prompt` at the workflow boundary.
3. Loop up to `config.max_review_rounds`; convergence = `review.approved AND not current_flags AND not veto` (veto only for scenarios that use it).
4. Register `## Claims` lines via `BaseWorkflow._register_claims` (inherits L1 cap).
5. Add reviewer critique to `self.wiki.add_feedback`.
6. Extract per-class flag lists via `extract_flags(critique, header)` (inherits L2 cap + M1 anchoring).
7. Build a `_build_*_checklist` listing human-action items (auditor sign-off, filing references, comparable-case citations).
8. Return `WorkflowResult` with output suffixed by `_DISCLAIMER`, metadata including flag list, checklist, `ledger_summary`, and (if veto) `veto_reason`.
9. PRODUCTION_GAPS docstring naming the live integrations a deployment would require (Guidewire ClaimCenter / PolicyCenter, Origami, AS400 mainframe extracts, NAIC Schedule P feed, ISO/Verisk loss-cost tables, state DOI filing portals).
10. Cite ARIS in the module docstring.

Skill templates: flat under `src/adv_multi_agent/pc/skills/templates/`, prefixed with the scenario noun (`reserve_*`, `coverage_*`, `underwriting_*`, `cyber_*`).

Example files: one per scenario at `examples/pc/<scenario>.py`, synthetic data only.

---

## Per-scenario specs

### 1. Claims Reserve Estimation — `ClaimsReserveWorkflow` (anchor PR)

**Gate type:** `RESERVE FLAGS` + `PRECEDENT FLAGS` + `LITIGATION FLAGS` + **reviewer-veto**. Highest-stakes shape — direct SOX / NAIC audit surface.

**Request fields:**
- `loss_event: str` — date, location, mechanism, named insured.
- `injury_or_damage: str` — bodily-injury severity tier OR property loss type + initial damage estimate.
- `coverage_summary: str` — policy form, limits (per-occurrence + aggregate), deductible/SIR, sub-limits.
- `comparable_cases: str` — analyst-cited prior settlements / verdicts with venue + year + settlement amount.
- `venue: str` — state + county + court (jury-friendliness materially affects reserve).
- `defense_posture: str` — fault/no-fault assessment, contributory negligence, comparative-fault percentage.
- `medical_or_repair_estimate: str` — treating-provider summary OR adjuster property estimate.
- `regulatory_exposure: str` — any class-action signals, multi-claimant signals, regulator interest (e.g. state AG inquiry).
- `current_reserve_proposal: str` — analyst's first-pass reserve $ + IBNR uplift basis.

**Reviewer flags to detect:**
- `RESERVE FLAGS:` — reserve is below comparable-case median without justification; IBNR uplift methodology not stated; defence-cost reserve omitted; sub-limit overlooked.
- `PRECEDENT FLAGS:` — cited comparables are venue-inappropriate (wrong state, federal vs state), too old (>7 yrs in volatile lines), or selection-biased (only favourable cases).
- `LITIGATION FLAGS:` — venue is plaintiff-friendly but the reserve assumes neutral venue; class-certification signal not reflected; bad-faith-claim risk on a low-ball reserve not captured.
- `REVIEWER VETO:` — any condition warranting halt for human actuary / claims-committee sign-off (e.g. catastrophic-injury signal but reserve <$500k; class-action signal but per-occurrence reserve; state-AG involvement not flagged in current_reserve_proposal).

**Convergence:** `approved AND not reserve_flags AND not precedent_flags AND not litigation_flags AND not veto`.

**Veto control flow:** identical to `RecallScopeWorkflow` (D-RETAIL-1) — pre-veto audit trail writes, banner-not-replace output, `metadata["veto_reason"]` verbatim.

**Skill templates:** `reserve_comparable_search.md`, `reserve_ibnr_calculation.md`, `reserve_venue_adjustment.md`, `reserve_defense_cost_estimate.md`, `reserve_regulatory_screen.md`

**Checklist items** (always):
- Senior actuary sign-off if reserve > $1M or veto raised
- Claims committee review per company reserve-authority matrix
- Document comparable-case selection rationale (Schedule P-defensible)
- Re-evaluate reserve every 90 days or on material development
- Notify reinsurer per treaty notification thresholds

**Why this is the anchor:** veto + triple-flag is the most expressive shape in the codebase; maps cleanly to `recall_scope.py`; SOX-restatement consequence makes the reviewer-veto rationale unambiguous to a researcher reading the example.

---

### 2. Coverage / Bad-Faith Decision — `CoverageDecisionWorkflow` (PR #2)

**Gate type:** `WORDING FLAGS` + `CASE-LAW FLAGS` + **reviewer-veto**.

**Request fields:**
- `claim_summary: str` — what the insured is claiming, when, against which coverage part.
- `policy_wording: str` — verbatim relevant clauses (insuring agreement, exclusions, conditions, endorsements).
- `factual_disputes: str` — what facts are contested between insurer and insured.
- `state_law: str` — governing law (state choice-of-law if multi-state).
- `bad_faith_exposure: str` — prior insurer communications, delay history, surplus-lines flag.
- `proposed_decision: str` — coverage / partial / denial + rationale.

**Reviewer flags:**
- `WORDING FLAGS:` — exclusion citation doesn't match the loss mechanism; ambiguity under `contra proferentem`; reasonable-expectations doctrine not addressed.
- `CASE-LAW FLAGS:` — cited precedent is wrong jurisdiction, overruled, or distinguishable on facts; recent state supreme court case not addressed.
- `REVIEWER VETO:` — bad-faith exposure (delay, lowball, claim-handling pattern) on a proposed denial; class-action class-rep signal; ambiguity that should be resolved in favour of insured per state doctrine.

**Why deferred to PR #2:** synthetic data harder to make convincing (real coverage decisions cite verbatim policy wording + case-law strings); deferring lets the anchor (Claims Reserve) settle the veto-pattern convention first.

---

### 3. Complex Commercial Underwriting — `CommercialUnderwritingWorkflow` (PR #3)

**Gate type:** `LOSS-COST FLAGS` + `EXCLUSION FLAGS` + `CAPACITY FLAGS`. **No veto** — bind decisions are reversible at policy renewal in most cases.

**Request fields:**
- `insured_summary: str` — NAICS code, exposure base (payroll/receipts/sq.ft.), operations summary.
- `prior_loss_history: str` — 5-year loss runs with frequency + severity.
- `hazard_grade: str` — class-code-derived hazard tier + special hazards (hot work, fleet age, hazardous materials).
- `requested_coverage: str` — lines, limits, deductibles, scheduled endorsements.
- `proposed_terms: str` — premium, retention, exclusions added, sub-limits.
- `regulatory_context: str` — state filings required, admitted vs surplus-lines, rate-adequacy filing status.
- `capacity_constraint: str` — line-of-business aggregate cap, treaty cession, catastrophe-zone exposure.

**Reviewer flags:**
- `LOSS-COST FLAGS:` — proposed premium below ISO loss-cost × LCM without filed deviation; expense-ratio assumption out of range.
- `EXCLUSION FLAGS:` — standard exclusions missing for the hazard class (e.g. mold/silica for construction); endorsement schedule contradicts main form.
- `CAPACITY FLAGS:` — bind would exceed aggregate cap; cat-zone concentration not addressed; reinsurance cession not pre-cleared.

---

### 4. Cyber Risk Underwriting — `CyberUnderwritingWorkflow` (PR #4)

**Gate type:** `CONTROL-GAP FLAGS` + `SUB-LIMIT FLAGS` + `AGGREGATION FLAGS`. **No veto** — emerging-risk line, capacity discipline is the gate, not life-safety.

**Request fields:**
- `applicant_summary: str` — industry, revenue, employee count, data-volume estimate (records held).
- `control_attestations: str` — MFA, EDR, backup-immutability, vendor-management posture as attested in application.
- `control_evidence: str` — any third-party scan results, attestation discrepancies, prior incident history.
- `requested_coverage: str` — first-party (BI, data restoration, ransomware) + third-party (privacy, regulatory, media); limits + sub-limits.
- `proposed_terms: str` — premium, retention, sub-limits, war/cyber-terrorism exclusions.
- `aggregation_context: str` — portfolio concentration by industry / cloud-provider / software vendor (SolarWinds-class systemic risk).

**Reviewer flags:**
- `CONTROL-GAP FLAGS:` — attestation contradicted by scan evidence; missing control given industry/size norms; ransomware sub-limit inappropriate given backup-immutability gap.
- `SUB-LIMIT FLAGS:` — ransomware sub-limit too high vs control maturity; regulatory-defence sub-limit missing for regulated industry; social-engineering sub-limit miscalibrated.
- `AGGREGATION FLAGS:` — cloud-provider concentration breaches portfolio cap; industry-vertical concentration breach; common-vendor systemic exposure not addressed.

---

## Out-of-scope for this sweep (future)

- **Reinsurance treaty placement** — heavy actuarial dependency; deferred.
- **Submission triage** — single-flag, low-novelty; covered by D9 pattern.
- **Renewal repricing** — overlaps with #3; revisit after #3 lands.
- **Surety bond** — niche; revisit if user demand appears.

---

## Anchor build sequence (proposed; locked at first-PR sign-off)

1. **PR #1** — `ClaimsReserveWorkflow` + `reserve_*` skill templates (5) + example + tests. Locks the P&C veto+triple-flag convention. Mirrors the recall_scope shape so the diff is mostly content, not structure.
2. PR #2 — `CoverageDecisionWorkflow` (veto + dual-flag).
3. PR #3 — `CommercialUnderwritingWorkflow` (triple-flag, no veto).
4. PR #4 — `CyberUnderwritingWorkflow` (triple-flag, no veto).

Pre-anchor open question (resolve before PR #1): does the `pc/` namespace mirror retail exactly (`workflows/`, `skills/templates/`)? Default: **yes** — same import path shape (`adv_multi_agent.pc.workflows.claims_reserve`).

---

## Decision references (see [decisions.md](decisions.md))

- D1, D2, D7, D8 — model + convergence inheritance.
- D-RETAIL-1 — reviewer-veto pattern (reused).
- D-RETAIL-2 → D-RETAIL-7 — no-base-class convention (reused).
- D-PC-1..5 — to be added with this design doc.
