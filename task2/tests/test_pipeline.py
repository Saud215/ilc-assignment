"""Tests for pipeline.py. call_llm is replaced with a fake, so no test uses a network."""

import copy
import json
import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

import llm_adapter  # noqa: E402
import pipeline  # noqa: E402
from skill_loader import load_skill  # noqa: E402

ANSWERS = [2] * 30  # all tied, so top is "RIA"
ABOUT = "I love biology and drawing. I am good at explaining things to friends."

FACTS = {"int": ["biology", "drawing"], "str": ["explaining things"], "sub": ["biology"], "goal": ""}

REPORT = {
    "sum": "Your interests point to hands-on and science work. Art also matters to you.",
    "fits": [
        {"t": "Lab Technician", "why": "You like science and practical work.",
         "ev": ["I", "biology"], "nxt": "Visit a school lab and ask a teacher about lab jobs."},
        {"t": "Medical Illustrator", "why": "It mixes biology with drawing.",
         "ev": ["A", "drawing", "biology"], "nxt": "Draw one labelled diagram from your biology book."},
        {"t": "Science Teacher", "why": "You explain things well and like biology.",
         "ev": ["explaining things", "biology"], "nxt": "Explain one biology topic to a friend."},
    ],
}

CORRECTED_FITS = [
    {"t": "Field Biologist", "why": "It joins biology with outdoor, hands-on work.",
     "ev": ["R", "biology"], "nxt": "Join a local nature walk and keep notes."},
    REPORT["fits"][1],
    REPORT["fits"][2],
]

REVIEW_OK = {"ok": True, "iss": [], "fits": []}
REVIEW_FIXED = {"ok": False, "iss": [{"i": 0, "p": "Too close to fit 2."}], "fits": CORRECTED_FITS}


def as_text(data):
    return json.dumps(data)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """Install a fake call_llm and a temporary cache folder.

    Tests put replies in fake["replies"]; every call is recorded in fake["calls"].
    """
    state = {"replies": [], "calls": []}

    def fake_call_llm(tier, system_prompt, user_content, max_tokens):
        state["calls"].append({"tier": tier, "user": user_content, "max_tokens": max_tokens})
        if not state["replies"]:
            raise AssertionError("call_llm was called more times than expected")
        reply = state["replies"].pop(0)

        # A reply can be plain text, or a dict to set finish_reason too.
        finish_reason = "stop"
        if isinstance(reply, dict):
            finish_reason = reply["finish_reason"]
            reply = reply["text"]

        return {
            "text": reply,
            "in_tokens": 10,
            "out_tokens": 5,
            "total_tokens": 20,
            "finish_reason": finish_reason,
            "model": "fake-" + tier,
        }

    monkeypatch.setattr(llm_adapter, "call_llm", fake_call_llm)
    monkeypatch.setattr(pipeline, "CACHE_DIR", str(tmp_path / "cache"))
    return state


@pytest.fixture(scope="module")
def skill():
    return load_skill(pipeline.SKILL_PATH)


# ---------- full pipeline ----------


def test_clean_run(fake, skill):
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_OK)]
    result = pipeline.run_pipeline(ANSWERS, ABOUT)

    # Limits are tuning values in SKILL.md, so compare with what is loaded from it.
    expected_max_tokens = []
    for name in ["extract", "generate", "validate"]:
        expected_max_tokens.append(skill["steps"][name]["max_tokens"])

    assert result["top"] == "RIA"
    assert result["facts"] == FACTS
    assert result["report"] == REPORT
    assert len(result["report"]["fits"]) == 3
    assert result["review"] == {"ok": True, "iss": []}
    assert result["notes"] == []
    assert result["cached"] is False
    assert [call["tier"] for call in fake["calls"]] == ["small", "main", "small"]
    assert [call["max_tokens"] for call in fake["calls"]] == expected_max_tokens
    for name in ["extract", "generate", "validate"]:
        assert result["usage"][name]["attempts"] == 1
        assert result["usage"][name]["total_tokens"] == 20


def test_user_message_is_compact_json(fake):
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_OK)]
    pipeline.run_pipeline(ANSWERS, ABOUT)
    first_user_message = fake["calls"][0]["user"]
    assert first_user_message == json.dumps({"about": ABOUT}, separators=(",", ":"))


def test_invented_evidence_triggers_retry(fake):
    bad_report = json.loads(as_text(REPORT))
    bad_report["fits"][0]["ev"] = ["football"]
    fake["replies"] = [as_text(FACTS), as_text(bad_report), as_text(REPORT), as_text(REVIEW_OK)]

    result = pipeline.run_pipeline(ANSWERS, ABOUT)

    assert result["usage"]["generate"]["attempts"] == 2
    assert result["usage"]["generate"]["total_tokens"] == 40
    assert "football" in fake["calls"][2]["user"]
    assert result["report"] == REPORT


def test_validate_replaces_fits_and_keeps_sum(fake):
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_FIXED)]
    result = pipeline.run_pipeline(ANSWERS, ABOUT)

    assert result["report"]["sum"] == REPORT["sum"]
    assert result["report"]["fits"] == CORRECTED_FITS
    assert result["review"] == {"ok": False, "iss": REVIEW_FIXED["iss"]}
    assert result["notes"] == []


def test_bad_correction_is_rejected(fake):
    bad_review = json.loads(as_text(REVIEW_FIXED))
    bad_review["fits"][0]["ev"] = ["chess club"]
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(bad_review)]

    result = pipeline.run_pipeline(ANSWERS, ABOUT)

    assert result["report"] == REPORT
    assert len(result["notes"]) == 1
    assert "rejected" in result["notes"][0]


