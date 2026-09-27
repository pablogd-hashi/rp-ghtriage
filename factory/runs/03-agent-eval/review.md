# 03 agent eval

Executed in the Cursor session on 2026-09-27. `cursor-agent` is not on PATH.

## Plan

`triage/tools.py`, `triage/policy.py`, `triage/agent.py`. `complete_with_tools` on Anthropic and Ollama, and `ScriptedToolLLM` for tests. Eval `--mode agent --repeat N` prints workflow, workflow+floor, agent, floor+agent.

The scripted agent proposes the floor label so the table measures the loop, the budget of 3, and label flips. It is not a hosted-model score. Draft rows stay with the worker because `unclear` is not offered to the agent.

## Review

APPROVE. Tests cover allowlist, the fourth call, tool failure, and a blocked downgrade. Gate still green.
