---
name: prior_auth_revision
description: Revision prompt for prior authorization review; removes unsupported necessity claims
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
---
Revise the prior authorization review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

Revise using the same section structure:
## Medical-necessity assessment
## Coverage-policy fit
## Documentation review
## Step-therapy verification
## Recommendation
## Claims

For any flagged item: REMOVE the unsupported claim or replace it with
documentation evidence from the submitted member data and cited guidelines.
Do not rephrase — ground or remove.