def test_blank_about_skips_extract(fake):
    letters_only = json.loads(as_text(REPORT))
    for fit in letters_only["fits"]:
        fit["ev"] = ["R"]
    fake["replies"] = [as_text(letters_only), as_text(REVIEW_OK)]

    result = pipeline.run_pipeline(ANSWERS, "   ")

    assert [call["tier"] for call in fake["calls"]] == ["main", "small"]
    assert result["facts"] == {"int": [], "str": [], "sub": [], "goal": ""}
    extract_usage = result["usage"]["extract"]
    assert extract_usage["skipped"] is True
    assert extract_usage["attempts"] == 0
    assert extract_usage["total_tokens"] == 0


def test_about_is_trimmed_to_150_words(fake):
    long_about = " ".join(["word"] * 200)
    fake["replies"] = [as_text({"int": [], "str": [], "sub": [], "goal": ""}),
                    as_text(REPORT).replace('"biology"', '"I"')
                    .replace('"drawing"', '"A"').replace('"explaining things"', '"R"'),
                    as_text(REVIEW_OK)]
    pipeline.run_pipeline(ANSWERS, long_about)
    sent = json.loads(fake["calls"][0]["user"])
    assert len(sent["about"].split()) == 150


def test_second_run_uses_cache(fake):
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_OK)]
    first = pipeline.run_pipeline(ANSWERS, ABOUT)
    calls_after_first = len(fake["calls"])

    second = pipeline.run_pipeline(ANSWERS, ABOUT)

    assert len(fake["calls"]) == calls_after_first
    assert second["cached"] is True
    assert second["report"] == first["report"]
    for step_usage in second["usage"].values():
        assert step_usage["in_tokens"] == 0
        assert step_usage["out_tokens"] == 0
        assert step_usage["total_tokens"] == 0


def test_cache_key_changes_when_params_change():
    config = llm_adapter.load_config()
    changed = copy.deepcopy(config)
    changed["params"] = {"small": {}, "main": {"reasoning_effort": "high"}}
    same = copy.deepcopy(config)

    key = pipeline.make_cache_key("skill text", config, ANSWERS, ABOUT)

    assert pipeline.make_cache_key("skill text", changed, ANSWERS, ABOUT) != key
    assert pipeline.make_cache_key("skill text", same, ANSWERS, ABOUT) == key


def test_changed_params_do_not_return_old_cached_result(fake, monkeypatch):
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_OK)]
    pipeline.run_pipeline(ANSWERS, ABOUT)

    # Same input, but a different thinking setting in config.json.
    changed = copy.deepcopy(llm_adapter.load_config())
    changed["params"] = {"small": {}, "main": {"reasoning_effort": "high"}}
    monkeypatch.setattr(llm_adapter, "load_config", lambda: changed)
    fake["replies"] = [as_text(FACTS), as_text(REPORT), as_text(REVIEW_OK)]

    result = pipeline.run_pipeline(ANSWERS, ABOUT)

    assert result["cached"] is False
    assert len(fake["calls"]) == 6


# ---------- run_step on its own ----------


def test_invalid_json_then_valid(fake, skill):
    fake["replies"] = ["not json at all", as_text(FACTS)]
    step = pipeline.run_step(skill, "extract", {"about": ABOUT})

    assert step["data"] == FACTS
    assert step["usage"]["attempts"] == 2
    assert "not valid JSON" in fake["calls"][1]["user"]
    assert "Reply with valid JSON only" in fake["calls"][1]["user"]


def test_always_invalid_raises_step_error(fake, skill):
    max_retries = llm_adapter.load_config()["max_retries"]
    fake["replies"] = ["{bad"] * (max_retries + 1)

    with pytest.raises(pipeline.StepError, match="extract"):
        pipeline.run_step(skill, "extract", {"about": ABOUT})
    assert len(fake["calls"]) == max_retries + 1


def test_schema_error_triggers_retry(fake, skill):
    too_many_keys = dict(FACTS)
    too_many_keys["extra"] = "x"
    fake["replies"] = [as_text(too_many_keys), as_text(FACTS)]

    step = pipeline.run_step(skill, "extract", {"about": ABOUT})

    assert step["usage"]["attempts"] == 2
    assert "schema error" in fake["calls"][1]["user"]


def test_cut_off_reply_triggers_retry(fake, skill):
    fake["replies"] = [{"text": as_text(FACTS), "finish_reason": "length"}, as_text(FACTS)]
    step = pipeline.run_step(skill, "extract", {"about": ABOUT})

    assert step["usage"]["attempts"] == 2
    assert "cut off" in fake["calls"][1]["user"]


def test_code_fence_is_stripped(fake, skill):
    fake["replies"] = ["```json\n" + as_text(FACTS) + "\n```"]
    step = pipeline.run_step(skill, "extract", {"about": ABOUT})
    assert step["data"] == FACTS
    assert step["usage"]["attempts"] == 1


# ---------- check_evidence ----------


def test_check_evidence():
    facts = {"int": ["biology"], "str": [], "sub": [], "goal": "become a vet"}
    fits = [{"ev": ["I", "biology", "become a vet"]}, {"ev": ["E", "Biology", "IA"]}]

    problems = pipeline.check_evidence(fits, "IAS", facts)

    assert len(problems) == 3
    assert "fit 1" in problems[0]


def test_empty_goal_is_not_evidence():
    facts = {"int": [], "str": [], "sub": [], "goal": ""}
    assert pipeline.check_evidence([{"ev": [""]}], "IAS", facts) != []
