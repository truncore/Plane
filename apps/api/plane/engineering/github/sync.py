# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Apply GitHub pull request and push events to work items.

- Pull request opened, reopened or ready for review: the work item moves to the review state.
- Merged: it moves to the merged state once none of its pull requests is still open.
- Closed without merging: the state stays and a comment explains why.
- Drafts change nothing. Work items only ever move forward, and cancelled ones are left alone.
- Trunk-based projects: commits pushed to the trunk link to the work items they mention; a mention
  starts an unstarted item and "fixes PAY-12" completes it.
"""

# Python imports
import re

# Django imports
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.html import escape

# Module imports
from plane.db.models import Issue, StateGroup
from plane.engineering.github.connection import first_state
from plane.engineering.models import LinkedCommit, PullRequest, PullRequestState, WorkflowMode
from plane.engineering.work_items import add_comment, add_link, github_bot, update_work_item

# Work items move forward through these groups; cancelled and triage items are never moved
STATE_GROUP_RANK = {
    StateGroup.BACKLOG.value: 0,
    StateGroup.UNSTARTED.value: 1,
    StateGroup.STARTED.value: 2,
    StateGroup.COMPLETED.value: 3,
}
CLOSING_KEYWORDS = r"(?:fix|fixes|fixed|close|closes|closed|resolve|resolves|resolved|done)"


def mentioned_sequence_ids(text, identifier):
    """Sequence numbers of the project's work items mentioned in text, e.g. PAY-12 or pay-12 → {12}."""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(identifier)}-(\d+)(?![A-Za-z0-9])"
    return {int(number) for number in re.findall(pattern, text or "", re.IGNORECASE)}


def closed_sequence_ids(text, identifier):
    """Sequence numbers after a closing keyword, e.g. "fixes PAY-12" or "Done: PAY-12" → {12}."""
    pattern = rf"\b{CLOSING_KEYWORDS}\b:?\s+{re.escape(identifier)}-(\d+)(?![A-Za-z0-9])"
    return {int(number) for number in re.findall(pattern, text or "", re.IGNORECASE)}


def moves_forward(current, target):
    if target is None or target.group not in STATE_GROUP_RANK:
        return False
    if current is None:
        return True
    if current.group not in STATE_GROUP_RANK:
        return False
    return (STATE_GROUP_RANK[target.group], target.sequence) > (STATE_GROUP_RANK[current.group], current.sequence)


def move_forward(issue, state, actor):
    if moves_forward(issue.state, state):
        update_work_item(issue, {"state": str(state.id)}, actor)


def pull_request_state(pull_request):
    if pull_request.get("merged"):
        return PullRequestState.MERGED
    if pull_request["state"] == "closed":
        return PullRequestState.CLOSED
    return PullRequestState.DRAFT if pull_request.get("draft") else PullRequestState.OPEN


def handle_pull_request(connection, payload, delivery_id):
    project = connection.project
    pull_request = payload["pull_request"]
    repository = payload["repository"]["full_name"]
    number = pull_request["number"]
    mentioned = mentioned_sequence_ids(pull_request["head"]["ref"], project.identifier) | mentioned_sequence_ids(
        pull_request["title"], project.identifier
    )
    work_items = Issue.issue_objects.filter(
        Q(pull_requests__repository_full_name__iexact=repository, pull_requests__number=number)
        | Q(sequence_id__in=mentioned),
        project=project,
    ).distinct()
    if not work_items:
        return

    bot = github_bot(project.workspace)
    github_updated_at = parse_datetime(pull_request["updated_at"])
    for issue in work_items.select_related("state", "workspace"):
        record = PullRequest.objects.filter(issue=issue, repository_full_name__iexact=repository, number=number).first()
        if record and record.github_updated_at and record.github_updated_at > github_updated_at:
            continue  # GitHub delivered an older event after a newer one
        record = record or PullRequest(issue=issue, project=project, repository_full_name=repository, number=number)
        record.title = pull_request["title"]
        record.url = pull_request["html_url"]
        record.head_branch = pull_request["head"]["ref"]
        record.base_branch = pull_request["base"]["ref"]
        record.state = pull_request_state(pull_request)
        record.author_login = (pull_request.get("user") or {}).get("login", "")
        record.additions = pull_request.get("additions")
        record.deletions = pull_request.get("deletions")
        record.changed_files = pull_request.get("changed_files")
        record.merged_at = parse_datetime(pull_request["merged_at"]) if pull_request.get("merged_at") else None
        record.closed_at = parse_datetime(pull_request["closed_at"]) if pull_request.get("closed_at") else None
        record.github_updated_at = github_updated_at
        record.save()

        add_link(issue, record.url, f"PR #{number}: {record.title}", bot)
        apply_pull_request_event(issue, record, payload["action"], connection, bot, delivery_id)


def apply_pull_request_event(issue, record, action, connection, bot, delivery_id):
    if record.state == PullRequestState.OPEN and action in ("opened", "reopened", "ready_for_review"):
        move_forward(issue, connection.review_state, bot)
    elif record.state == PullRequestState.MERGED and action == "closed":
        # Done when no pull request is still open; ones closed without merging don't hold it back
        if not issue.pull_requests.filter(state__in=[PullRequestState.OPEN, PullRequestState.DRAFT]).exists():
            move_forward(issue, connection.merged_state, bot)
    elif record.state == PullRequestState.CLOSED and action == "closed":
        link = f'<a href="{escape(record.url)}">#{record.number}</a>'
        add_comment(
            issue,
            f"<p>Pull request {link} was closed without merging, so the state was not changed.</p>",
            bot,
            external_id=f"pull-request-closed:{delivery_id}",
        )


def handle_push(connection, payload, delivery_id):
    if connection.workflow_mode != WorkflowMode.TRUNK_BASED or payload["ref"] != f"refs/heads/{connection.base_branch}":
        return
    project = connection.project
    bot = github_bot(project.workspace)
    first_started = first_state(project, StateGroup.STARTED)
    repository = payload["repository"]["full_name"]

    for commit in payload.get("commits", []):
        message = commit["message"]
        closed = closed_sequence_ids(message, project.identifier)
        mentioned = mentioned_sequence_ids(message, project.identifier)
        work_items = Issue.issue_objects.filter(project=project, sequence_id__in=mentioned).select_related(
            "state", "workspace"
        )
        for issue in work_items:
            LinkedCommit.objects.get_or_create(
                issue=issue,
                sha=commit["id"],
                defaults={
                    "project": project,
                    "repository_full_name": repository,
                    "branch": connection.base_branch,
                    "message": message,
                    "url": commit["url"],
                    "author_name": commit["author"].get("name", ""),
                    "author_login": commit["author"].get("username", ""),
                    "committed_at": parse_datetime(commit["timestamp"]),
                },
            )
            if issue.sequence_id in closed:
                move_forward(issue, connection.merged_state, bot)
            elif issue.state and issue.state.group in (StateGroup.BACKLOG.value, StateGroup.UNSTARTED.value):
                move_forward(issue, first_started, bot)


EVENT_HANDLERS = {"pull_request": handle_pull_request, "push": handle_push}
