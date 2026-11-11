# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Opening a pull request from a work item: branch suggestions, a preview with warnings, and creation."""

# Django imports
from django.utils import timezone
from django.utils.dateparse import parse_datetime

# Module imports
from plane.engineering.github.client import GitHubClient
from plane.engineering.github.sync import mentioned_sequence_ids, move_forward, record_pull_request
from plane.engineering.models import WorkflowMode
from plane.engineering.work_items import add_link


def client_for(connection):
    return GitHubClient(connection.token, connection.repository_owner, connection.repository_name)


def work_item_branches(connection, issue):
    """The repository's recent branches, newest first, with the ones naming this work item at the top."""
    branches = client_for(connection).list_branches()
    for branch in branches:
        branch["suggested"] = issue.sequence_id in mentioned_sequence_ids(branch["name"], connection.project.identifier)
    return sorted(branches, key=lambda branch: not branch["suggested"])


def preview_pull_request(connection, base, head):
    """What a pull request from head into base would contain, with the trunk-based warnings."""
    client = client_for(connection)
    comparison = client.compare(base, head)
    commits = comparison.get("commits", [])
    files = comparison.get("files", [])
    # GitHub lists the branch's commits oldest first: the first one dates the branch
    first_commit_at = parse_datetime(commits[0]["commit"]["committer"]["date"]) if commits else None
    branch_age_days = (timezone.now() - first_commit_at).days if first_commit_at else 0
    changed_lines = sum(file["additions"] + file["deletions"] for file in files)
    existing = client.find_open_pull_request(base, head)
    trunk_based = connection.workflow_mode == WorkflowMode.TRUNK_BASED
    return {
        "ahead_by": comparison["ahead_by"],
        "changed_files": len(files),
        "changed_lines": changed_lines,
        "branch_age_days": branch_age_days,
        "is_old_branch": trunk_based and branch_age_days > connection.branch_age_limit_days,
        "is_large": trunk_based and changed_lines > connection.large_pr_lines,
        "existing_pull_request_url": existing["html_url"] if existing else None,
    }


def open_pull_request(connection, issue, user, base, head, title, body):
    """Open the pull request on GitHub, then record and link it and move the work item, as the user who asked."""
    pull_request = client_for(connection).create_pull_request(base, head, title, body)
    record = record_pull_request(issue, connection.repository_full_name, pull_request)
    add_link(issue, record.url, f"PR #{record.number}: {record.title}", user)
    move_forward(issue, connection.review_state, user)
    return record
