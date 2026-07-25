"""Cross-domain convention guards (depth review 2026-07-23 + audit A11).

These are the durable half of the depth review and the follow-up security
audit. The per-workflow suites assert behaviour; these assert that the
*convention* holds across every domain at once, so a future workflow cannot
silently reintroduce a closed class.

Per `LESSONS_LEARNED.md`: a claimed invariant with no test that recomputes it
from the source of truth is a claim, not a check. The 2026-07-18 F2 finding is
the precedent — most unit files assert flags with `any(substr in f)`, which
stays green through a parser slurp, so a green suite is not evidence for any
of the invariants below.

Guards:
  G1 — a module that calls `extract_flags` must DECLARE `_FLAG_HEADERS`, and a
       declared tuple must be USED. A declared-but-never-referenced tuple looks
       load-bearing and is not: editing it changes nothing, because the real
       header strings are hardcoded elsewhere in the same file.
  G2 — every header string literal passed to `extract_flags` (positionally OR
       by keyword) must be a member of that module's `_FLAG_HEADERS`. Closes
       the fail-OPEN rename path inside a module.
  G3 — every reviewer-veto workflow must render the verbatim veto directive
       into `WorkflowResult.output`, not only into `metadata['veto_reason']`.
  G4 — no metadata value may carry an unsanitized `request.<attr>`.
  G5 — every `_FLAG_HEADERS` member must appear verbatim in that module's
       reviewer-criteria text, inside an explicit emission block. This is the
       tuple↔prompt-template half of the rename path, which G1/G2 cannot see:
       they only compare code to code.
  G6 — every string literal used to index `current` / `accumulated` must be a
       member of `_FLAG_HEADERS`, so key drift fails at author time rather
       than silently yielding an empty checklist section via `.get(k, [])`.
  G7 — no workflow calls `<request>.to_prompt_text()` directly; the request-text
       boundary must route through `core._internal.sanitize_request_text`. The
       retired `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)`
       cut a long request's trailing fields off the executor prompt below
       n_fields x _MAX_FIELD_CHARS, and the reviewer only sees the executor
       draft, so the dropped evidence left the whole adversarial loop (H-1).
  G9 — no colon-suffixed flag header (`_FLAG_HEADERS` member) may appear in the
       reviewer-criteria PROSE; it belongs ONLY in the emission block. A header
       restated in the rubric body (a cross-ref "flag under X FLAGS:." or a
       "zero X FLAGS: ready" scoring line) is echoed by the reviewer, and once
       the echo lands line-anchored in the critique `_header_anchor_re` matches
       it: `extract_flags` unions in the template placeholder and, in a veto
       module, `extract_veto_directive` returns the literal placeholder so the
       halt fires with its reason destroyed (M-1, 2026-07-25 CGT ship-audit;
       same root class as C-1 but fail-CLOSED on the gate). Refer to a section
       in prose WITHOUT its trailing colon. Covers modules AND the mirrored
       `skills/templates/*_review.md`.

  (G8 is reserved for the L-1 gate-uses-`_flag_classes_unresolved` guard from
  the 2026-07-25 CGT ship-audit, not yet built.)
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "adv_multi_agent"
_DOMAINS = (
    "research",
    "parole",
    "retail",
    "pc",
    "industrial",
    "healthcare",
    "lifesciences",
)

# Calls whose result is not raw caller text, so a `request.<attr>` inside them
# is not an unsanitized metadata scalar.
_SANITIZING_CALLS = {"sanitize_for_prompt", "len"}
# Two spellings are in use: "End your review with exactly these lines:" (most
# domains) and "End your review with:" (parole + the two single-class retail
# workflows). Matching the bare prefix "End your review with" is NOT safe: the
# veto criteria block opens "End your review with a REVIEWER VETO: line ...",
# so a prefix match splits on that sentence instead and the "emission block"
# becomes everything after it — which still contains the headers, making the
# guard pass even with the real block deleted. (Caught by mutation-testing
# this guard; a loose anchor is the same class of bug the guard exists to
# catch.) The trailing colon is what distinguishes a block header.
_EMISSION_BLOCK_RE = re.compile(r"End your review with(?: exactly these lines)?:")


def _workflow_files() -> list[Path]:
    files: list[Path] = []
    for domain in _DOMAINS:
        wf_dir = _SRC / domain / "workflows"
        if not wf_dir.is_dir():
            continue
        files.extend(p for p in sorted(wf_dir.glob("*.py")) if p.name != "__init__.py")
    assert files, "no workflow modules discovered — path drift in _SRC"
    return files


_WORKFLOW_FILES = _workflow_files()
_IDS = [f"{p.parent.parent.name}/{p.name}" for p in _WORKFLOW_FILES]


def _template_files() -> list[Path]:
    files: list[Path] = []
    for domain in _DOMAINS:
        td = _SRC / domain / "skills" / "templates"
        if td.is_dir():
            files.extend(sorted(td.glob("*_review.md")))
    return files


_TEMPLATE_FILES = _template_files()
_TPL_IDS = [f"{p.parent.parent.parent.name}/{p.name}" for p in _TEMPLATE_FILES]

# G9 does NOT scan only the declared `_FLAG_HEADERS`. The runtime parser's
# generic terminator `_is_section_header` fires on ANY uppercase LHS ending in
# FLAGS followed by a colon (`core/_internal.py`), so a *non-tuple* header
# echoed line-anchored into a real section would truncate it — fail-OPEN, worse
# than M-1's fail-closed. This case-SENSITIVE, whitespace-flexible pattern
# matches that terminator shape at ANY line position (a reviewer reformats when
# it echoes, so a midline rubric mention is as dangerous as a line-anchored
# one). Case-sensitive on purpose: an all-lowercase "red flags:" in prose is not
# a parser terminator, so matching it would be a false positive.
_GENERIC_FLAG_HEADER_RE = re.compile(
    r"[A-Z][A-Z0-9\-]*(?:[ \t]+[A-Z0-9\-]+)*[ \t]+FLAGS[ \t]*:"
)


def _declared_header_re(header: str) -> re.Pattern[str]:
    """Case-insensitive, whitespace-flexible matcher for one declared header.

    `_header_anchor_re` (what `extract_flags` runs on the critique) is `(?mi)`
    with `[ \\t]+` between words, so `moa-linkage flags:` or `MOA-LINKAGE  FLAGS:`
    is a live parser match that a case-sensitive substring compare would miss.
    NOT a swap-in for `_header_anchor_re`: this is intentionally position-
    agnostic (no `^`) so it also catches a MIDLINE echo the reviewer could
    reflow to line-start; do not "simplify" it to the anchored form.
    """
    core = header.rstrip(":").strip()
    body = r"[ \t]+".join(re.escape(word) for word in core.split())
    return re.compile(r"(?i)" + body + r"[ \t]*:")


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_assignments(tree: ast.Module) -> dict[str, ast.expr]:
    out: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                out[node.target.id] = node.value
    return out


def _flag_headers(tree: ast.Module) -> tuple[str, ...] | None:
    value = _module_assignments(tree).get("_FLAG_HEADERS")
    if not isinstance(value, (ast.Tuple, ast.List)):
        return None
    return tuple(
        el.value
        for el in value.elts
        if isinstance(el, ast.Constant) and isinstance(el.value, str)
    )


def _extract_flags_calls(tree: ast.Module) -> list[ast.Call]:
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == "extract_flags":
            calls.append(node)
    return calls


def _header_literals(call: ast.Call) -> list[str]:
    """Header string literals from a call, positional OR keyword (A11-M6.3)."""
    out = []
    if len(call.args) >= 2 and isinstance(call.args[1], ast.Constant):
        if isinstance(call.args[1].value, str):
            out.append(call.args[1].value)
    for kw in call.keywords:
        if kw.arg == "header" and isinstance(kw.value, ast.Constant):
            if isinstance(kw.value.value, str):
                out.append(kw.value.value)
    return out


# ---------------------------------------------------------------------------
# G1 — a module using extract_flags declares _FLAG_HEADERS, and uses it
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_flag_headers_declared_and_used(path: Path) -> None:
    tree = _parse(path)
    headers = _flag_headers(tree)
    calls = _extract_flags_calls(tree)

    if not calls:
        assert headers is None, (
            f"{path.name} declares _FLAG_HEADERS but never calls extract_flags."
        )
        return

    # A11-M6.2: a positive assertion, not pytest.skip. Skipping let 8 modules
    # (5 of them veto workflows) opt out of G1+G2 entirely while still holding
    # hardcoded header literals — the exact class these guards exist to catch.
    assert headers is not None, (
        f"{path.name} calls extract_flags but declares no _FLAG_HEADERS. "
        "Declare the tuple so the header set has one source of truth and G2/G5 "
        "can check it against the call sites and the reviewer prompt."
    )
    refs = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "_FLAG_HEADERS"
    )
    assert refs >= 2, (
        f"{path.name} declares _FLAG_HEADERS but never references it. A dead "
        "declaration reads as the source of truth while the real header "
        "strings are hardcoded elsewhere in the file — editing the tuple "
        "would silently change nothing."
    )


# ---------------------------------------------------------------------------
# G2 — extract_flags literals ⊆ _FLAG_HEADERS
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_extract_flags_headers_match_flag_headers(path: Path) -> None:
    tree = _parse(path)
    headers = _flag_headers(tree)
    if headers is None:
        return
    literals: list[str] = []
    for call in _extract_flags_calls(tree):
        literals.extend(_header_literals(call))
    stray = sorted(set(literals) - set(headers))
    assert not stray, (
        f"{path.name} calls extract_flags with header literal(s) {stray} that "
        f"are not in _FLAG_HEADERS {list(headers)}. A header renamed in the "
        "tuple but not at the call site makes extract_flags return [] forever "
        "— the convergence gate's `and not <flags>` is then permanently "
        "satisfied and that flag class is never enforced again (fail-OPEN)."
    )


# ---------------------------------------------------------------------------
# G5 — _FLAG_HEADERS ⊆ the reviewer-criteria emission block  (A11-M1 / A11-M2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_flag_headers_are_requested_in_reviewer_criteria(path: Path) -> None:
    """The reviewer must be TOLD to emit every header the parser looks for.

    G1/G2 compare code to code and cannot see this. `claims_appeal_review.py`
    passed both while never instructing the reviewer to emit its three flag
    sections at all — so all three classes would parse as empty every round
    and the convergence gate silently reduced to score-only (A11-M2).
    """
    tree = _parse(path)
    headers = _flag_headers(tree)
    if headers is None:
        return

    criteria = "\n".join(
        value.value
        for name, value in _module_assignments(tree).items()
        if name.endswith("_CRITERIA")
        and isinstance(value, ast.Constant)
        and isinstance(value.value, str)
    )
    assert criteria, f"{path.name} declares _FLAG_HEADERS but has no *_CRITERIA text."

    blocks = list(_EMISSION_BLOCK_RE.finditer(criteria))
    assert blocks, (
        f"{path.name} reviewer criteria has no explicit emission block "
        f"({_EMISSION_BLOCK_RE.pattern}). Without it the reviewer is never "
        "told to emit the flag sections in a parseable form, every class "
        "parses as empty, and the convergence gate degenerates to score-only "
        "(fail-OPEN)."
    )
    # last match: the emission block is the final instruction in every template
    block = criteria[blocks[-1].end():]
    missing = [h for h in headers if h not in block]
    assert not missing, (
        f"{path.name} never asks the reviewer to emit {missing} in its emission "
        f"block, but the parser looks for them. extract_flags will return [] "
        "for each, which the gate reads as 'clean' (fail-OPEN). Keep the tuple "
        "and the emission block in lockstep."
    )


# ---------------------------------------------------------------------------
# G6 — current/accumulated lookup keys ⊆ _FLAG_HEADERS  (A11-L10)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_flag_dict_lookup_keys_match_flag_headers(path: Path) -> None:
    """Catch key drift statically instead of via a silently empty checklist.

    Every `_build_*_checklist` reads `accumulated.get(header, [])`, so a
    drifted key yields an empty section — the approver loses a warning with no
    signal at all. A static check fails at author time instead.
    """
    tree = _parse(path)
    headers = _flag_headers(tree)
    if headers is None:
        return
    keys: list[str] = []
    for node in ast.walk(tree):
        # accumulated["X"] / current["X"]
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            if node.value.id in {"current", "accumulated"} and isinstance(
                node.slice, ast.Constant
            ):
                if isinstance(node.slice.value, str):
                    keys.append(node.slice.value)
        # accumulated.get("X", []) — including on a parameter renamed at the
        # checklist boundary, so match on the method name too.
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and node.args:
                owner = node.func.value
                is_flag_dict = isinstance(owner, ast.Name) and owner.id in {
                    "current",
                    "accumulated",
                }
                if is_flag_dict and isinstance(node.args[0], ast.Constant):
                    if isinstance(node.args[0].value, str):
                        keys.append(node.args[0].value)
    stray = sorted(set(keys) - set(headers))
    assert not stray, (
        f"{path.name} indexes the flag dicts with {stray}, not in _FLAG_HEADERS "
        f"{list(headers)}. A `.get()` miss yields an empty checklist section "
        "with no error — the approver silently loses that warning."
    )


# ---------------------------------------------------------------------------
# G3 — veto workflows surface the directive in output  (D2 + A11-L9)
# ---------------------------------------------------------------------------


def _veto_workflow_files() -> list[Path]:
    """Select on the veto PARSER call, not on a composer's name (A11-L9).

    Selecting by the substring `_compose_output` silently excludes any future
    veto workflow whose composer is named differently.
    """
    out = []
    for path in _WORKFLOW_FILES:
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else getattr(func, "attr", None)
                )
                if name == "extract_veto_directive":
                    out.append(path)
                    break
    return out


_VETO_FILES = _veto_workflow_files()
_VETO_IDS = [f"{p.parent.parent.name}/{p.name}" for p in _VETO_FILES]


def test_veto_workflow_census_is_stable() -> None:
    """30 veto workflows as of the 2026-07-24 CGT/ATMP segment (D-LIFESCI-7/6).

    Recomputed from source, not hardcoded in prose — adding a veto workflow
    fails here and forces a re-read of the guards below. (25 at the 2026-07-23
    depth review + 5 CGT veto workflows: potency, HCT/P classification,
    comparability, durability-claim, donor-eligibility.)
    """
    assert len(_VETO_FILES) == 30, (
        f"veto-workflow count changed to {len(_VETO_FILES)}; confirm the new "
        "workflow renders its veto directive into output (D-DEPTH-2) and "
        "update this count."
    )


@pytest.mark.parametrize("path", _VETO_FILES, ids=_VETO_IDS)
def test_compose_output_renders_veto_directive(path: Path) -> None:
    """The approver reads `WorkflowResult.output`.

    Pre-2026-07-23, 7 of 25 veto workflows composed the output as
    `draft + banner` and never rendered `veto_reason` — the reason for the
    halt lived only in `metadata['veto_reason']`, which the banner told the
    reader to go find. On reserve booking, coverage denial, and recall scope
    that is the wrong default.
    """
    tree = _parse(path)
    func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_compose_output":
            func = node
            break
    assert func is not None, f"{path.name} has no _compose_output"

    # sorted by line: ast.walk is BFS, so its order is not source order and
    # `returns[-1]` would not be the veto branch.
    returns = sorted(
        (n for n in ast.walk(func) if isinstance(n, ast.Return) and n.value),
        key=lambda n: n.lineno,
    )
    assert len(returns) >= 2, (
        f"{path.name} _compose_output should have a no-veto return and a veto "
        "return."
    )
    # A11-L9: assert specifically on the VETO branch (the final return), not
    # "any return mentions veto_reason" — the latter is satisfied by a
    # no-veto return that merely references the parameter.
    veto_return = returns[-1]
    uses = any(
        isinstance(sub, ast.Name) and sub.id == "veto_reason"
        for sub in ast.walk(veto_return.value)  # type: ignore[arg-type]
    )
    assert uses, (
        f"{path.name} _compose_output's veto branch never interpolates "
        "veto_reason into the returned string. The vetoed output shows the "
        "draft plus a banner pointing at metadata['veto_reason'] — the "
        "approver reading .output never sees why the workflow halted."
    )


# ---------------------------------------------------------------------------
# G4 — metadata scalars are sanitized  (D3 + A11-L8)
# ---------------------------------------------------------------------------


def _carries_raw_request(value: ast.expr) -> bool:
    """True if `value` reaches a `request.<attr>` without a sanitizing call."""
    has_request = any(
        isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Name)
        and n.value.id == "request"
        for n in ast.walk(value)
    )
    if not has_request:
        return False
    for n in ast.walk(value):
        if isinstance(n, ast.Call):
            func = n.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name in _SANITIZING_CALLS:
                return False
    return True


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_metadata_scalars_are_sanitized(path: Path) -> None:
    """L-HEALTH-2, generalized to every domain.

    A metadata value reaching a bare `request.<attr>` is uncapped and
    unsanitized: control characters survive, and a caller passing a multi-MB
    field gets it echoed whole into `WorkflowResult.metadata`.

    A11-L8 widened this beyond the exact `request.attr` node to any expression
    that reaches one — `request.attr[:200]`, `f"{request.attr}"`, `str(...)` —
    and beyond dict literals to `metadata["k"] = ...` assignments.
    """
    tree = _parse(path)
    raw: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                    continue
                if _carries_raw_request(value):
                    raw.append(f"{key.value!r}: <raw request.*>")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and "metadata" in target.value.id
                    and _carries_raw_request(node.value)
                ):
                    raw.append(f"{ast.unparse(target)} = <raw request.*>")

    assert not raw, (
        f"{path.name} puts unsanitized request field(s) into metadata: {raw}. "
        "Wrap with sanitize_for_prompt(..., max_chars=200) so control "
        "characters are stripped and the value is bounded (L-HEALTH-2)."
    )


# ---------------------------------------------------------------------------
# G7 — request text bounded via sanitize_request_text, never a bespoke
#      post-concat sanitize_for_prompt cap  (H-1 / D-A11-6)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_request_text_routes_through_shared_helper(path: Path) -> None:
    """No workflow may call `<request>.to_prompt_text()` directly.

    The request-text boundary is `core._internal.sanitize_request_text`, which
    renders `to_prompt_text()` and applies only the control-char / NFC pass plus
    a field-count backstop. The retired convention wrapped it in
    `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)`; 6000 sits
    below n_fields x _MAX_FIELD_CHARS for any workflow with more than four
    fields, so a long request had its trailing fields — the veto/flag evidence —
    hard-cut off the executor prompt. Because the reviewer only ever sees the
    executor draft (`reviewer.review(output, ...)`), evidence dropped there
    leaves the whole adversarial loop (H-1). The shared helper is now the ONLY
    caller of `to_prompt_text()`, so a direct call in a workflow module is
    either the old guillotine or an unbounded raw embed.
    """
    tree = _parse(path)
    hits = sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_prompt_text"
    )
    assert not hits, (
        f"{path.name} calls .to_prompt_text() directly at line(s) {hits}. Route "
        "the request through sanitize_request_text(request) instead — a bespoke "
        "sanitize_for_prompt(..., max_chars=N) cap silently guillotines the "
        "trailing request fields off the executor prompt (H-1 / D-A11-6)."
    )


# ---------------------------------------------------------------------------
# G9 — no colon-suffixed flag header in reviewer-criteria PROSE  (M-1)
# ---------------------------------------------------------------------------


def _criteria_prose(text: str) -> str:
    """The rubric body preceding the emission block.

    The colon-headers the reviewer is TOLD to emit live in the emission block;
    everything before it is prose the reviewer reads and may echo. `blocks[-1]`
    is deliberate: the veto-criteria sentence ("End your review with a REVIEWER
    VETO: line ...") is not matched by `_EMISSION_BLOCK_RE` (no trailing colon
    on "with"), so the last match is the real flag-emission block.
    """
    blocks = list(_EMISSION_BLOCK_RE.finditer(text))
    return text[: blocks[-1].start()] if blocks else text


def _prose_header_offenders(prose: str, declared: tuple[str, ...]) -> list[str]:
    """Every colon-suffixed section header the parser could match in `prose`.

    Two prongs, matching the two runtime matchers:
      - the generic uppercase `X FLAGS:` shape (`_is_section_header`, the sibling
        terminator) — catches a header that is NOT in this module's tuple; and
      - each declared header, case-insensitively and whitespace-flexibly
        (`_header_anchor_re`, `(?mi)`) — catches a `moa-linkage flags:` variant
        the generic uppercase prong would skip.
    """
    hits = {m.group(0) for m in _GENERIC_FLAG_HEADER_RE.finditer(prose)}
    for header in declared:
        if _declared_header_re(header).search(prose):
            hits.add(header)
    return sorted(hits)


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_no_flag_header_colon_in_module_criteria_prose(path: Path) -> None:
    """A restated header in the rubric body is a fail-CLOSED finding-integrity
    hole (M-1). The reviewer echoes it; once the echo is line-anchored in the
    critique, `_header_anchor_re` matches it and the real findings/veto reason
    are replaced by the template placeholder. Keep the colon-form in the
    emission block only; refer to a section in prose without its colon.
    """
    tree = _parse(path)
    declared = _flag_headers(tree)
    if declared is None:
        return
    offenders: list[str] = []
    for name, value in _module_assignments(tree).items():
        if not (
            name.endswith("_CRITERIA")
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            continue
        prose = _criteria_prose(value.value)
        offenders += [f"{name}:{tok!r}" for tok in _prose_header_offenders(prose, declared)]
    assert not offenders, (
        f"{path.name} restates flag header(s) {offenders} in reviewer-criteria "
        "prose. A colon-suffixed header belongs ONLY in the emission block: "
        "restated in the rubric body it is echoed by the reviewer, and once the "
        "echo lands line-anchored in the critique the parser slices the real "
        "findings (and, in a veto module, the veto reason) out (M-1). Refer to "
        "the section without its trailing colon, e.g. 'flag under MOA-LINKAGE "
        "FLAGS'."
    )


@pytest.mark.parametrize("path", _TEMPLATE_FILES, ids=_TPL_IDS)
def test_no_flag_header_colon_in_template_prose(path: Path) -> None:
    """Same invariant on the mirrored skill templates (`*_review.md`).

    No tuple to read here, so the generic uppercase prong carries it (template
    headers are uppercase). A template with no emission block is scanned whole —
    that is deliberate, not a silent opt-out: a genuine flag template has an
    emission block, and a non-flag review template has no `X FLAGS:` token to
    match, so scanning the whole file only ever flags a malformed one.
    """
    text = path.read_text(encoding="utf-8")
    blocks = list(_EMISSION_BLOCK_RE.finditer(text))
    prose = text[: blocks[-1].start()] if blocks else text
    offenders = _prose_header_offenders(prose, ())
    assert not offenders, (
        f"{path.name} restates flag header(s) {offenders} in prose above its "
        "emission block. The reviewer echoes the rubric and the parser then "
        "slices real findings out (M-1). Drop the trailing colon in prose."
    )
