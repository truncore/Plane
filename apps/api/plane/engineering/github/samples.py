# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Sample GitHub webhook payloads with the fields Plane reads, for local testing and the test suite."""

# Python imports
import uuid

# Django imports
from django.utils import timezone


def pull_request_payload(repository, number, branch, title, action, base="main", draft=False, merged=False):
    now = timezone.now().isoformat()
    closed = action == "closed"
    return {
        "action": action,
        "number": number,
        "repository": {"full_name": repository},
        "pull_request": {
            "number": number,
            "title": title,
            "html_url": f"https://github.com/{repository}/pull/{number}",
            "state": "closed" if closed else "open",
            "draft": draft,
            "merged": merged,
            "merged_at": now if merged else None,
            "closed_at": now if closed else None,
            "updated_at": now,
            "head": {"ref": branch},
            "base": {"ref": base},
            "user": {"login": "octocat"},
            "additions": 120,
            "deletions": 30,
            "changed_files": 4,
        },
    }


def push_payload(repository, branch, messages):
    return {
        "ref": f"refs/heads/{branch}",
        "repository": {"full_name": repository},
        "commits": [
            {
                "id": uuid.uuid4().hex + uuid.uuid4().hex[:8],
                "message": message,
                "url": f"https://github.com/{repository}/commit/{index}",
                "timestamp": timezone.now().isoformat(),
                "author": {"name": "Octo Cat", "username": "octocat"},
            }
            for index, message in enumerate(messages)
        ],
    }


# Sample name -> (GitHub event, pull request action or None for a push, extra options)
SAMPLES = {
    "pr-opened": ("pull_request", "opened", {}),
    "pr-draft": ("pull_request", "opened", {"draft": True}),
    "pr-ready": ("pull_request", "ready_for_review", {}),
    "pr-reopened": ("pull_request", "reopened", {}),
    "pr-merged": ("pull_request", "closed", {"merged": True}),
    "pr-closed": ("pull_request", "closed", {}),
    "push": ("push", None, {}),
    "push-fixes": ("push", None, {"closes": True}),
}


def sample_payload(name, connection, work_item_key, number, branch):
    """Build a named sample event for a work item like PAY-12. Returns (event, payload)."""
    event, action, options = SAMPLES[name]
    repository = connection.repository_full_name
    if event == "push":
        message = f"fixes {work_item_key}" if options.get("closes") else f"{work_item_key}: work in progress"
        return event, push_payload(repository, connection.base_branch, [message])
    return event, pull_request_payload(
        repository,
        number,
        branch or f"feat/{work_item_key.lower()}-sample",
        f"[{work_item_key}] Sample pull request",
        action,
        base=connection.base_branch,
        draft=options.get("draft", False),
        merged=options.get("merged", False),
    )
