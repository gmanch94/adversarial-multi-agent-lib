# Semver policy

**Status:** active from 2026-05-18 (Tier 2.2 ship).
**Scope:** `adv_multi_agent` library. Sibling deployments under `examples/production/` follow their own cadence (operator-owned).

---

## The contract

| Bump   | Allowed change | Example |
|--------|---------------|---------|
| **Patch** `0.x.y → 0.x.y+1` | Bug fixes, internal refactors, doc edits | A regex tightened; a `# type: ignore` removed; comment fixed |
| **Minor** `0.x.y → 0.x+1.0` | Additive only — new symbols in `__all__`, new optional kwargs with defaults, new optional Protocol methods (default-implemented), new dataclass fields with defaults | `EncryptedCheckpointStore.seal()` added; `Checkpoint.integrity_tag` added; new module `schema_migrations` exported |
| **Major** `0.x.y → 0.y+1.0` | Breaking changes to public API — removing symbols, renaming kwargs, adding required kwargs, removing dataclass fields, changing return types | `_inner` → `inner` rename (would have been major if `_inner` were public; it wasn't); removing `RunHaltedByVeto` |

Pre-1.0 caveat: under semver, 0.x bumps are technically free to break. We voluntarily honor the minor/major split above so operators can pin `>=0.x,<0.x+1` and trust additivity.

---

## What counts as "public API"

**Public** = symbols listed in `core/durable/__init__.py:__all__`. The Tier 2.2 pin (`tests/unit/durable/test_public_api_stability.py`) is the source of truth.

**Private** = anything else, including underscore-prefixed symbols (`_inner`, `_encrypt_request_json`, `_compute_integrity_payload`). Private symbols may change in any release without notice. Operator code that imports private symbols is on the operator.

Edge case: `EncryptedCheckpointStore.inner` is a public `@property` (D-API-3). The underlying `self._inner` attribute is private. Operators should always go through `store.inner`, never `store._inner`.

---

## How a public API change ships

1. Author proposes the change in a PR.
2. `test_public_api_stability.py` fails — the golden constants no longer match.
3. PR author **updates the golden** in the same commit and writes the semver classification in the commit body:
   > "Minor: adds `EncryptedCheckpointStore.seal()` to public surface (operator scripts can now drop reach-through to `_encrypt_request_json`)."
4. Reviewer sanity-checks the classification.
5. The next release version bumps accordingly.

The test exists to convert "I forgot to bump" into a CI failure at PR time. It does not auto-bump versions; that remains a release-engineering decision.

---

## Inner workflow + sibling deployment surfaces (out of scope)

This policy covers `adv_multi_agent.core.*` only. Behavioral changes outside that surface — workflow scoring rules, MCP server tools, sibling deployment scripts, OTel collector config — are not gated by this policy. Each surface has its own runbook + change log.

---

## Cross-references

- `docs/superpowers/specs/2026-05-18-api-stability-design.md` — design rationale (D-API-1..5)
- `docs/SECURITY_MODEL.md` §4 — public-API trust boundary
- `tests/unit/durable/test_public_api_stability.py` — the CI gate
- `core/durable/__init__.py` — current public surface
