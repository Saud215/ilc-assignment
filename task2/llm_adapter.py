"""Thin LLM adapter.

All provider details (base URL, key variable, model IDs) live in config.json,
so switching provider means editing that file only, never this code.
Any provider with an OpenAI-compatible chat.completions endpoint works.
"""

import json
import os

from dotenv import load_dotenv
from openai import OpenAI

# Paths are relative to this file, so the app works from any working directory.
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
ENV_PATH = os.path.join(APP_DIR, ".env")


def load_config():
    """Read config.json from the folder this file is in."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_model_id(config, tier):
    """Look up the model ID for a tier ("small" or "main")."""
    models = config["models"]
    if tier not in models:
        raise ValueError(f"Unknown tier '{tier}'. Expected one of: {', '.join(models)}")

    model_id = models[tier]
    # Catch the placeholder early, instead of getting a confusing API error.
    if not model_id or model_id.startswith("PUT_"):
        raise ValueError(f"No model ID set for tier '{tier}'. Edit 'models' in config.json.")
    return model_id


def get_params(config, tier):
    """Extra request settings for a tier (for example thinking effort). Empty if none are set."""
    # "params" is optional in config.json, and so is each tier inside it.
    all_params = config.get("params") or {}
    params = all_params.get(tier) or {}
    if not isinstance(params, dict):
        raise ValueError(f"params for tier '{tier}' in config.json must be a JSON object.")
    return params


def get_api_key(config):
    """Read the API key from the environment variable named in config.json."""
    # .env is optional; a variable set in the shell also works.
    load_dotenv(ENV_PATH)
    key_name = config["provider"]["api_key_env"]
    api_key = os.getenv(key_name)
    if not api_key:
        # Name the variable, never the key itself.
        raise RuntimeError(f"Missing API key. Set {key_name} in .env or in your environment.")
    return api_key


def call_llm(tier, system_prompt, user_content, max_tokens):
    """Send one system and one user message and return the reply as a plain dict."""
    config = load_config()
    model_id = get_model_id(config, tier)
    params = get_params(config, tier)
    api_key = get_api_key(config)

    request = {
        "model": model_id,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
    }

    # On duplicate keys extra_body wins, so a clash would silently replace
    # a value the app sets (such as the step's max_tokens). Refuse it instead.
    for key in params:
        if key in request:
            raise ValueError(
                f"params for tier '{tier}' in config.json cannot set '{key}'; the app sets it."
            )

    # create() rejects keyword arguments it does not know, but extra_body is
    # merged into the request JSON as-is, so it works for known and unknown
    # parameters alike. With no params, nothing is added.
    if params:
        request["extra_body"] = params

    # 60 seconds instead of the openai default of 600, so one stuck request
    # cannot hold the page for many minutes.
    client = OpenAI(base_url=config["provider"]["base_url"], api_key=api_key, timeout=60)
    response = client.chat.completions.create(**request)

    # Some providers can return no text (e.g. blocked reply); use "" so callers get a string.
    text = response.choices[0].message.content or ""

    # Usage can be missing on some providers; report 0 rather than crash.
    in_tokens = 0
    out_tokens = 0
    total_tokens = 0
    if response.usage is not None:
        in_tokens = response.usage.prompt_tokens or 0
        out_tokens = response.usage.completion_tokens or 0
        # Total also counts hidden thinking tokens, which completion_tokens leaves out.
        total_tokens = response.usage.total_tokens or 0

    # "length" means the reply was cut off by max_tokens.
    finish_reason = response.choices[0].finish_reason or ""

    return {
        "text": text,
        "in_tokens": in_tokens,
        "out_tokens": out_tokens,
        "total_tokens": total_tokens,
        "finish_reason": finish_reason,
        "model": model_id,
    }
