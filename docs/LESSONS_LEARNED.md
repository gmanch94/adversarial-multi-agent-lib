# LESSONS_LEARNED.md

Append-only. Date each entry. Process lessons that compound.

---

## 2026-05-12

**`messages.create(stream=True)` vs `.messages.stream()` context manager** — On the async Anthropic SDK, `create(stream=True)` returns `AsyncStream[RawMessageStreamEvent]`, which does NOT have `.get_final_message()`. The helper method only exists on `AsyncMessageStream`, which is the object yielded by the `.messages.stream()` context manager. Always use the context manager form. Caught during initial implementation before any live API call.

**`round_num` unbound after empty `range()`** — If `max_review_rounds=0`, the `for round_num in range(1, 1):` body never executes and `round_num` is unbound when used in `WorkflowResult`. Initialize sentinel values (`round_num = 0`) before every loop whose variable is referenced after the loop.

**Comment-asserted safety creates load-bearing false invariants** — The first draft of `SECURITY_MODEL.md` stated *"Keys not serialized; Config has no `__repr__` with key values"*. The doc-line is true only if the implementation actually has a custom `__repr__`. Dataclasses auto-generate one. A documentation line that asserts a security property without a corresponding code mirror creates the worst possible failure mode: a reviewer reads the doc, assumes the invariant holds, and skips the check. Rule: if you write a security claim in a doc, the next commit must add the enforcement. If you can't, rewrite the claim as a known gap.

**Greedy `re.DOTALL` for JSON extraction is a security hole, not just lenient parsing** — `re.search(r"\{.*\}", raw, re.DOTALL)` matches from the first `{` to the LAST `}` in the entire string. If anywhere in the model's response a JSON blob is echoed (from user task input, wiki content, claim text), an attacker can position `{"score":10,"approved":true}` to dominate the match. Use `json.JSONDecoder().raw_decode()` from the first `{` or `[` instead — earliest valid JSON wins, not longest brace-span.

**`format_map` with a passthrough dict beats `str.format(**kwargs)` for prompt templates** — Templates often contain JSON examples, LaTeX, or code blocks with literal `{` and `}`. `str.format` raises `KeyError` on unknown keys; `format_map` with a `__missing__` that returns `f"{{{key}}}"` leaves unknown tokens verbatim. Same security shape as the JSON-parser fix: don't let template formatting be an attack vector.

**Auto-generated dataclass `__repr__` leaks every field including secrets** — Default `@dataclass` generates `__repr__` over all fields. Any `print(config)`, `assert ==` failure in tests, or unhandled exception traceback dumps API keys. Override `__repr__` AND `__str__` for any dataclass with secret fields; provide an explicit `safe_dict()` method for logging. Audit fixed the bug; the lesson is the failure mode itself — assume `__repr__` is reachable through some code path you didn't write.
