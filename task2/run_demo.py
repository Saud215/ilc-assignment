# Manual demo of the full pipeline with one fixed sample student.
# The first run makes up to 3 LLM calls (more only on retries).
# A repeat run with the same input makes none, because the result is cached.
# It writes one file under cache/.
# Run: .venv/bin/python run_demo.py

import json
import os

import llm_adapter
from pipeline import run_pipeline

# The sample student lives in a data file, so the web app can use the same one.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_PATH = os.path.join(APP_DIR, "sample_student.json")


def load_sample():
    """Read the fixed sample student (30 answers and an about text)."""
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def show(title, value):
    print(f"== {title} ==")
    print(json.dumps(value, indent=2, ensure_ascii=False))
    print()


def show_params():
    """Print the extra request settings (for example thinking effort) for each tier."""
    print("== Params per tier (config.json) ==")
    config = llm_adapter.load_config()
    for tier in config["models"]:
        params = llm_adapter.get_params(config, tier)
        print(f"{tier:<6}{json.dumps(params)}")
    print()


def thinking_tokens(step):
    """Hidden thinking tokens: counted in total, but not in in or out."""
    think = step["total_tokens"] - step["in_tokens"] - step["out_tokens"]
    # A provider that reports no total would otherwise show a negative number.
    if think < 0:
        think = 0
    return think


def show_usage_table(usage):
    print("== Tokens per step ==")
    header = (
        f"{'step':<10}{'model':<26}{'in':>7}{'out':>7}{'think':>7}"
        f"{'total':>8}{'attempts':>10}"
    )
    print(header)
    print("-" * len(header))

    grand = {"in_tokens": 0, "out_tokens": 0, "total_tokens": 0, "attempts": 0}
    grand_think = 0
    for step_name in ["extract", "generate", "validate"]:
        step = usage[step_name]
        model = step["model"]
        if step["skipped"]:
            model = "(skipped)"
        think = thinking_tokens(step)
        print(
            f"{step_name:<10}{model:<26}{step['in_tokens']:>7}{step['out_tokens']:>7}"
            f"{think:>7}{step['total_tokens']:>8}{step['attempts']:>10}"
        )
        for key in grand:
            grand[key] += step[key]
        grand_think += think

    print("-" * len(header))
    print(
        f"{'total':<10}{'':<26}{grand['in_tokens']:>7}{grand['out_tokens']:>7}"
        f"{grand_think:>7}{grand['total_tokens']:>8}{grand['attempts']:>10}"
    )
    print()


sample = load_sample()
result = run_pipeline(sample["answers"], sample["about"])

show("Scores (sc)", result["sc"])
print(f"== Top ==\n{result['top']}\n")
show("Facts", result["facts"])
show("Report", result["report"])
show("Review", result["review"])
show("Notes", result["notes"])
show_params()
show_usage_table(result["usage"])
print(f"From cache: {result['cached']}")
