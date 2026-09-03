# Connect bootcamp

Throwaway. The point is to meet the eight things Connect can do before using them for
real on Evening 2–3.

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
task bootcamp -- 01-hello
```

Work through them in order. **Break each one on purpose** before moving on. The whole
value is in seeing what Connect does when things go wrong, because that is what Evening 3
will actually be like.

Log every surprise in `NOTES.md`. That file is the write-up.

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
