"""Load SKILL.md into a plain dict the app can use.

SKILL.md is the single source of truth for prompts and schemas,
so the app reads them from there instead of copying them into code.
"""

import json
import os

# Map the step headings in SKILL.md to short keys used by the app.
STEP_HEADINGS = {
    "extract": "Step 1: Extract",
    "generate": "Step 2: Generate",
    "validate": "Step 3: Validate and refine",
}


class SkillFormatError(Exception):
    """Raised when SKILL.md is missing a section, prompt block or schema block."""


def split_sections(lines, marker):
    """Split lines into {heading: body lines} at headings that start with marker.

    Lines inside fenced code blocks are skipped when looking for headings,
    so a '#' inside a prompt can never start a new section.
    """
    sections = {}
    current = None
    in_fence = False

    for line in lines:
        if line.strip().startswith("```"):
            in_fence = not in_fence

        if not in_fence and line.startswith(marker):
            current = line[len(marker):].strip()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)

    return sections


def get_section(sections, heading, where):
    """Return one section, or raise a clear error if it is missing."""
    if heading not in sections:
        raise SkillFormatError(f"Missing section '{heading}' in {where}.")
    return sections[heading]


def first_code_block(lines, where):
    """Return the text inside the first fenced code block in lines."""
    inside = False
    block = []

    for line in lines:
        if line.strip().startswith("```"):
            if inside:
                return "\n".join(block).strip()
            inside = True
            continue
        if inside:
            block.append(line)

    raise SkillFormatError(f"Missing fenced code block in {where}.")


def read_setting(lines, label, where):
    """Read a value from a line like '- Model tier: small'."""
    prefix = f"- {label}:"
    for line in lines:
        if line.strip().startswith(prefix):
            return line.strip()[len(prefix):].strip()
    raise SkillFormatError(f"Missing '{label}' line in {where}.")


def load_step(step_lines, heading):
    """Parse one step section into tier, max_tokens, prompt and schema."""
    tier = read_setting(step_lines, "Model tier", heading)
    max_tokens_text = read_setting(step_lines, "Max output tokens", heading)

    subsections = split_sections(step_lines, "### ")
    prompt_where = f"'{heading}' > Prompt"
    schema_where = f"'{heading}' > Schema"

    prompt = first_code_block(get_section(subsections, "Prompt", heading), prompt_where)
    schema_text = first_code_block(get_section(subsections, "Schema", heading), schema_where)

    if not prompt:
        raise SkillFormatError(f"Empty prompt block in {prompt_where}.")

    try:
        max_tokens = int(max_tokens_text)
    except ValueError:
        raise SkillFormatError(f"Max output tokens is not a whole number in '{heading}'.")

    try:
        schema = json.loads(schema_text)
    except json.JSONDecodeError as error:
        raise SkillFormatError(f"Schema in {schema_where} is not valid JSON: {error}")

    return {
        "tier": tier,
        "max_tokens": max_tokens,
        "prompt": prompt,
        "schema": schema,
    }


def load_skill(path):
    """Read SKILL.md and return role, rules and the three steps as a dict."""
    with open(path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    sections = split_sections(lines, "## ")
    where = os.path.basename(path)

    role = "\n".join(get_section(sections, "Role", where)).strip()
    rules = "\n".join(get_section(sections, "Rules", where)).strip()

    steps = {}
    for key, heading in STEP_HEADINGS.items():
        step_lines = get_section(sections, heading, where)
        steps[key] = load_step(step_lines, heading)

    return {"role": role, "rules": rules, "steps": steps}


def build_system_prompt(skill, step_name):
    """Join Role, Rules and the step's prompt, with one blank line between parts."""
    if step_name not in skill["steps"]:
        raise KeyError(f"Unknown step '{step_name}'. Expected one of: {', '.join(skill['steps'])}")

    parts = [skill["role"], skill["rules"], skill["steps"][step_name]["prompt"]]
    return "\n\n".join(parts)
