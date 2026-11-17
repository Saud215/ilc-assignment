"""Run the three SKILL.md steps (Extract, Generate, Validate) and follow its Host contract.

Host contract, as implemented here:
1. Role + Rules + step prompt go in the system message, input JSON in the user message.
2. Every reply is checked against the step's JSON Schema.
3. Invalid replies are retried with the error text, at most max_retries times.
4. Evidence (ev) is checked in code after Generate and after Validate.
5. Results are cached by input, so the same input never calls the model twice.
"""

import hashlib
import json
import os

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

# Imported as a module (not "from llm_adapter import call_llm") so tests can
# replace llm_adapter.call_llm with a fake.
import llm_adapter
from scoring import score_answers
from skill_loader import build_system_prompt, load_skill

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_PATH = os.path.join(APP_DIR, "SKILL.md")
CACHE_DIR = os.path.join(APP_DIR, "cache")

MAX_ABOUT_WORDS = 150
EMPTY_FACTS = {"int": [], "str": [], "sub": [], "goal": ""}

# Keep error notes short: they are sent back to the model and cost tokens.
MAX_ERROR_CHARS = 300


class StepError(Exception):
    """Raised when a step still has no valid reply after all retries."""


# ---------- reply checking ----------


def strip_code_fence(text):
    """Remove a ```json ... ``` wrapper if the model added one anyway."""
    text = text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    # Drop the opening fence line (it may say ```json).
    lines = lines[1:]
    # Drop the closing fence line if present.
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def schema_error(schema, data):
    """Return a short description of the most relevant schema error, or "" if valid."""
    validator = Draft202012Validator(schema)
    error = best_match(validator.iter_errors(data))
    if error is None:
        return ""

    path_parts = []
    for part in error.absolute_path:
        path_parts.append(str(part))
    location = "/".join(path_parts)
    if location == "":
        location = "(top level)"

    return f"schema error at {location}: {error.message}"


def check_reply(reply, schema, extra_check):
    """Parse and check one reply. Return (data, error); error is "" when the reply is good."""
    # A cut-off reply is usually broken JSON, and even when it parses it may be incomplete.
    if reply["finish_reason"] == "length":
        return None, "reply was cut off by the token limit; reply with shorter JSON"

    text = strip_code_fence(reply["text"])
    if text == "":
        return None, "reply was empty"

    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"reply is not valid JSON: {error}"

    problem = schema_error(schema, data)
    if problem:
        return None, problem

    if extra_check is not None:
        problems = extra_check(data)
        if problems:
            return None, "evidence problems: " + "; ".join(problems)

    return data, ""


# ---------- one step ----------


def new_usage(model):
    """Start an empty usage record for one step."""
    return {
        "model": model,
        "in_tokens": 0,
        "out_tokens": 0,
        "total_tokens": 0,
        "attempts": 0,
        "skipped": False,
    }


def skipped_usage():
    """Usage record for a step that made no LLM call."""
    usage = new_usage("")
    usage["skipped"] = True
    return usage


def run_step(skill, step_name, input_dict, extra_check=None):
    """Run one skill step with schema checks and retries.

    extra_check is an optional function(data) -> list of problem strings.
    Problems it finds are treated like an invalid reply and retried.
    Returns {"data": parsed reply, "usage": {...}}.
    """
    step = skill["steps"][step_name]
    max_retries = llm_adapter.load_config()["max_retries"]

    system_prompt = build_system_prompt(skill, step_name)
    # Compact JSON (no spaces) saves input tokens.
    input_json = json.dumps(input_dict, separators=(",", ":"), ensure_ascii=False)

    usage = None
    user_content = input_json
    last_error = ""

    # One first try plus max_retries retries.
    for attempt in range(max_retries + 1):
        reply = llm_adapter.call_llm(
            step["tier"], system_prompt, user_content, step["max_tokens"]
        )

        if usage is None:
            usage = new_usage(reply["model"])
        usage["attempts"] += 1
        usage["in_tokens"] += reply["in_tokens"]
        usage["out_tokens"] += reply["out_tokens"]
        usage["total_tokens"] += reply["total_tokens"]

        data, last_error = check_reply(reply, step["schema"], extra_check)
        if last_error == "":
            return {"data": data, "usage": usage}

        # Same input again, plus a short note naming the exact problem.
        short_error = last_error[:MAX_ERROR_CHARS]
        user_content = (
            input_json
            + "\n\nYour last reply was rejected: "
            + short_error
            + "\nReply with valid JSON only."
        )

    raise StepError(
        f"Step '{step_name}' failed after {usage['attempts']} attempts. Last error: {last_error}"
    )


