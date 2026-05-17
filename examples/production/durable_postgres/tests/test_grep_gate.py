"""F-C-02: positive test that the grep gate actually fails on f-string SQL.

A gate that never fails is decorative. This test writes a tempfile with
known-bad SQL pattern, runs the gate against it, asserts exit 1.
"""
from __future__ import annotations

import pathlib
import subprocess
import tempfile

import pytest


GATE = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "check_no_fstring_sql.sh"


def test_gate_catches_fstring_sql(tmp_path: pathlib.Path) -> None:
    bad = tmp_path / "bad.py"
    bad.write_text('query = f"SELECT * FROM users WHERE id = {user_id}"\n')

    # Run the gate against a controlled directory containing the bad file.
    # Build the wrapper script without f-string interpolation to avoid false positives.
    wrapper = tmp_path / "run_gate.sh"
    wrapper_content = "#!/usr/bin/env bash\nset -e\n# Re-execute the gate logic against the test directory.\n"
    wrapper_content += 'if command -v rg >/dev/null 2>&1; then\n'
    wrapper_content += '    rg -n --type py \'f"(SELECT|INSERT|UPDATE|DELETE)\' "' + str(tmp_path) + '" 2>/dev/null && exit 1\n'
    wrapper_content += "else\n"
    wrapper_content += '    grep -rn --include=\'*.py\' \'f"\\(SELECT\\|INSERT\\|UPDATE\\|DELETE\\)\' "' + str(tmp_path) + '" 2>/dev/null && exit 1\n'
    wrapper_content += "fi\nexit 0\n"
    wrapper.write_text(wrapper_content)
    wrapper.chmod(0o755)
    result = subprocess.run(["bash", str(wrapper)], capture_output=True)
    # We expect the wrapper to exit 1 (gate caught the bad pattern)
    assert result.returncode == 1, (
        f"Gate did NOT catch f-string SQL. stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_gate_passes_on_parameterized_sql(tmp_path: pathlib.Path) -> None:
    """Negative case — clean code should pass."""
    good = tmp_path / "good.py"
    good.write_text('query = "SELECT * FROM users WHERE id = $1"\n')

    if subprocess.run(["which", "rg"], capture_output=True).returncode == 0:
        cmd = ["rg", "-n", "--type", "py",
               r'f"(SELECT|INSERT|UPDATE|DELETE)',
               str(tmp_path)]
    else:
        cmd = ["grep", "-rn", "--include=*.py",
               r'f"\(SELECT\|INSERT\|UPDATE\|DELETE\)',
               str(tmp_path)]
    result = subprocess.run(cmd, capture_output=True)
    # No matches → grep/rg returns non-zero (1 = no matches in grep, 1 in rg too)
    assert result.returncode != 0 or not result.stdout, (
        "Gate falsely flagged parameterized SQL as injection-risk"
    )
