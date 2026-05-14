"""Unit tests for src/skills/registry.py — no API calls."""
from __future__ import annotations

from pathlib import Path

import pytest

from adv_multi_agent.core.skills.registry import SkillRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_skill(
    skills_dir: Path,
    filename: str,
    name: str = "my_skill",
    description: str = "A test skill",
    inputs: str = "[topic]",
    body: str = "Tell me about {topic}.",
) -> Path:
    """Write a minimal valid skill .md file."""
    content = f"---\nname: {name}\ndescription: {description}\ninputs: {inputs}\n---\n{body}"
    path = skills_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Valid skill loading
# ---------------------------------------------------------------------------


class TestSkillLoading:
    def test_valid_skill_loads(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "review.md", name="review")
        registry = SkillRegistry(str(tmp_path))
        assert "review" in registry.list()

    def test_skill_name_from_frontmatter(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "something.md", name="custom_name")
        registry = SkillRegistry(str(tmp_path))
        assert "custom_name" in registry.list()

    def test_skill_description_stored(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s.md", name="skill_a", description="Does X")
        registry = SkillRegistry(str(tmp_path))
        assert registry.get("skill_a").description == "Does X"

    def test_skill_inputs_stored(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s.md", name="skill_b", inputs="[topic, style]")
        registry = SkillRegistry(str(tmp_path))
        assert registry.get("skill_b").inputs == ["topic", "style"]

    def test_empty_dir_loads_empty(self, tmp_path: Path) -> None:
        registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []

    def test_nonexistent_dir_loads_empty(self, tmp_path: Path) -> None:
        registry = SkillRegistry(str(tmp_path / "no_such_dir"))
        assert registry.list() == []

    def test_reload_picks_up_new_file(self, tmp_path: Path) -> None:
        registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []
        write_skill(tmp_path, "new.md", name="new_skill")
        registry.reload()
        assert "new_skill" in registry.list()


# ---------------------------------------------------------------------------
# Invalid skill names
# ---------------------------------------------------------------------------


class TestInvalidSkillNames:
    def test_uppercase_name_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text(
            "---\nname: BadName\ndescription: x\ninputs: []\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning, match="invalid skill name"):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []

    def test_name_with_slash_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text(
            "---\nname: with/slash\ndescription: x\ninputs: []\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []

    def test_name_with_space_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text(
            "---\nname: has space\ndescription: x\ninputs: []\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []

    def test_empty_name_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "bad.md").write_text(
            "---\nname: \ndescription: x\ninputs: []\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []


# ---------------------------------------------------------------------------
# Invalid inputs
# ---------------------------------------------------------------------------


class TestInvalidInputs:
    def test_hyphenated_input_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "s.md").write_text(
            "---\nname: skill_c\ndescription: x\ninputs: [foo-bar]\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning, match="invalid input name"):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []

    def test_numeric_start_input_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "s.md").write_text(
            "---\nname: skill_d\ndescription: x\ninputs: [1foo]\n---\nbody",
            encoding="utf-8",
        )
        with pytest.warns(UserWarning):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []


# ---------------------------------------------------------------------------
# Duplicate names
# ---------------------------------------------------------------------------


class TestDuplicateNames:
    def test_duplicate_name_raises(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "a.md", name="dupe")
        write_skill(tmp_path, "b.md", name="dupe")
        with pytest.raises(ValueError, match="duplicate skill name"):
            SkillRegistry(str(tmp_path))


# ---------------------------------------------------------------------------
# _split_frontmatter — line-anchored (LOW-2 regression guard)
# ---------------------------------------------------------------------------


class TestSplitFrontmatter:
    def test_dashes_in_value_do_not_terminate(self, tmp_path: Path) -> None:
        """A value containing '---' mid-line must NOT split the frontmatter."""
        content = (
            "---\n"
            "name: tricky\n"
            "description: value with --- inside it\n"
            "inputs: []\n"
            "---\n"
            "body text"
        )
        (tmp_path / "tricky.md").write_text(content, encoding="utf-8")
        registry = SkillRegistry(str(tmp_path))
        skill = registry.get("tricky")
        assert skill.description == "value with --- inside it"
        assert skill.template == "body text"

    def test_no_frontmatter_warns_and_skips(self, tmp_path: Path) -> None:
        (tmp_path / "nofm.md").write_text("just body text, no frontmatter", encoding="utf-8")
        with pytest.warns(UserWarning, match="missing or malformed frontmatter"):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []


# ---------------------------------------------------------------------------
# Non-recursive loading
# ---------------------------------------------------------------------------


class TestNonRecursiveLoading:
    def test_subdir_md_not_loaded(self, tmp_path: Path) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        write_skill(sub, "nested.md", name="nested_skill")
        registry = SkillRegistry(str(tmp_path))
        assert "nested_skill" not in registry.list()


# ---------------------------------------------------------------------------
# Skill.render — passthrough + missing input
# ---------------------------------------------------------------------------


class TestSkillRender:
    def test_render_substitutes_declared(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s.md", name="sk", inputs="[topic]", body="About {topic}.")
        skill = SkillRegistry(str(tmp_path)).get("sk")
        assert skill.render(topic="Python") == "About Python."

    def test_render_missing_declared_input_raises(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s.md", name="sk2", inputs="[topic]", body="About {topic}.")
        skill = SkillRegistry(str(tmp_path)).get("sk2")
        with pytest.raises(ValueError, match="missing inputs"):
            skill.render()

    def test_render_passthrough_unknown_tokens(self, tmp_path: Path) -> None:
        """Unknown {tokens} in template must be left verbatim — CRIT-1 regression guard."""
        write_skill(
            tmp_path,
            "s.md",
            name="sk3",
            inputs="[declared]",
            body="{declared} and {undeclared}",
        )
        skill = SkillRegistry(str(tmp_path)).get("sk3")
        result = skill.render(declared="X")
        assert result == "X and {undeclared}"

    def test_render_json_braces_preserved(self, tmp_path: Path) -> None:
        """Literal doubled braces in template must survive round-trip."""
        write_skill(
            tmp_path,
            "s.md",
            name="sk4",
            inputs="[topic]",
            body='Example JSON: {{"key": "value"}} for {topic}.',
        )
        skill = SkillRegistry(str(tmp_path)).get("sk4")
        result = skill.render(topic="test")
        assert result == 'Example JSON: {"key": "value"} for test.'

    def test_h3_oversized_input_value_raises(self, tmp_path: Path) -> None:
        """H3: caller-supplied input values must be size-capped to bound prompt size."""
        write_skill(tmp_path, "s.md", name="big", inputs="[x]", body="V={x}")
        skill = SkillRegistry(str(tmp_path)).get("big")
        with pytest.raises(ValueError, match="exceeds"):
            skill.render(x="x" * 100_000)

    def test_h3_too_many_input_keys_raises(self, tmp_path: Path) -> None:
        """H3: caller-supplied input dict must have a bounded key count."""
        write_skill(tmp_path, "s.md", name="many", inputs="[x]", body="V={x}")
        skill = SkillRegistry(str(tmp_path)).get("many")
        too_many = {f"k{i}": "v" for i in range(200)}
        too_many["x"] = "ok"
        with pytest.raises(ValueError, match="too many"):
            skill.render(**too_many)

    def test_h3_control_chars_stripped_from_value(self, tmp_path: Path) -> None:
        """H3: control chars (incl. ANSI ESC) stripped from rendered output."""
        write_skill(tmp_path, "s.md", name="ctrl", inputs="[x]", body="V={x}")
        skill = SkillRegistry(str(tmp_path)).get("ctrl")
        out = skill.render(x="hi\x1b[2Jbye\x00!")
        assert "\x1b" not in out
        assert "\x00" not in out
        assert "hi" in out and "bye" in out

    def test_l_pc_4_braces_stripped_from_input_value(self, tmp_path: Path) -> None:
        """L-PC-4: braces in input values must be stripped to prevent
        format-syntax smuggling into the rendered prompt."""
        write_skill(tmp_path, "s.md", name="brace", inputs="[x]", body="V={x}")
        skill = SkillRegistry(str(tmp_path)).get("brace")
        out = skill.render(x="hello {system_override} world {{escaped}}")
        assert "{" not in out
        assert "}" not in out
        assert "hello" in out and "world" in out
        # The literal content (sans braces) is preserved:
        assert "system_override" in out
        assert "escaped" in out


# ---------------------------------------------------------------------------
# M10 — multi-line frontmatter values (block scalar)
# ---------------------------------------------------------------------------


class TestBlockScalarFrontmatter:
    def test_literal_block_scalar_preserves_newlines(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "name: blocky\n"
            "description: |\n"
            "  Line one of the description.\n"
            "  Line two with detail.\n"
            "  Line three.\n"
            "inputs: []\n"
            "---\n"
            "body"
        )
        (tmp_path / "blocky.md").write_text(content, encoding="utf-8")
        skill = SkillRegistry(str(tmp_path)).get("blocky")
        assert skill.description == (
            "Line one of the description.\n"
            "Line two with detail.\n"
            "Line three."
        )

    def test_folded_block_scalar_joins_with_space(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "name: folded\n"
            "description: >\n"
            "  one two\n"
            "  three four\n"
            "inputs: []\n"
            "---\n"
            "body"
        )
        (tmp_path / "folded.md").write_text(content, encoding="utf-8")
        skill = SkillRegistry(str(tmp_path)).get("folded")
        assert skill.description == "one two three four"

    def test_block_scalar_terminates_on_dedent(self, tmp_path: Path) -> None:
        """A less-indented sibling key ends the block, and is parsed normally."""
        content = (
            "---\n"
            "name: dedent\n"
            "description: |\n"
            "  line A\n"
            "  line B\n"
            "inputs: [topic]\n"
            "---\n"
            "body"
        )
        (tmp_path / "dedent.md").write_text(content, encoding="utf-8")
        skill = SkillRegistry(str(tmp_path)).get("dedent")
        assert skill.description == "line A\nline B"
        assert skill.inputs == ["topic"]


# ---------------------------------------------------------------------------
# M11 — skill version field
# ---------------------------------------------------------------------------


class TestSkillVersion:
    def test_version_defaults_when_absent(self, tmp_path: Path) -> None:
        write_skill(tmp_path, "s.md", name="vdefault")
        skill = SkillRegistry(str(tmp_path)).get("vdefault")
        assert skill.version == "1.0.0"

    def test_version_from_frontmatter(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "name: vset\n"
            "description: x\n"
            "inputs: []\n"
            "version: 2.3.1\n"
            "---\n"
            "body"
        )
        (tmp_path / "v.md").write_text(content, encoding="utf-8")
        skill = SkillRegistry(str(tmp_path)).get("vset")
        assert skill.version == "2.3.1"

    def test_invalid_version_charset_rejected(self, tmp_path: Path) -> None:
        content = (
            "---\n"
            "name: vbad\n"
            "description: x\n"
            "inputs: []\n"
            "version: has space\n"
            "---\n"
            "body"
        )
        (tmp_path / "v.md").write_text(content, encoding="utf-8")
        with pytest.warns(UserWarning, match="invalid skill version"):
            registry = SkillRegistry(str(tmp_path))
        assert registry.list() == []
