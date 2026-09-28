---
name: run-evals
description: Run the factory golden and broken fixtures. Base is sdd/factory, never main.
disable-model-invocation: true
---

# Run evals

`main` is the demo. Do not check it out. These fixtures check the factory, and the good pull request base is `sdd/factory`.

Run `python3 evals/factory/run.py` or `task run-evals`. A good folder must pass. Each broken folder must fail with its expected error.

Validate: `python3 evals/factory/run.py`

Next: factory-status
