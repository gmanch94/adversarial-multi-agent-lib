"""Cross-domain convention guards (depth review 2026-07-23, D1 / D2 / D3).

These are the durable half of the depth review. The per-workflow suites assert
behaviour; these assert that the *convention* holds across every domain at
once, so a future workflow cannot silently reintroduce a closed class.

Per `LESSONS_LEARNED.md`: a claimed invariant with no test that recomputes it
from the source of truth is a claim, not a check. The 2026-07-18 F2 finding is
the precedent — 26 of 44 unit files assert flags with `any(substr in f)`, which
stays green through a parser slurp, so "1257 tests pass" is not evidence for
any of the three invariants below.

Guards:
  G1 (D1) — a module that declares `_FLAG_HEADERS` must USE it. A declared-but-
            never-referenced tuple looks load-bearing and is not: editing it
            changes nothing, because the real header strings are hardcoded
            elsewhere in the same file.
  G2 (D1) — every header string literal passed to `extract_flags` must be a
            member of that module's `_FLAG_HEADERS`. Closes the fail-OPEN
            rename path: a header renamed in the tuple but not at the call site
            makes `extract_flags` return `[]` forever, permanently satisfying
            `and not <flag class>` in the convergence gate.
  G3 (D2) — every reviewer-veto workflow must render the verbatim veto
            directive into `WorkflowResult.output`, not only into
            `metadata['veto_reason']`. The approver reads `output`.
  G4 (D3) — no metadata scalar may be a bare `request.<attr>`; each must go
            through `sanitize_for_prompt` (L-HEALTH-2 generalized).
"""
from __future__ import annotations

import ast
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


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _flag_headers(tree: ast.Module) -> tuple[str, ...] | None:
    """Return the module-level `_FLAG_HEADERS` literal, or None if absent."""
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "_FLAG_HEADERS":
                value = node.value
                if isinstance(value, (ast.Tuple, ast.List)):
                    return tuple(
                        el.value
                        for el in value.elts
                        if isinstance(el, ast.Constant) and isinstance(el.value, str)
                    )
    return None


# ---------------------------------------------------------------------------
# G1 — a declared _FLAG_HEADERS must be used (D1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_declared_flag_headers_is_actually_used(path: Path) -> None:
    tree = _parse(path)
    if _flag_headers(tree) is None:
        pytest.skip("module does not declare _FLAG_HEADERS")
    refs = sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and node.id == "_FLAG_HEADERS"
    )
    assert refs >= 2, (
        f"{path.name} declares _FLAG_HEADERS but never references it. A dead "
        "declaration reads as the source of truth while the real header "
        "strings are hardcoded elsewhere in the file — editing the tuple "
        "would silently change nothing. Drive the flag loop from the tuple "
        "(`for header in _FLAG_HEADERS:`) or delete it."
    )


# ---------------------------------------------------------------------------
# G2 — extract_flags literals must come from _FLAG_HEADERS (D1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_extract_flags_headers_match_flag_headers(path: Path) -> None:
    tree = _parse(path)
    headers = _flag_headers(tree)
    if headers is None:
        pytest.skip("module does not declare _FLAG_HEADERS")
    literals: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "extract_flags" or len(node.args) < 2:
            continue
        arg = node.args[1]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            literals.append(arg.value)
    stray = sorted(set(literals) - set(headers))
    assert not stray, (
        f"{path.name} calls extract_flags with header literal(s) {stray} that "
        f"are not in _FLAG_HEADERS {list(headers)}. A header renamed in the "
        "tuple but not at the call site makes extract_flags return [] forever "
        "— the convergence gate's `and not <flags>` is then permanently "
        "satisfied and that flag class is never enforced again (fail-OPEN). "
        "Pass the loop variable instead of a literal."
    )


# ---------------------------------------------------------------------------
# G3 — veto workflows must surface the directive in output (D2)
# ---------------------------------------------------------------------------


def _veto_workflow_files() -> list[Path]:
    out = []
    for path in _WORKFLOW_FILES:
        if "_compose_output" in path.read_text(encoding="utf-8"):
            out.append(path)
    return out


_VETO_FILES = _veto_workflow_files()
_VETO_IDS = [f"{p.parent.parent.name}/{p.name}" for p in _VETO_FILES]


def test_veto_workflow_census_is_stable() -> None:
    """25 veto workflows as of the 2026-07-23 depth review.

    Recomputed from source, not hardcoded in prose — if a veto workflow is
    added or removed, this fails and the reviewer re-reads the guards below.
    """
    assert len(_VETO_FILES) == 25, (
        f"veto-workflow count changed to {len(_VETO_FILES)}; confirm the new "
        "workflow renders its veto directive into output (D2) and update this "
        "count."
    )


@pytest.mark.parametrize("path", _VETO_FILES, ids=_VETO_IDS)
def test_compose_output_renders_veto_directive(path: Path) -> None:
    """The approver reads `WorkflowResult.output`.

    Pre-2026-07-23, 7 of 25 veto workflows composed the output as
    `draft + banner` and never rendered `veto_reason` — the reason for the halt
    lived only in `metadata['veto_reason']`, which the banner told the reader
    to go find. On reserve booking, coverage denial, and recall scope, that is
    the wrong default. This asserts the veto_reason parameter reaches the
    returned string.
    """
    tree = _parse(path)
    func: ast.FunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_compose_output":
            func = node
            break
    assert func is not None, f"{path.name} has no _compose_output"

    # The veto branch must reference the veto_reason parameter, not merely
    # test it for None.
    used_in_return = False
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        for sub in ast.walk(node.value):
            if isinstance(sub, ast.Name) and sub.id == "veto_reason":
                used_in_return = True
    assert used_in_return, (
        f"{path.name} _compose_output never interpolates veto_reason into a "
        "returned string. The vetoed output shows the draft plus a banner "
        "pointing at metadata['veto_reason'] — the approver reading .output "
        "never sees why the workflow halted. Render the directive inline."
    )


# ---------------------------------------------------------------------------
# G4 — metadata scalars must be sanitized (D3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", _WORKFLOW_FILES, ids=_IDS)
def test_metadata_scalars_are_sanitized(path: Path) -> None:
    """L-HEALTH-2, generalized to every domain.

    A metadata value of the bare form `request.<attr>` is uncapped and
    unsanitized: control characters survive, and a caller passing a multi-MB
    field gets it echoed whole into `WorkflowResult.metadata`. Healthcare was
    fixed in 2026-05-16; retail / pc / industrial carried 28 raw scalars until
    the 2026-07-23 depth review.
    """
    tree = _parse(path)
    raw: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and isinstance(key.value, str)):
                continue
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "request"
            ):
                raw.append(f"{key.value!r}: request.{value.attr}")
    assert not raw, (
        f"{path.name} puts unsanitized request field(s) into a metadata dict: "
        f"{raw}. Wrap with sanitize_for_prompt(..., max_chars=200) so control "
        "characters are stripped and the value is bounded (L-HEALTH-2)."
    )
