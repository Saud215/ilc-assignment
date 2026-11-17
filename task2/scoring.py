"""Score the RIASEC questionnaire in code. No LLM, zero tokens."""

import json
import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS_PATH = os.path.join(APP_DIR, "questions.json")

# Fixed letter order. Also used to break ties, so the same answers
# always give the same top letters.
LETTERS = ["R", "I", "A", "S", "E", "C"]
MIN_ANSWER = 0
MAX_ANSWER = 4


def load_questions():
    """Read questions.json from the folder this file is in."""
    with open(QUESTIONS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def check_answers(answers, item_count):
    """Raise a clear ValueError if the answers list is not usable."""
    if not isinstance(answers, list):
        raise ValueError("Answers must be a list of whole numbers.")
    if len(answers) != item_count:
        raise ValueError(f"Expected {item_count} answers, got {len(answers)}.")

    for position, value in enumerate(answers, start=1):
        # bool is a subclass of int in Python, so reject it on purpose.
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Answer {position} must be a whole number, got {value!r}.")
        if value < MIN_ANSWER or value > MAX_ANSWER:
            raise ValueError(
                f"Answer {position} must be from {MIN_ANSWER} to {MAX_ANSWER}, got {value}."
            )


def tie_break_key(letter, scores):
    """Sort key: highest score first, then the fixed R, I, A, S, E, C order."""
    return (-scores[letter], LETTERS.index(letter))


def score_answers(answers):
    """Add up answers per letter and return {"sc": {...}, "top": "..."}."""
    items = load_questions()["items"]
    check_answers(answers, len(items))

    scores = {}
    for letter in LETTERS:
        scores[letter] = 0

    # Answers are in item order, so answer i belongs to item i.
    for item, value in zip(items, answers):
        scores[item["type"]] += value

    ranked = sorted(LETTERS, key=lambda letter: tie_break_key(letter, scores))
    top = "".join(ranked[:3])

    return {"sc": scores, "top": top}
