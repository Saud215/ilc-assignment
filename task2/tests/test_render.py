"""Tests for render.py. Pure functions, no Gradio and no LLM."""

import os
import sys

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP_DIR)

import render  # noqa: E402

FIT = {
    "t": "Lab Technician",
    "why": "You like science.",
    "ev": ["I", "biology"],
    "nxt": "Visit a lab.",
}


def step_usage(model, in_tokens, out_tokens, total_tokens, attempts=1, skipped=False):
    return {
        "model": model,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "total_tokens": total_tokens,
        "attempts": attempts,
        "skipped": skipped,
    }


def test_career_card_escapes_model_text():
    fit = {
        "t": "<script>alert(1)</script>",
        "why": "Fun & <b>bold</b>",
        "ev": ['<img src=x onerror="x">'],
        "nxt": "Try \"this\"",
    }
    card = render.career_card_html(fit, 1)

    assert "<script>" not in card
    assert "<b>bold</b>" not in card
    assert "<img" not in card
    assert "&lt;script&gt;" in card
    assert "Fun &amp; &lt;b&gt;bold&lt;/b&gt;" in card


def test_three_fits_give_three_cards():
    page = render.cards_html([FIT, FIT, FIT])
    assert page.count('class="career-card"') == 3


def test_letter_evidence_shows_full_type_name():
    card = render.career_card_html(FIT, 1)
    assert ">Investigative</span>" in card
    assert ">I</span>" not in card
    # A fact is shown as written.
    assert ">biology</span>" in card


def test_token_rows_calculate_think():
    usage = {
        "extract": step_usage("small-model", 120, 40, 160),
        "generate": step_usage("main-model", 355, 212, 2356),
        "validate": step_usage("small-model", 500, 30, 530, attempts=2),
    }
    rows = render.token_rows(usage)

    assert rows[0] == ["Extract", "small-model", 120, 40, 0, 160, 1]
    assert rows[1] == ["Generate", "main-model", 355, 212, 1789, 2356, 1]
    assert rows[3] == ["Total", "", 975, 282, 1789, 3046, 4]


def test_token_rows_show_skipped_step_and_never_negative_think():
    usage = {
        "extract": step_usage("", 0, 0, 0, attempts=0, skipped=True),
        # A provider that reports no total must not give a negative think count.
        "generate": step_usage("main-model", 300, 200, 0),
        "validate": step_usage("small-model", 500, 30, 530),
    }
    rows = render.token_rows(usage)

    assert rows[0][1] == "skipped"
    assert rows[1][4] == 0


def test_review_badge_states():
    assert "Checked, no problems found" in render.review_html({"ok": True, "iss": []})

    review = {"ok": False, "iss": [{"i": 1, "p": "Next step is <vague>."}]}
    page = render.review_html(review)
    assert "Checked and corrected" in page
    assert "Career 2: Next step is &lt;vague&gt;." in page


def test_scores_use_full_names_and_mark_top_three():
    sc = {"R": 6, "I": 17, "A": 14, "S": 12, "E": 5, "C": 8}
    rows = render.score_rows(sc, "IAS")

    assert rows[0] == ["Realistic", 6, ""]
    assert rows[1] == ["Investigative", 17, "Top 1"]
    assert rows[3] == ["Social", 12, "Top 3"]
    assert "17 / 20" in render.scores_html(sc, "IAS")
