"""Tests for scoring.py. No LLM involved."""

import os
import sys

import pytest

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

from scoring import load_questions, score_answers  # noqa: E402

ITEM_TYPES = [item["type"] for item in load_questions()["items"]]


def answers_from_type_values(values_by_type):
    """Build an answer list in item order from per-letter value lists."""
    # Copy the lists so we can pop from them.
    remaining = {}
    for letter, values in values_by_type.items():
        remaining[letter] = list(values)

    answers = []
    for letter in ITEM_TYPES:
        answers.append(remaining[letter].pop(0))
    return answers


def test_there_are_30_items():
    assert len(ITEM_TYPES) == 30


def test_all_zeros():
    result = score_answers([0] * 30)
    assert result["sc"] == {"R": 0, "I": 0, "A": 0, "S": 0, "E": 0, "C": 0}


def test_all_fours():
    result = score_answers([4] * 30)
    assert result["sc"] == {"R": 20, "I": 20, "A": 20, "S": 20, "E": 20, "C": 20}


def test_hand_made_answers():
    answers = answers_from_type_values({
        "R": [0, 1, 2, 3, 4],  # 10
        "I": [4, 4, 4, 4, 3],  # 19
        "A": [3, 3, 3, 3, 3],  # 15
        "S": [2, 2, 2, 2, 1],  # 9
        "E": [0, 0, 0, 0, 0],  # 0
        "C": [1, 1, 1, 1, 1],  # 5
    })
    result = score_answers(answers)
    assert result["sc"] == {"R": 10, "I": 19, "A": 15, "S": 9, "E": 0, "C": 5}
    assert result["top"] == "IAR"


def test_all_tied_uses_fixed_order():
    assert score_answers([2] * 30)["top"] == "RIA"


def test_partial_tie_uses_fixed_order():
    answers = answers_from_type_values({
        "R": [0] * 5,
        "I": [4] * 5,  # 20
        "A": [0] * 5,
        "S": [4] * 5,  # 20, ties with I
        "E": [1] * 5,  # 5
        "C": [1] * 5,  # 5, ties with E
    })
    assert score_answers(answers)["top"] == "ISE"


@pytest.mark.parametrize("count", [0, 29, 31])
def test_wrong_length_raises(count):
    with pytest.raises(ValueError, match="Expected 30 answers"):
        score_answers([2] * count)


@pytest.mark.parametrize("bad_value", [-1, 5, 2.5, "3", True, None])
def test_bad_value_raises(bad_value):
    answers = [2] * 30
    answers[7] = bad_value
    with pytest.raises(ValueError, match="Answer 8"):
        score_answers(answers)
