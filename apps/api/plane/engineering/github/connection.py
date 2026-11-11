# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Module imports
from plane.db.models import State, StateGroup

from .client import GitHubClient, GitHubError

REVIEW_STATE_NAME = "In Review"
REVIEW_STATE_COLOR = "#8B5CF6"


def default_review_state(project):
    """The state for an open pull request: "In Review" in the started group, created when missing.

    A project that already uses the name "In Review" outside the started group keeps it, and pull
    requests use its first started state instead.
    """
    existing = State.objects.filter(project=project, name__iexact=REVIEW_STATE_NAME).first()
    if existing is not None:
        return existing if existing.group == StateGroup.STARTED.value else first_state(project, StateGroup.STARTED)

    last_started = first_state(project, StateGroup.STARTED, last=True)
    return State.objects.create(
        project=project,
        name=REVIEW_STATE_NAME,
        group=StateGroup.STARTED.value,
        color=REVIEW_STATE_COLOR,
        # Right after the existing started states, before the completed ones
        sequence=last_started.sequence + 1000 if last_started else 40000,
    )


def first_state(project, group, last=False):
    states = State.objects.filter(project=project, group=group.value).order_by("sequence")
    return states.last() if last else states.first()


def check_connection(connection):
    """Check that the token can see the repository, push to it, and that the base branch exists."""
    client = GitHubClient(connection.token, connection.repository_owner, connection.repository_name)
    repository = client.get_repository()
    if not repository.get("permissions", {}).get("push"):
        raise GitHubError("no_push_permission")
    client.get_branch(connection.base_branch)
    return {
        "repository": repository["full_name"],
        "private": repository["private"],
        "default_branch": repository["default_branch"],
    }
