---
name: rebuttal
description: Generate a point-by-point rebuttal to peer-review comments
inputs: [comments, paper_context]
---

You are writing a formal rebuttal to peer reviewer comments for an academic paper.

### Paper context
{paper_context}

### Reviewer comments
{comments}

### Instructions
For each comment:
1. **Acknowledge** what the reviewer is pointing at (even if you disagree).
2. **Respond** directly:
   - For valid concerns: describe the specific change you will make to the manuscript.
   - For partially valid concerns: clarify the misunderstanding AND note any update.
   - For invalid concerns: correct the reviewer politely but firmly, citing evidence.
3. **Do not** use vague phrases like "we will address this" — be concrete.

Format: numbered list matching the reviewer's numbering.
Tone: professional, respectful, direct.
