"""The fetch filter and the record shape. No network."""

from triage.github import account_events, is_bot, opened_pull_requests, project_record


def test_opened_pull_requests_drop_everything_else():
    events = [
        {"type": "PushEvent", "id": "1", "payload": {}, "actor": {"login": "a"}},
        {"type": "PullRequestEvent", "id": "2", "payload": {"action": "closed"}, "actor": {"login": "a"}},
        {"type": "PullRequestEvent", "id": "3", "payload": {"action": "opened"}, "actor": {"login": "dependabot[bot]"}},
        {"type": "PullRequestEvent", "id": "4", "payload": {"action": "opened"}, "actor": {"login": "someone"}},
        "not an event",
    ]
    kept = opened_pull_requests(events)
    assert [event["id"] for event in kept] == ["4"]
    assert is_bot("renovate-bot")
    assert not is_bot("someone")


def test_account_events_lists_every_dropped_pull_request():
    events = [
        {"type": "PushEvent", "id": "1", "repo": {"name": "acme/api"}, "payload": {}, "actor": {"login": "a"}},
        {"type": "PullRequestEvent", "id": "2", "repo": {"name": "acme/api"}, "payload": {"action": "closed", "number": 8}, "actor": {"login": "a"}},
        {"type": "PullRequestEvent", "id": "3", "repo": {"name": "acme/api"}, "payload": {"action": "opened", "number": 9}, "actor": {"login": "dependabot[bot]"}},
        {"type": "PullRequestEvent", "id": "4", "repo": {"name": "acme/web"}, "payload": {"action": "opened", "number": 3}, "actor": {"login": "someone"}},
        "not an event",
    ]
    summary, kept = account_events(events)
    assert summary["events"] == 5
    assert summary["pull_requests"] == 3
    assert summary["not_pull_requests"] == 2
    assert summary["dropped_not_opened"] == 1
    assert summary["dropped_bots"] == 1
    assert summary["kept"] == 1
    assert [event["id"] for event in kept] == ["4"]
    assert [(card["number"], card["reason"]) for card in summary["dropped"]] == [(8, "not opened"), (9, "bot")]


def test_project_record_truncates_like_connect():
    event = {
        "id": "99",
        "created_at": "2026-09-28T00:00:00Z",
        "repo": {"name": "acme/api"},
        "actor": {"login": "someone"},
        "payload": {"number": 7, "pull_request": {"url": "https://api.github.com/repos/acme/api/pulls/7"}},
    }
    pr = {
        "url": "https://api.github.com/repos/acme/api/pulls/7",
        "html_url": "https://github.com/acme/api/pull/7",
        "number": 7,
        "user": {"login": "someone"},
        "draft": False,
        "title": "fix auth",
        "body": "x" * 2500,
        "additions": 1,
        "deletions": 0,
        "changed_files": 9,
    }
    files = [
        {"filename": f"f{i}.py", "status": "modified", "additions": 1, "deletions": 0, "patch": "p" * 2000}
        for i in range(10)
    ]
    record = project_record(event, pr, files)
    assert record["repo"] == "acme/api"
    assert record["pr_number"] == 7
    assert len(record["body"]) == 2000
    assert len(record["files"]) == 8
    assert len(record["files"][0]["patch"]) == 1500
    assert record["files_changed"] == 9
