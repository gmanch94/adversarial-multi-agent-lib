# Adversarial Multi-Agent Products

A reusable Python template implementing the adversarial multi-agent collaboration pattern from the [ARIS paper](docs/for_research.pdf) (Yang, Li, Li — SJTU, April 2026).

## Core idea

Pair an **executor** (Claude Opus 4.7, adaptive thinking) with a **reviewer from a different model family** (GPT-4o by default). Cross-model pairing prevents the echo-chamber effect: the reviewer cannot reuse the executor's reasoning shortcuts. The loop runs until the reviewer's score exceeds a threshold or max rounds is reached.

```
Task → Executor generates → Reviewer scores + critiques
          ↑                        ↓
          └──── revise ────────────┘  (repeat until converged)
```

## Project structure

```
src/
  core/
    agents.py       ExecutorAgent (Claude), ReviewerAgent (cross-model)
    ledger.py       ClaimLedger — tracks every factual claim + evidence
    wiki.py         ResearchWiki — persistent knowledge store
    config.py       Config, EffortLevel enum
  workflows/
    review_loop.py  Auto Review Loop — main adversarial iteration
    idea_discovery.py  Lit survey → novelty check → research proposal
    rebuttal.py     Point-by-point rebuttal for peer-review comments
  assurance/
    verifier.py     3-stage claim verification (integrity → mapping → audit)
    editor.py       5-pass scientific editing pipeline
  skills/
    registry.py     Markdown-based skill loader
skills/
  review.md         Review skill template
  generate.md       Generation skill template
  rebuttal.md       Rebuttal skill template
examples/
  basic_review_loop.py
```

## Quickstart

```bash
# 1. Install
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and OPENAI_API_KEY

# 3. Run the example
python examples/basic_review_loop.py
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | required | Executor (Claude Opus 4.7) |
| `OPENAI_API_KEY` | required | Reviewer (GPT-4o) |
| `EFFORT_LEVEL` | `high` | `low\|medium\|high\|xhigh` |
| `MAX_REVIEW_ROUNDS` | `5` | Hard cap on iterations |
| `SCORE_THRESHOLD` | `8.0` | Score (0–10) to stop early |
| `REVIEWER_PROVIDER` | `openai` | `openai` or `anthropic` |

## Usage

### Auto Review Loop

```python
from adv_multi_agent.core.config import Config
from adv_multi_agent.workflows.review_loop import AutoReviewLoop

config = Config.from_env()
result = await AutoReviewLoop(config).run(
    task="Write a literature review on X",
    criteria="correctness, novelty, clarity, rigor",
)
print(result.output)
print(f"Converged in {result.rounds} rounds, score={result.final_score:.1f}")
```

### Idea Discovery

```python
from adv_multi_agent.workflows.idea_discovery import IdeaDiscovery

result = await IdeaDiscovery(config).run(topic="continual learning in LLMs")
# result.output  → one-page research proposal
# result.metadata["survey"]   → full literature survey
# result.metadata["novelty"]  → novelty assessment
```

### Rebuttal

```python
from adv_multi_agent.workflows.rebuttal import RebuttalWorkflow

result = await RebuttalWorkflow(config).run(
    comments="1. The baseline is weak...\n2. Missing ablation...",
    context="Abstract: We propose...",
)
print(result.output)
```

### Claim verification

```python
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.assurance.verifier import ClaimVerifier

ledger = ClaimLedger("ledger.json")
verifier = ClaimVerifier(config, ledger)
report = await verifier.verify(document_context=full_paper_text)
print(f"Pass rate: {report.pass_rate:.0%}  disputed: {report.disputed}")
```

### 5-pass editing

```python
from adv_multi_agent.assurance.editor import ScientificEditor

report = await ScientificEditor(config).edit(draft_text)
print(report.final)
print("Flags:", report.flags)
```

### Skill registry

```python
from adv_multi_agent.skills.registry import SkillRegistry

registry = SkillRegistry("skills/")
prompt = registry.get("review").render(text=my_text, criteria="clarity, rigor")
output = await executor.run(prompt)
```

## Architecture notes

- **Executor**: `claude-opus-4-7` with `thinking: {type: "adaptive"}` and configurable `effort`. Uses `.messages.stream()` context manager throughout.
- **Reviewer**: GPT-4o by default. Set `REVIEWER_PROVIDER=anthropic` to use a second Claude model (less adversarial but no OpenAI dependency).
- **Claim ledger**: append-only JSON, persisted after each mutation. The 3-stage verifier resolves PENDING → SUPPORTED/DISPUTED/RETRACTED.
- **Wiki**: shared knowledge store across workflow runs. Self-improvement proposals are recorded here and require explicit reviewer approval before adoption.
- **Skills**: `.md` files with YAML frontmatter. Drop new `.md` files into `skills/` — they are auto-discovered at startup.

## Extending

**Add a skill**: create `skills/my_skill.md` with frontmatter `name`, `description`, `inputs`.

**Add a workflow**: subclass `BaseWorkflow`, implement `async def run(self, **kwargs) -> WorkflowResult`.

**Swap the reviewer**: set `REVIEWER_PROVIDER=anthropic` or pass a custom `ReviewerAgent` subclass.
