# Parole Assessment Workflow — spec (2026-05-12)

Teaching / research example: adapting the ARIS adversarial pattern to
high-stakes decision-support. Status: shipped, 21 tests passing.

---

## Intent

Three intended uses, in priority order:

1. **Teaching** — show how the ARIS pattern adapts to a domain with legal
   and ethical constraints. The workflow is a concrete, runnable
   illustration of what changes when you move from "generate a paper abstract"
   to "inform a liberty decision."

2. **Research** — foundation for studying demographic-proxy bias in LLM
   decision-support, adversarial bias detection, and convergence behaviour
   under dual-mandate review criteria.

3. **Real tool (future)** — NOT production-ready as shipped. Seven explicit
   gaps (PRODUCTION_GAPS) block any production use.

---

## Key design decisions

### 1. Structured input (`ParoleCase`)

Free-text task strings are replaced by a dataclass with named fields:
`offense_description`, `sentence_imposed`, `time_served`,
`in_custody_conduct`, `programs_completed`, `psychological_assessment`,
`reentry_plan`, and optional `victim_statement` / `external_risk_score`.

**Why:** Forces the caller to enumerate what evidence they actually have.
An empty field is a visible gap; a missing free-text sentence is invisible.
`to_prompt_text()` renders the fields into a structured block for prompt
injection.

### 2. Dual-mandate reviewer criteria

The reviewer's scoring rubric covers five dimensions:

| Dimension | Weight | Role |
|---|---|---|
| Balance | 30 % | Is risk/rehabilitation given honest proportionate weight? |
| Evidence grounding | 25 % | Are claims tied to individual case evidence, not class stereotypes? |
| Bias audit | 25 % | Do any risk signals use demographic proxies? |
| Completeness | 10 % | Are evidence gaps named? |
| Actionability | 10 % | Are proposed conditions specific and enforceable? |

The bias-audit dimension is the pattern adaptation from `AutoReviewLoop`.
A production system should separate it into a third independent model
(see PRODUCTION_GAPS §4).

### 3. Bias-gate convergence

Standard `AutoReviewLoop` convergence: `score >= threshold`.

`ParoleAssessmentWorkflow` adds a second gate: `not current_bias_flags`.

```
if review.approved and not current_bias_flags:
    converged = True
    break
```

A brief that scores 9/10 but contains a flagged demographic proxy does
not converge. The loop continues until both conditions hold or max rounds
is exhausted.

### 4. Bias flag extraction and feedback

The reviewer is instructed to list bias instances under a `BIAS FLAGS:`
heading. `_extract_bias_flags(critique)` parses that section:

- Returns `[]` when the section is absent or contains "None detected".
- Stops accumulating at the next `##` heading or "Overall score:" line.
- Handles `•`, `*`, `-` bullet variants.

Extracted flags are:
- Accumulated across all rounds into `all_bias_flags` (metadata output).
- Fed back to the executor in the revision prompt with explicit instruction:
  **REMOVE the flagged reasoning, do not rephrase it.**

### 5. Claims ledger

Same as `AutoReviewLoop`: parses `## Claims` section from executor output,
registers each `[Source: <case field>] <claim text>` line into
`ClaimLedger`. Enables post-hoc auditability — every factual assertion is
traceable to a specific case field.

### 6. Mandatory disclaimer

Every output appends:

> ⚠️ ADVISORY ONLY — This AI-generated brief is not a parole decision.
> A qualified human parole board member must review all evidence
> independently and make the final determination.

The disclaimer is part of `WorkflowResult.output`, not metadata — it
travels with the brief regardless of how the caller handles the result.

### 7. Board checklist

`_build_board_checklist(case, bias_flags)` generates a human verification
checklist. If any bias flags accumulated, the first checklist item is a
prominent warning. Standard items cover: case file completeness, claim
cross-checks, certificate verification, independent contact verification,
clinician review, victim notification, and an explicit sign-off that the
board is not bound by the AI recommendation.

---

## Output structure

`WorkflowResult`:

| Field | Content |
|---|---|
| `output` | Full advisory brief (markdown) + `---` separator + disclaimer |
| `rounds` | Rounds executed |
| `final_score` | Reviewer score on the last round |
| `converged` | `True` iff score ≥ threshold AND zero bias flags on last round |
| `metadata.case_id` | From `ParoleCase.case_id` |
| `metadata.recommendation` | First non-empty line of `## Advisory Recommendation` section, ≤ 200 chars |
| `metadata.bias_flags` | Deduplicated list of all flagged instances across all rounds |
| `metadata.board_checklist` | Human verification steps (list of strings) |
| `metadata.disclaimer` | The disclaimer string (for downstream display) |
| `metadata.ledger_summary` | `ClaimLedger.summary()` dict |

---

## PRODUCTION_GAPS

Seven gaps block production deployment. Each corresponds to a concrete
failure mode if deployed as-is:

1. **Disparate-impact auditing** — no validation that recommendations are
   demographically neutral across protected classes. Without this, the
   system can reproduce COMPAS-class disparities even with bias flags
   removed from individual briefs.

2. **Calibrated risk scores** — the 0–10 reviewer score is a quality
   signal for the brief, not an actuarial risk score. Presenting it as
   risk probability would be statistically invalid.

3. **Court-admissible explanations** — every claim must be traceable to a
   specific source document with citation. The `## Claims` section
   establishes the structure; full traceability requires evidence attachment
   at the ledger level.

4. **Dedicated third-model bias auditor** — the reviewer's bias audit
   shares context with its quality scoring. A production system needs a
   separate model (different family) whose only function is demographic
   proxy detection.

5. **Demographic blind evaluation** — the executor currently sees all case
   fields including potential proxy indicators. Production requires redacting
   race, gender, ZIP code, school name, and socioeconomic indicators before
   the executor pass; a human re-introduces context after.

6. **Jurisdiction compliance check** — AI output must be validated against
   applicable parole statutes before release to the board. Jurisdiction
   varies significantly; no such check is implemented.

7. **Human approval gate** — the system delivers a brief; it does not
   enforce that a board member read it before the brief enters any record.
   A production system must require explicit acknowledgment.

---

## Example configuration

Cross-family pairing (Gemini executor + GPT-4o reviewer) as recommended
in ARIS §3.2:

```python
config = Config(
    executor_provider=ExecutorProvider.GEMINI,
    reviewer_provider=ReviewerProvider.OPENAI,
    effort=EffortLevel.HIGH,
    max_review_rounds=4,
    score_threshold=7.5,
    workspace_dir="parole_workspace",
)
workflow = ParoleAssessmentWorkflow(config)
result = await workflow.run(case=CASE)
```

`examples/parole_assessment.py` contains a complete synthetic case
(`CASE-2024-0847`) with all fields populated for illustration.
