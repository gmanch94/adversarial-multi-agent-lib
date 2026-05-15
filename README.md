# adv-multi-agent

A reusable Python library implementing the adversarial multi-agent collaboration pattern from the [ARIS paper](https://arxiv.org/pdf/2605.03042) (Yang, Li, Li — SJTU, May 2026).

Pair an **executor** (Claude Opus 4.7 or Gemini 2.5 Pro) with a **reviewer from a different model family** (GPT-4o by default). Cross-model pairing prevents the echo-chamber effect: the reviewer cannot reuse the executor's reasoning shortcuts. The loop runs until the reviewer's score exceeds a threshold **and** every domain-specific FLAGS class is clear (and, for veto-using workflows, no reviewer veto fires) — or the round cap is reached.

**23 workflows across 5 domains** — research (4), parole (1), retail (8), pc (7), industrial (8 MVP of 27-workflow catalog). 7 workflows use the reviewer-veto pattern for irreversible-class decisions (recall, claims reserve, coverage decision, environmental impairment, gig platform liability, product-liability root-cause, recall-scope manufacturing). **481 tests** passing; ruff + mypy clean.

```
Task → Executor generates → Reviewer scores + critiques
          ↑                        ↓
          └──── revise ────────────┘  (repeat until converged)
```

---

## Package structure

```
src/adv_multi_agent/
  core/                         # shared infrastructure
    agents.py                   #   ExecutorAgent (Anthropic + Gemini), ReviewerAgent
    config.py                   #   Config, EffortLevel, ExecutorProvider, ReviewerProvider
    ledger.py                   #   ClaimLedger — tracks every factual claim
    wiki.py                     #   ResearchWiki — persistent knowledge store
    workflow.py                 #   BaseWorkflow (ABC), WorkflowResult
    _internal.py                #   sanitize_for_prompt, parse_first_json, atomic_write
    skills/
      registry.py               #   SkillRegistry — Markdown-based skill loader
      mcp_server.py             #   FastMCP server (list/describe/get/render, 4 tools)
  research/                     # research automation domain (4 workflows)
    workflows/
      review_loop.py            #   AutoReviewLoop — core adversarial iteration
      idea_discovery.py         #   IdeaDiscovery — lit survey → novelty → proposal
      rebuttal.py               #   RebuttalWorkflow — point-by-point peer-review rebuttal
      manuscript_assurance.py   #   ManuscriptAssurance — review + verify + edit chain
    assurance/
      verifier.py               #   ClaimVerifier — 3-stage claim verification
      editor.py                 #   ScientificEditor — 5-pass prose editing
    skills/templates/           #   15 bundled research skill templates
  parole/                       # parole decision-support domain (1 workflow)
    workflows/parole.py         #   ParoleAssessmentWorkflow, ParoleCase (BIAS FLAGS gate)
    skills/templates/           #   6 bundled parole skill templates
  retail/                       # retail decision-support domain (8 workflows)
    workflows/                  #   demand · labor · recall (veto) · loyalty · promo
                                #   supplier · inventory · private_label
    skills/templates/           #   25 bundled retail skill templates
  pc/                           # B2B P&C insurance domain (7 workflows · 2 tracks)
    workflows/                  #   Foundational: claims_reserve (veto) · coverage_decision (veto)
                                #     commercial_underwriting · cyber_underwriting
                                #   Specialty (D-PC-6): environmental_impairment (veto)
                                #     parametric_crop · gig_platform_liability (veto)
    skills/templates/           #   29 bundled pc skill templates
  industrial/                   # industrial manufacturing + IoT (8 MVP of 27 catalog)
    workflows/                  #   Mfg Ops: make_vs_buy · supplier_qualification
                                #     engineering_change_order · quality_incident_root_cause
                                #   Safety/Recall: product_liability_root_cause (veto)
                                #     recall_scope_manufacturing (veto)
                                #   Strategic: supply_chain_resilience
                                #   IoT: telematics_anomaly_triage
    skills/templates/           #   32 bundled industrial skill templates
                                #   (19 Phase-2 workflow designs locked in design doc)

examples/
  research/{basic_review_loop, gemini_executor, manuscript_assurance}.py
  parole/parole_assessment.py
  retail/{demand_forecasting, labor_scheduling, recall_scope, loyalty_offer, ...}.py
  pc/{claims_reserve, coverage_decision, commercial_underwriting, ...}.py
  industrial/{make_vs_buy, supplier_qualification, product_liability_root_cause, ...}.py
```

---

## Installation

```bash
pip install adv-multi-agent                       # Anthropic executor + OpenAI reviewer
pip install 'adv-multi-agent[gemini]'             # add Gemini executor support
pip install 'adv-multi-agent[mcp]'                # add MCP server
pip install 'adv-multi-agent[gemini,mcp,dev]'     # everything
```

```bash
cp .env.example .env      # fill in API keys
python -m examples.research.basic_review_loop
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Required if using Anthropic executor or reviewer |
| `OPENAI_API_KEY` | — | Required if `REVIEWER_PROVIDER=openai` (default) |
| `GEMINI_API_KEY` | — | Required if `EXECUTOR_PROVIDER=gemini` |
| `EXECUTOR_PROVIDER` | `anthropic` | `anthropic` \| `gemini` |
| `REVIEWER_PROVIDER` | `openai` | `openai` \| `anthropic` |
| `EFFORT_LEVEL` | `high` | `low` \| `medium` \| `high` \| `xhigh` |
| `MAX_REVIEW_ROUNDS` | `5` | Hard cap on iterations |
| `SCORE_THRESHOLD` | `8.0` | Score (0–10) to converge early |

---

## Usage

### Auto Review Loop

```python
from adv_multi_agent.core.config import Config
from adv_multi_agent.research.workflows.review_loop import AutoReviewLoop

config = Config.from_env()
result = await AutoReviewLoop(config).run(
    task="Write a literature review on continual learning in LLMs",
    criteria="correctness, novelty, clarity, rigor",
)
print(result.output)
print(f"Converged in {result.rounds} rounds, score={result.final_score:.1f}")
```

### Idea Discovery

```python
from adv_multi_agent.research.workflows.idea_discovery import IdeaDiscovery

result = await IdeaDiscovery(config).run(topic="continual learning in LLMs")
```

### Rebuttal

```python
from adv_multi_agent.research.workflows.rebuttal import RebuttalWorkflow

result = await RebuttalWorkflow(config).run(
    comments="1. The baseline is weak...\n2. Missing ablation...",
    context="Abstract: We propose...",
)
print(result.output)
```

### Claim verification

```python
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.research.assurance.verifier import ClaimVerifier

ledger = ClaimLedger("ledger.json")
verifier = ClaimVerifier(config, ledger)
report = await verifier.verify(document_context=full_paper_text)
print(f"Pass rate: {report.pass_rate:.0%}  disputed: {report.disputed}")
```

### Scientific editing

```python
from adv_multi_agent.research.assurance.editor import ScientificEditor

report = await ScientificEditor(config).edit(draft_text)
print(report.final)
print("Flags:", report.flags)
```

### Gemini executor (cross-family pairing)

```python
from adv_multi_agent.core.config import (
    Config, EffortLevel, ExecutorProvider, ReviewerProvider
)

config = Config(
    executor_provider=ExecutorProvider.GEMINI,
    reviewer_provider=ReviewerProvider.OPENAI,
    effort=EffortLevel.HIGH,
)
```

### Parole assessment (advisory only)

```python
from adv_multi_agent.parole.workflows.parole import ParoleAssessmentWorkflow, ParoleCase

case = ParoleCase(
    case_id="CASE-2024-0847",
    offense_description="...",   # behaviour-only; redact demographics upstream
    # ... other fields
)
result = await ParoleAssessmentWorkflow(config).run(case=case)
print(result.metadata["recommendation"])
for item in result.metadata["board_checklist"]:
    print(item)
```

See `examples/parole/parole_assessment.py` and `docs/slides/parole-executive-brief.md`.
⚠️ **NOT FOR PRODUCTION DEPLOYMENT** — see `parole.py` module docstring for the deployment checklist.

### Retail decision support (advisory only)

```python
from adv_multi_agent.retail.workflows.demand_forecasting import (
    DemandForecastWorkflow, ForecastRequest,
)
from adv_multi_agent.retail.workflows.labor_scheduling import (
    LaborSchedulingWorkflow, SchedulingRequest,
)

# Demand forecast — ASSUMPTION FLAGS convergence gate
forecast = await DemandForecastWorkflow(config).run(
    request=ForecastRequest(store_id="KRO-OH-0042", sku="...", ...)
)

# Labor schedule — COMPLIANCE FLAGS convergence gate
schedule = await LaborSchedulingWorkflow(config).run(
    request=SchedulingRequest(store_id="KRO-OH-0042", week_start="2026-05-18", ...)
)
```

See `examples/retail/*.py` (8 workflows). All 8 use a per-workflow FLAGS convergence gate; `recall_scope` adds the reviewer-veto pattern.
⚠️ **NOT FOR PRODUCTION DEPLOYMENT** — `PRODUCTION_GAPS` documented in each module docstring (live POS/HCM integration, actuarial baseline, human approval gate).

### B2B Property & Casualty (advisory only)

```python
from adv_multi_agent.pc.workflows.claims_reserve import (
    ClaimsReserveWorkflow, ClaimsReserveRequest,
)

# Reserve estimation — RESERVE + PRECEDENT + LITIGATION flags + reviewer veto
# (SOX-restatement risk on under-reserving fires the veto channel)
result = await ClaimsReserveWorkflow(config).run(
    request=ClaimsReserveRequest(loss_event="...", venue="...", ...)
)
```

7 workflows across Foundational (claims_reserve [veto], coverage_decision [veto], commercial_underwriting, cyber_underwriting) and Specialty (environmental_impairment [veto], parametric_crop, gig_platform_liability [veto]) tracks. See `examples/pc/*.py`.
⚠️ **NOT FOR PRODUCTION DEPLOYMENT** — Guidewire ClaimCenter / PolicyCenter / Origami integrations, loss-development triangles, ISO/Verisk loss-cost, NAIC Schedule P, Westlaw, USDA-RMA, EPA ECHO all listed as `PRODUCTION_GAPS`.

### Industrial Manufacturing & IoT (advisory only)

```python
from adv_multi_agent.industrial.workflows.product_liability_root_cause import (
    ProductLiabilityRootCauseWorkflow, ProductLiabilityRootCauseRequest,
)

# Product-liability attribution — DESIGN-DEFECT + OPERATOR-ERROR + WARNING-ADEQUACY
# flags + reviewer veto (fires when operator-error attribution masks design-defect signal)
result = await ProductLiabilityRootCauseWorkflow(config).run(
    request=ProductLiabilityRootCauseRequest(
        incident_summary="...", telematics_and_trace="...", standards_context="...",
    )
)
```

8 MVP workflows across Manufacturing Ops, Safety/Recall (2 veto), Strategic Capital, and Industrial IoT tracks. 19 Phase-2 workflow designs locked in [`docs/superpowers/specs/2026-05-14-industrial-domain-design.md`](docs/superpowers/specs/2026-05-14-industrial-domain-design.md). See `examples/industrial/*.py`.
⚠️ **NOT FOR PRODUCTION DEPLOYMENT** — PLM (Teamcenter / Windchill / Aras), ERP, MES, CMMS / FRACAS, telematics platform (InfoLink / Hyster Tracker / Linde connect:), standards library (ANSI / ITSDF / ISO), CPSC § 15(b) / OSHA / EU GPSR notification routing, D&B / RapidRatings supplier-risk feeds all listed as `PRODUCTION_GAPS`.

### Skills

```python
from adv_multi_agent.core.skills.registry import SkillRegistry

# bundled skills (no path needed)
registry = SkillRegistry(str(SkillRegistry.bundled_skills_path(domain="research")))
prompt = registry.get("literature_review").render(topic="X", depth="comprehensive", style="academic")
output = await executor.run(prompt)
```

### MCP server

```bash
# Register research skills as Claude Code tools (default)
claude mcp add adv-multi-agent-skills -- python -m adv_multi_agent.core.skills.mcp_server

# Per-domain registrations
SKILLS_DOMAIN=parole     claude mcp add adv-multi-agent-parole     -- python -m adv_multi_agent.core.skills.mcp_server
SKILLS_DOMAIN=retail     claude mcp add adv-multi-agent-retail     -- python -m adv_multi_agent.core.skills.mcp_server
SKILLS_DOMAIN=pc         claude mcp add adv-multi-agent-pc         -- python -m adv_multi_agent.core.skills.mcp_server
SKILLS_DOMAIN=industrial claude mcp add adv-multi-agent-industrial -- python -m adv_multi_agent.core.skills.mcp_server
```

---

## Architecture notes

- **Executor** — `claude-opus-4-7` with `thinking: {type: "adaptive"}` and configurable `effort`. Gemini 2.5 Pro supported via `[gemini]` extra. Uses `.messages.stream()` context manager throughout.
- **Reviewer** — GPT-4o by default. Set `REVIEWER_PROVIDER=anthropic` for a same-family pairing (less adversarial, no OpenAI key required). Same-family raises a `UserWarning` at construction.
- **Claim ledger** — append-only JSON, persisted after each mutation. 3-stage verifier resolves `PENDING → SUPPORTED / DISPUTED / RETRACTED`.
- **Wiki** — shared knowledge store across workflow runs. Self-improvement proposals require explicit human approval: `wiki.approve_improvement(id, human_reviewer_id="alice")` (M1: name persisted as audit trail).
- **Skills** — `.md` files with YAML frontmatter (`name`, `description`, `inputs`). **107 bundled templates** (15 research + 6 parole + 25 retail + 29 pc + 32 industrial). Drop `.md` files into any directory and point `Config(skills_dir=...)` at it.
- **Convergence patterns** — `BaseWorkflow` subclasses use one of three patterns: (1) score-only (`research/*` early workflows), (2) score + domain FLAGS conjunction gate (most retail / pc / industrial), (3) score + FLAGS + reviewer-veto (7 workflows where decisions are irreversible-class). Shared helpers in `core/_internal.py`: `extract_flags` (M1 line-anchored + H-IND-1 hyphen-tolerant sibling-stop), `extract_veto_directive` (M-PC-1 line-anchored + M2/L5/H-IND-1), `truncate_flag_display` (L-PC-5 re-injection cap of 16), `sanitize_for_prompt` (control-char strip + length cap), `_is_sibling_header_lhs` (shared sibling-stop helper).
- **Security model** — see [`docs/SECURITY_MODEL.md`](docs/SECURITY_MODEL.md). 5 audit cycles completed (2026-05-12 / 13 / 14 AM / 14 PM); zero CRIT/HIGH currently open. Latest closure: H-IND-1 (shared-parser hyphen-tolerant sibling-stop).

---

## Extension points

**Add a skill** — create `skills/my_skill.md` with frontmatter `name`, `description`, `inputs`. Auto-discovered at `SkillRegistry` load time.

**Add a workflow** — subclass `BaseWorkflow`, implement `async def run(self, **kwargs) -> WorkflowResult`. `BaseWorkflow.__init__` provides `executor`, `reviewer`, `ledger`, `wiki`.

```python
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult

class MyWorkflow(BaseWorkflow):
    async def run(self, task: str) -> WorkflowResult:
        output = await self.executor.run(task)
        review = await self.reviewer.review(output, criteria="...")
        return WorkflowResult(output=output, rounds=1,
                              final_score=review.score, converged=review.approved)
```

**Swap the reviewer** — set `REVIEWER_PROVIDER=anthropic` or pass a custom `ReviewerAgent` subclass to `BaseWorkflow.__init__`.

**Add a domain** — create `src/adv_multi_agent/<domain>/` with `workflows/`, `skills/templates/`, and `__init__.py`. Register package data in `pyproject.toml`.

---

## Tests

```bash
python -m pytest tests/          # 481 tests
python -m mypy src/ tests/ --strict
python -m ruff check src/ tests/
```

---

## Citation

This library implements the adversarial multi-agent collaboration pattern from the ARIS paper. **If you use this work, please cite the underlying research:**

> Yang, R., Li, Y., & Li, S. (2026). *ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration*. arXiv:2605.03042. https://arxiv.org/abs/2605.03042

BibTeX:

```bibtex
@article{yang2026aris,
  title   = {ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration},
  author  = {Yang, Ruofeng and Li, Yongcan and Li, Shuai},
  journal = {arXiv preprint arXiv:2605.03042},
  year    = {2026},
  url     = {https://arxiv.org/abs/2605.03042},
  note    = {Shanghai Jiao Tong University; Shanghai Innovation Institute}
}
```

Project page: https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep

All workflows in this library — research (4), parole (1), retail (8), pc (7), industrial (8 MVP of 27-workflow catalog) — are domain adaptations of the executor + cross-family-reviewer loop introduced in the ARIS paper. See `CITATION.cff` for machine-readable citation metadata.
