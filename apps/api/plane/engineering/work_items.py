# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Change work items on behalf of an integration the same way the public API does.

Every change is validated by the API serializers and recorded through ``issue_activity`` and
``model_activity``, so history, notifications and outgoing webhooks stay correct.
"""

# Python imports
import json
import uuid

# Django imports
from django.contrib.auth.hashers import make_password
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

# Third party imports
from crum import impersonate

# Module imports
from plane.api.serializers import IssueCommentCreateSerializer, IssueLinkCreateSerializer, IssueSerializer
from plane.app.permissions import ROLE
from plane.bgtasks.issue_activities_task import issue_activity
from plane.bgtasks.webhook_task import model_activity
from plane.db.models import BotTypeEnum, IssueLink, User, WorkspaceMember
from plane.utils.host import base_host
from plane.utils.serializers import writable_data


def github_bot(workspace):
    """The workspace's GitHub bot user, the actor of every change GitHub causes."""
    username = f"github_bot_{workspace.id}"
    bot = User.objects.filter(username=username).first()
    if bot is None:
        bot = User.objects.create(
            username=username,
            email=f"{username}@github.bot.plane",
            display_name="GitHub",
            first_name="GitHub",
            is_bot=True,
            bot_type=BotTypeEnum.GITHUB,
            password=make_password(uuid.uuid4().hex),
            is_password_autoset=True,
        )
    WorkspaceMember.objects.get_or_create(workspace=workspace, member=bot, defaults={"role": ROLE.MEMBER.value})
    return bot


def _epoch():
    return int(timezone.now().timestamp())


def update_work_item(issue, data, actor):
    """Partially update a work item, e.g. ``{"state": state_id}``, as ``actor``."""
    current_instance = json.dumps(IssueSerializer(issue).data, cls=DjangoJSONEncoder)
    serializer = IssueSerializer(
        issue,
        data=data,
        partial=True,
        context={"project_id": issue.project_id, "workspace_id": issue.workspace_id},
    )
    serializer.is_valid(raise_exception=True)
    with impersonate(actor):
        serializer.save()
    accepted_data = {**writable_data(serializer, data), **serializer.implied_changes}
    issue_activity.delay(
        type="issue.activity.updated",
        requested_data=json.dumps(accepted_data, cls=DjangoJSONEncoder),
        actor_id=str(actor.id),
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=current_instance,
        epoch=_epoch(),
        notification=True,
        origin=base_host(request=None, is_app=True),
    )
    model_activity.delay(
        model_name="issue",
        model_id=str(issue.id),
        requested_data=accepted_data,
        current_instance=current_instance,
        actor_id=actor.id,
        slug=issue.workspace.slug,
        origin=base_host(request=None, is_app=True),
    )


def add_comment(issue, comment_html, actor, external_id):
    """Comment on a work item as ``actor``. ``external_id`` makes repeated deliveries add it only once."""
    if issue.issue_comments.filter(external_source="github", external_id=external_id).exists():
        return
    serializer = IssueCommentCreateSerializer(
        data={"comment_html": comment_html, "external_source": "github", "external_id": external_id}
    )
    serializer.is_valid(raise_exception=True)
    with impersonate(actor):
        serializer.save(project_id=issue.project_id, issue_id=issue.id, actor=actor)
    issue_activity.delay(
        type="comment.activity.created",
        requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
        actor_id=str(actor.id),
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=None,
        epoch=_epoch(),
    )
    model_activity.delay(
        model_name="issue_comment",
        model_id=str(serializer.instance.id),
        requested_data=serializer.data,
        current_instance=None,
        actor_id=actor.id,
        slug=issue.workspace.slug,
        origin=base_host(request=None, is_app=True),
    )


def add_link(issue, url, title, actor):
    """Link a URL to a work item as ``actor``, once."""
    if IssueLink.objects.filter(issue=issue, url=url).exists():
        return
    serializer = IssueLinkCreateSerializer(data={"url": url, "title": title})
    serializer.is_valid(raise_exception=True)
    with impersonate(actor):
        serializer.save(project_id=issue.project_id, issue_id=issue.id)
    issue_activity.delay(
        type="link.activity.created",
        requested_data=json.dumps(serializer.data, cls=DjangoJSONEncoder),
        actor_id=str(actor.id),
        issue_id=str(issue.id),
        project_id=str(issue.project_id),
        current_instance=None,
        epoch=_epoch(),
    )
