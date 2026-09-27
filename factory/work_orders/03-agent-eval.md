# Agent eval mode

## Goal

A plain tool loop the eval can run, with no new framework. Tools are read-only
and fixture-backed. Policy caps the loop and refuses a downgrade of `security`.

## Acceptance

- `triage/tools.py`: `read_file`, `list_changed_files`, `osv_lookup`. Each has a
  fake backed by the fixture record or `fixtures/tool_catalog.json`. Tests make
  no network calls.
- `triage/policy.py`: allowlist of those three names, `MAX_TOOL_CALLS = 3`,
  a timeout, and a rule that cannot replace `security` with another category.
- `triage/agent.py`: one loop. Returns a trace. Stops on tool failure with
  `status=failed` and does not invent a label.
- `complete_with_tools` on `AnthropicLLM`, and `ScriptedToolLLM` for tests.
- `python evals/run.py --mode agent --repeat N` prints four rows: `workflow`,
  `workflow+floor`, `agent`, `floor+agent`. Columns: accuracy, security recall,
  tool calls, latency, label flips across runs.
- The scripted agent row is labelled as scripted. It is not a claim about a
  hosted model. A hosted run is `LLM_PROVIDER=anthropic`.
- `python scripts/gate.py` exits 0.

## Likely files

- `triage/tools.py`
- `triage/policy.py`
- `triage/agent.py`
- `triage/llm.py`
- `evals/run.py`
- `fixtures/tool_catalog.json`
- `tests/test_agent.py`