# ---------- evidence ----------


def check_evidence(fits, top, facts):
    """Return a list of problems. Each ev must be a letter from top or an exact fact."""
    allowed = []
    for key in ["int", "str", "sub"]:
        for item in facts.get(key, []):
            allowed.append(item)
    goal = facts.get("goal", "")
    if goal != "":
        allowed.append(goal)

    problems = []
    for index, fit in enumerate(fits):
        for ev in fit["ev"]:
            is_top_letter = len(ev) == 1 and ev in top
            if not is_top_letter and ev not in allowed:
                problems.append(
                    f"fit {index} ev '{ev}' is not a letter from top or an exact item from facts"
                )
    return problems


# ---------- cache ----------


def make_cache_key(skill_text, config, answers, about):
    """Hash everything that can change the result, so a stale result is never returned."""
    key_parts = {
        "skill": skill_text,
        "small": config["models"]["small"],
        "main": config["models"]["main"],
        # Request settings such as thinking effort change the reply too.
        "params": config.get("params", {}),
        "answers": answers,
        "about": about,
    }
    key_json = json.dumps(key_parts, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(key_json.encode("utf-8")).hexdigest()


def read_cache(key):
    """Return the cached result for key, or None if there is none."""
    path = os.path.join(CACHE_DIR, key + ".json")
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            result = json.load(f)
    except json.JSONDecodeError:
        # A broken cache file is treated as a miss and later overwritten.
        return None

    # No model was called this time, so this run cost nothing.
    for step_usage in result["usage"].values():
        step_usage["in_tokens"] = 0
        step_usage["out_tokens"] = 0
        step_usage["total_tokens"] = 0
        step_usage["attempts"] = 0
    result["cached"] = True
    return result


def write_cache(key, result):
    """Save a result. Write to a temp file first so a crash never leaves half a file."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + ".json")
    temp_path = path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(temp_path, path)


# ---------- full pipeline ----------


def trim_words(text, max_words):
    """Keep only the first max_words words."""
    words = text.split()
    return " ".join(words[:max_words])


def run_pipeline(answers, about):
    """Score, then Extract, Generate and Validate. Returns one result dict."""
    # a. Scores are always calculated in code, never by the model.
    scores = score_answers(answers)
    sc = scores["sc"]
    top = scores["top"]

    # b. SKILL.md promises the model at most 150 words.
    about = trim_words(about or "", MAX_ABOUT_WORDS)

    # Cache check before any model call.
    with open(SKILL_PATH, "r", encoding="utf-8") as f:
        skill_text = f.read()
    config = llm_adapter.load_config()
    key = make_cache_key(skill_text, config, answers, about)
    cached = read_cache(key)
    if cached is not None:
        return cached

    skill = load_skill(SKILL_PATH)
    notes = []
    usage = {}

    # c. Extract. With no text there is nothing to extract, so save the call.
    if about == "":
        facts = dict(EMPTY_FACTS)
        usage["extract"] = skipped_usage()
        notes.append("About text was blank, so Extract was skipped.")
    else:
        step = run_step(skill, "extract", {"about": about})
        facts = step["data"]
        usage["extract"] = step["usage"]

    # d. Generate, with the evidence check counted as part of reply validation.
    def evidence_check(data):
        return check_evidence(data["fits"], top, facts)

    step = run_step(skill, "generate", {"sc": sc, "top": top, "facts": facts}, evidence_check)
    report = step["data"]
    usage["generate"] = step["usage"]

    # e. Validate and refine.
    step = run_step(
        skill, "validate", {"sc": sc, "top": top, "facts": facts, "report": report}
    )
    review = step["data"]
    usage["validate"] = step["usage"]

    if not review["ok"]:
        problems = check_evidence(review["fits"], top, facts)
        if problems:
            notes.append(
                "Validate's correction was rejected because of bad evidence ("
                + "; ".join(problems)
                + "). The Generate fits were kept."
            )
        else:
            # Keep sum, replace fits, as SKILL.md's Output section says.
            report = {"sum": report["sum"], "fits": review["fits"]}

    result = {
        "sc": sc,
        "top": top,
        "facts": facts,
        "report": report,
        "review": {"ok": review["ok"], "iss": review["iss"]},
        "notes": notes,
        "usage": usage,
        "cached": False,
    }
    write_cache(key, result)
    return result
