# Build log

Two lines per breakage: what I expected, what actually happened. Written as I go, not
tidied up afterwards.

---

## Picking the source

**Expected:** GitHub's `/events` feed would hand me a PR title and description, like the
HN and USGS feeds hand you their fields.

**Actual:** it hands you five keys and none of them describe the change:

 payload.pull_request = { id, number, url, base, head }

No title, no body, no diff URL. Every word the model eventually reads has to be fetched by
my own pipeline. This is the whole reason the source is defensible, there is nothing here
a regex could act on.

Also measured: `x-poll-interval: 60`, 60 req/hr anonymous, and only ~2 PullRequestEvents
per 100 events, with heavy overlap between consecutive polls.


