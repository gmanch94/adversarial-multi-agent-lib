# Persistence layer — retro-spec (2026-05-12)

Retro-spec for `ClaimLedger` and `ResearchWiki` — the two persistent state stores shipped in the initial implementation. Both use append-only JSON files on the local filesystem.

---

## What shipped

### ClaimLedger (`src/core/ledger.py`)

- **Claim lifecycle:** `PENDING → SUPPORTED | DISPUTED | RETRACTED`. All transitions via explicit methods (`resolve`, `dispute`, `retract`).
- **Evidence attachment:** `attach_evidence(claim_id, Evidence)` appends an `Evidence` struct (source, excerpt, page_or_line).
- **Queries:** `pending()`, `disputed()`, `by_status()`, `summary()`.
- **Persistence:** `_save()` called after every mutation; `_load()` at init if file exists. File is valid UTF-8 JSON with `updated_at` timestamp + `claims` dict.
- **IDs:** 8-char UUID prefix (`uuid4()[:8]`). Collision-free at expected V0 claim volume (<1000 claims per run).

### ResearchWiki (`src/core/wiki.py`)

- **Entry kinds:** `LITERATURE | HYPOTHESIS | EXPERIMENT | FEEDBACK | IMPROVEMENT | NOTE`.
- **Self-improvement proposals:** `add_improvement()` creates an entry with `approved=None`. Requires explicit `approve_improvement()` or `reject_improvement()` — never auto-committed.
- **`context_for_round()`:** returns most-recent N entries formatted as a block for prompt injection. Accepts `round_num` param (currently used only for metadata, not as a filter).
- **Supersedes chain:** `supersedes` field allows entries to reference the ID they replace (not enforced by a constraint, by convention only).
- **Persistence:** same pattern as ClaimLedger — `_save()` on every mutation.

---

## Invariants enforced (× attack surface)

| Invariant | Normal usage (via workflow) | Direct class instantiation | Enforcement |
|---|---|---|---|
| Claims append-only; never deleted | Workflows call `ledger.add()` / `resolve()` | Direct callers use same methods; no `delete()` exists | No delete method. Status transitions update in-place but no row is removed |
| Status is a forward-only ratchet (no re-pending) | `resolve()` called by verifier | Direct caller can call `resolve()` with any status | **Gap**: `resolve()` accepts any `ClaimStatus` value including back-to-`PENDING`. No transition guard. |
| Self-improvement proposals require explicit approval | `AutoReviewLoop` calls `approve_improvement()` / `reject_improvement()` | Direct callers can skip the approval step by just reading `pending_improvements()` and acting on them | Proposals sit in `approved=None` state until explicitly acted on; loop logic enforces approval before adoption |
| Persist after every mutation | All mutation methods call `_save()` | Same — all public mutation methods call `_save()` at the end | `_save()` is the last line of every mutating method |
| IDs are unique per run | `uuid.uuid4()[:8]` | Same | **Gap**: 8-char prefix has non-zero collision probability at >10K claims. Acceptable at V0 scale. |
| `approve_improvement()` only valid on IMPROVEMENT kind | Method checks `entry.kind != EntryKind.IMPROVEMENT` | Same | `ValueError` raised on wrong kind |

---

## Files

```
src/core/ledger.py          ClaimLedger, Claim, Evidence, ClaimStatus
src/core/wiki.py            ResearchWiki, WikiEntry, EntryKind
```

---

## Known gaps / V1 followups

- **No status transition guard on `ClaimLedger`.** `resolve(id, ClaimStatus.PENDING, ...)` is callable — a claim can be "un-resolved" back to PENDING. Add a guard: `if claim.status != ClaimStatus.PENDING: raise ValueError(...)` at the top of `resolve()`. Or define an explicit transition table.
- **`context_for_round()` ignores `round_num` filter.** The method accepts `round_num` but uses it only in the signature — all entries regardless of round are returned (sorted by round, then sliced). Either filter by `round_num` OR rename the param to remove ambiguity.
- **No concurrent-write protection.** Two processes writing to the same `ledger.json` or `wiki.json` concurrently will race. Last writer wins; intermediate state is lost. Acceptable for single-process library use; document the limitation. V1: file locking (`fcntl`/`portalocker`) or SQLite.
- **Full file rewrite on every mutation.** `_save()` serializes the entire store on each call. For large research runs (thousands of claims), this is slow. V1: append-only line-delimited JSON or SQLite.
- **No max-size enforcement.** Claim text, evidence excerpts, and wiki body are unbounded strings. A malformed or adversarial model output could write megabytes to a single field. Add length caps in `add()` / `attach_evidence()`.
- **`supersedes` field is convention-only.** Wiki entries can claim to supersede IDs that don't exist, or supersede entries of a different kind. No integrity check. V1: validate `supersedes` ID exists and is not `None` at write time.
- **ID collisions at >10K items.** 8-char hex prefix = 2^32 space. At 10K items collision probability is ~1.2%. Upgrade to full UUID or 12-char prefix before production use.

---

## Cross-references

- [docs/decisions.md](../decisions.md) — #4 (JSON persistence rationale), #6 (dataclasses for internal objects).
- [src/assurance/verifier.py](../../../src/assurance/verifier.py) — primary consumer of ClaimLedger.
- [src/workflows/review_loop.py](../../../src/workflows/review_loop.py) — writes claims + wiki feedback entries.
