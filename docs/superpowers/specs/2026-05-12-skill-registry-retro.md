# Skill registry — retro-spec (2026-05-12)

Retro-spec for `SkillRegistry` and the three bundled skill markdown templates shipped in the initial implementation.

---

## What shipped

### SkillRegistry (`src/skills/registry.py`)

- **Discovery:** globs `*.md` from `skills/` directory at construction. Silently skips files without valid frontmatter.
- **Frontmatter parsing:** minimal YAML parser (`_parse_simple_yaml`) handles string scalars and inline lists (`[a, b, c]`). No external YAML dependency.
- **Skill struct:** `name`, `description`, `inputs` (list of required placeholder names), `template` (prompt body), `path`.
- **Rendering:** `skill.render(**kwargs)` validates all required inputs are present, then calls `str.format(**kwargs)` on the template.
- **Public API:** `registry.get(name)`, `registry.list()`, `registry.describe()`, `registry.reload()`.

### Bundled skills

| File | Name | Inputs |
|---|---|---|
| `skills/review.md` | `review` | `text`, `criteria` |
| `skills/generate.md` | `generate` | `artifact_type`, `topic`, `context` |
| `skills/rebuttal.md` | `rebuttal` | `comments`, `paper_context` |

---

## Invariants enforced (× attack surface)

| Invariant | Normal usage | Direct registry instantiation | Enforcement |
|---|---|---|---|
| Missing inputs raise before any API call | `skill.render()` checks `missing = [k for k in self.inputs if k not in kwargs]` | Same | `ValueError` raised with missing key list before `str.format()` |
| Unknown skill raises clearly | `registry.get(name)` raises `KeyError` with available list | Same | `KeyError` with message listing available skills |
| Skills are read-only once loaded | No mutate methods on `Skill` dataclass | `registry.reload()` re-reads from disk | `Skill` is a frozen dataclass (effectively — no setters) |
| Frontmatter is required | `_parse()` returns `None` if no frontmatter; `_load()` skips `None` results | Same | Silent skip — **no warning emitted** |
| `inputs` is always a list | `_parse_simple_yaml` returns `list` for inline arrays or wraps scalar in `[scalar]` | Same | `isinstance(inputs_raw, list)` check with fallback wrap |

---

## Files

```
src/skills/registry.py    SkillRegistry, Skill
skills/review.md          Adversarial review skill
skills/generate.md        Structured artifact generation skill
skills/rebuttal.md        Peer-review rebuttal skill
```

---

## Known gaps / V1 followups

- **`str.format(**kwargs)` breaks on templates containing literal `{` or `}`.** Any skill template that includes JSON examples, code snippets, or LaTeX curly braces will raise `KeyError` or `ValueError` when rendered. Replace `str.format()` with a safe substitute (e.g. `string.Template` with `$placeholder` syntax, or Jinja2) or double-escape literal braces in templates (`{{` / `}}`). This is a correctness bug for any ARIS-extended skill that includes a JSON schema example.
- **Skills dir silently skips files with no frontmatter.** A typo in the opening `---` produces a silent no-op. Callers get no warning that a file was skipped. Add a `warnings.warn()` when a `.md` file is found but not parsed.
- **`_parse_simple_yaml` doesn't handle multi-line values.** YAML continuation lines (indented after a `key:`) are not supported. Skill descriptions or input docs longer than one line will be truncated at the first line. Either restrict frontmatter to single-line values (document the constraint) or use `pyyaml` for frontmatter parsing.
- **No skill versioning.** Changing a skill template is silent — no version field, no migration path. Add an optional `version: "1.0"` frontmatter field and expose it in `registry.describe()`.
- **No skill namespace isolation.** Two skills with the same `name` in different files silently overwrite each other (last `.md` file sorted by glob wins). Add a warning on name collision in `_load()`.
- **Skill content is trusted.** `SkillRegistry` treats `.md` file content as trusted prompt text. If `skills/` is user-writable by untrusted parties, a malicious skill could inject instructions that override the agent's system prompt. Document the trust boundary: `skills/` must be in a trusted, access-controlled directory.
- **No bundled skill for experiment planning or citation.** ARIS §3.1 describes 65+ skills. Only 3 are shipped. Phase 4 (build-plan) tracks this.

---

## Cross-references

- [docs/decisions.md](../decisions.md) — #5 (Markdown skill registry rationale).
- [docs/build-plan.md](../build-plan.md) — Phase 4 (extended skill library).
- [src/core/agents.py](../../../src/core/agents.py) — rendered skill prompts are passed to `ExecutorAgent.run()`.
