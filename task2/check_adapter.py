# Manual check of llm_adapter.py.
# Makes 2 small LLM calls (one per tier) and writes no files.
# Run: .venv/bin/python check_adapter.py

from llm_adapter import call_llm

for tier in ["small", "main"]:
    result = call_llm(
        tier=tier,
        system_prompt="Reply with the single word: ok",
        user_content="test",
        max_tokens=20,
    )
    print(f"tier:       {tier}")
    print(f"model:      {result['model']}")
    print(f"reply:      {result['text']!r}")
    print(f"in_tokens:  {result['in_tokens']}")
    print(f"out_tokens: {result['out_tokens']}")
    print()
