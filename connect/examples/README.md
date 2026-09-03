# Connect examples

Small standalone pipelines, one per idea, covering the eight Connect features
`../ingest.yaml` is built from. Each one runs on its own and prints to stdout.

They exist because the failure modes are easier to see in isolation than in the real
pipeline, where a filter drops most of the traffic before you get to look at it.

## ⚠️ Before you start: get a GitHub token

Anonymous GitHub allows **60 requests per hour**. A misconfigured pipeline burns that in
seconds, and then everything 403s for the rest of the hour.

Make a classic PAT with **no scopes ticked** (this only reads public data), put it in
`.env` as `GITHUB_TOKEN`, and you get 5,000/hr instead.

Check what you have left at any time:

```bash
curl -s -H "User-Agent: x" https://api.github.com/rate_limit | python3 -m json.tool
```

Run one with:

```bash
task example -- 01-hello
```

Run them in order. Each file has notes marked `BREAK IT` suggesting a change to make on
purpose, so you can watch the failure rather than read about it. Several of those are
mistakes that cost real time in `ingest.yaml`.

## The eight things

| Thing | What it is |
|---|---|
| `input` | Where messages come from |
| `pipeline.processors` | An ordered list of steps. Top to bottom. |
| `output` | Where they go |
| `mapping` | Bloblang. The little language for reshaping a message |
| `branch` | Go fetch something, graft it on **without** clobbering the message |
| `cache_resources` | Remember what we have seen (used by `dedupe`) |
| `rate_limit_resources` | Do not exceed N calls per interval |
| error handling | `retries`, `.catch()`, routing failures somewhere |
