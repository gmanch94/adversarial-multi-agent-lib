---
name: biosimilar_revision
description: Revision pass for a biosimilar comparability assessment; addresses reviewer ANALYTICAL-SIMILARITY / RESIDUAL-UNCERTAINTY / BRIDGING flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this biosimilar comparability assessment. Address EVERY issue in the
reviewer's critique, especially any ANALYTICAL-SIMILARITY FLAGS, RESIDUAL-
UNCERTAINTY FLAGS, or BRIDGING FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any ANALYTICAL-SIMILARITY flag: do not claim similarity a CQA does not demonstrate.
⚠️  For any RESIDUAL-UNCERTAINTY flag: state the uncertainty and how the evidence resolves it.
⚠️  For any BRIDGING flag: justify or withdraw the bridge/extrapolation.
