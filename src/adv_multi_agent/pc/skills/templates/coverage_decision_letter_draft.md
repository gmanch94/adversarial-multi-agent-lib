---
name: coverage_decision_letter_draft
description: Draft the structure of a coverage decision letter (denial, partial, or reservation-of-rights)
inputs: [decision_type, controlling_clause, factual_basis, governing_state]
---
You are drafting the structural outline of a coverage decision letter for coverage counsel to finalise. Do NOT write the actual letter — produce the section-by-section content.

Decision type (denial / partial / reservation-of-rights / acknowledgement): {decision_type}
Controlling clause: {controlling_clause}
Factual basis (facts the insurer relied on): {factual_basis}
Governing state: {governing_state}

For the chosen decision_type, populate these sections:

1. **Salutation + claim identification** — claim number, date of loss, named insured, policy number.
2. **Facts** — neutral one-paragraph recital of the loss facts as the insurer understands them.
3. **Policy provisions cited** — verbatim quote of each provision the decision rests on (insuring agreement, exclusion, condition, endorsement). Note which form / endorsement.
4. **Analysis** — how each cited provision applies to the facts.
5. **Decision** — explicit statement of decision_type, scope, dollar amount if applicable.
6. **Reservation language** (denials and partials) — explicit reservation of rights, notice that the insurer is not waiving any defence by issuing this letter.
7. **Insured rights** — state-mandated language: appeal rights, DOI complaint contact, statute-of-limitations notice (if any), demand for appraisal / arbitration (if applicable to LOB).
8. **Response window** — date by which the insured may submit additional information.

Output format:
- Section-by-section content: each item above with one-paragraph content
- State-specific language requirements flagged for governing_state
- Recommended attachments: [list of policy pages, endorsements, prior correspondence to include]
- Reviewer note: anything that coverage counsel should specifically verify before signing the letter
