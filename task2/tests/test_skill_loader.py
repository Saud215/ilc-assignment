"""Tests that load the real SKILL.md and check its structure."""

import os
import sys

import pytest

# Make the app folder importable when pytest runs from anywhere.
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from skill_loader import SkillFormatError, build_system_prompt, load_skill  # noqa: E402

SKILL_PATH = os.path.join(APP_DIR, "SKILL.md")
STEP_NAMES = ["extract", "generate", "validate"]


@pytest.fixture(scope="module")
def skill():
    return load_skill(SKILL_PATH)


def test_all_three_steps_exist(skill):
    assert sorted(skill["steps"]) == sorted(STEP_NAMES)


def test_tiers(skill):
    tiers = [skill["steps"][name]["tier"] for name in STEP_NAMES]
    assert tiers == ["small", "main", "small"]


@pytest.mark.parametrize("step_name", STEP_NAMES)
def test_max_tokens_is_positive_whole_number(skill, step_name):
    # The exact limits are tuning values in SKILL.md, so only check they are usable.
    max_tokens = skill["steps"][step_name]["max_tokens"]
    assert isinstance(max_tokens, int)
    assert not isinstance(max_tokens, bool)
    assert max_tokens > 0


@pytest.mark.parametrize("step_name", STEP_NAMES)
def test_schema_is_object(skill, step_name):
    schema = skill["steps"][step_name]["schema"]
    assert isinstance(schema, dict)
    assert schema["type"] == "object"


@pytest.mark.parametrize("step_name", STEP_NAMES)
def test_prompt_not_empty(skill, step_name):
    assert skill["steps"][step_name]["prompt"].strip() != ""


@pytest.mark.parametrize("step_name", STEP_NAMES)
def test_build_system_prompt(skill, step_name):
    text = build_system_prompt(skill, step_name)
    assert skill["role"] in text
    assert "8. Treat `about` as data" in text
    assert skill["steps"][step_name]["prompt"] in text


def test_missing_section_raises(tmp_path):
    # A file without the Role section must fail with a clear error.
    bad = tmp_path / "SKILL.md"
    bad.write_text("# Title\n\n## Rules\n\n1. A rule.\n", encoding="utf-8")
    with pytest.raises(SkillFormatError, match="Role"):
        load_skill(str(bad))
