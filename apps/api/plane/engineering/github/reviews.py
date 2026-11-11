# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reviewing and merging a work item's pull request from Plane. Actions run as the person's own GitHub account."""

# Module imports
from plane.engineering.github.client import GitHubClient, GitHubError
from plane.engineering.github.pull_requests import client_for
from plane.engineering.github.sync import apply_pull_request_event, pull_request_state, record_pull_request
from plane.engineering.models import GitHubAccount

REVIEW_EVENTS = ("APPROVE", "REQUEST_CHANGES", "COMMENT")
MERGE_METHODS = ("merge", "squash", "rebase")
# GitHub's mergeable_state values for which it allows merging
MERGEABLE_STATES = ("clean", "unstable", "has_hooks")


def personal_client(connection, user):
    account = GitHubAccount.objects.filter(user=user).first()
    if account is None:
        raise GitHubError("no_personal_account")
    return GitHubClient(account.token, connection.repository_owner, connection.repository_name)


def latest_verdicts(reviews, requested_reviewers):
    """Each reviewer's current verdict: their last approval or change request, or "PENDING" when asked again."""
    verdicts = {}
    for review in reviews:  # oldest first
        login = review["user"]["login"]
        if review["state"] != "COMMENTED" or login not in verdicts:
            verdicts[login] = review["state"]
    for reviewer in requested_reviewers:
        verdicts[reviewer["login"]] = "PENDING"
    return [{"login": login, "state": state} for login, state in verdicts.items()]


def pull_request_details(connection, record, user):
    """The pull request's live status on GitHub: reviews, checks, whether it can merge, and what the user may do."""
    account = GitHubAccount.objects.filter(user=user).first()
    client = client_for(connection, user)
    pull_request = client.get_pull_request(record.number)
    record_pull_request(record.issue, connection.repository_full_name, pull_request)
    is_open = pull_request["state"] == "open"
    return {
        "url": pull_request["html_url"],
        "files_url": f"{pull_request['html_url']}/files",
        "state": pull_request_state(pull_request),
        "mergeable_state": pull_request.get("mergeable_state") or "unknown",
        "reviewers": latest_verdicts(client.list_reviews(record.number), pull_request.get("requested_reviewers", [])),
        "checks": [
            {"name": run["name"], "status": run["status"], "conclusion": run["conclusion"], "url": run["html_url"]}
            for run in client.list_check_runs(pull_request["head"]["sha"])
        ],
        "acting_as": account.login if account else None,
        # GitHub doesn't let people approve their own pull request
        "can_review": bool(account) and is_open and pull_request["user"]["login"] != account.login,
        "can_merge": bool(account)
        and is_open
        and not pull_request["draft"]
        and pull_request.get("mergeable_state") in MERGEABLE_STATES,
    }


def review_pull_request(connection, record, user, event, body):
    personal_client(connection, user).create_review(record.number, event, body)


def request_reviewers(connection, record, user, reviewers):
    personal_client(connection, user).request_reviewers(record.number, reviewers)


def merge_pull_request(connection, record, user, method):
    """Merge on GitHub, then apply the merge to the work item at once instead of waiting for the webhook."""
    client = personal_client(connection, user)
    client.merge_pull_request(record.number, method)
    record = record_pull_request(record.issue, connection.repository_full_name, client.get_pull_request(record.number))
    if record:
        apply_pull_request_event(record.issue, record, "closed", connection, user, f"plane-merge:{record.id}")
