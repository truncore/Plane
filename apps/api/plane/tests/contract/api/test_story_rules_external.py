# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The public API applies the same User Story and Task rules as the web app."""

import json
from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import Estimate, EstimatePoint, Issue, IssueType, Project, ProjectMember
from plane.engineering.work_item_rules import POINTS_ON_TASK, TASK_PARENT_NOT_STORY


def built_in_type(workspace, key):
    return IssueType.objects.get(workspace=workspace, external_source="plane", external_id=key)


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def point(workspace, project):
    estimate = Estimate.objects.create(name="Fibonacci", type="points", project=project)
    return EstimatePoint.objects.create(estimate=estimate, key=3, value="3", project=project, workspace=workspace)


@pytest.fixture
def issues_url(workspace, project):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/"


@pytest.mark.contract
@pytest.mark.django_db
class TestExternalStoryRules:
    def test_task_cannot_have_points(self, api_key_client, issues_url, point):
        response = api_key_client.post(issues_url, {"name": "Task", "estimate_point": str(point.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert POINTS_ON_TASK in json.dumps(response.data)

    def test_task_cannot_go_under_a_task(self, api_key_client, workspace, project, issues_url):
        task = Issue.objects.create(name="Task", workspace=workspace, project=project)

        response = api_key_client.post(issues_url, {"name": "Sub task", "parent": str(task.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert TASK_PARENT_NOT_STORY in json.dumps(response.data)

    def test_story_switched_to_task_loses_its_points_in_the_history(
        self, api_key_client, workspace, project, issues_url, point
    ):
        story = Issue.objects.create(
            name="Story",
            workspace=workspace,
            project=project,
            type=built_in_type(workspace, "user_story"),
            estimate_point=point,
        )

        with mock.patch("plane.api.views.issue.issue_activity") as issue_activity:
            response = api_key_client.patch(
                f"{issues_url}{story.id}/", {"type_id": str(built_in_type(workspace, "task").id)}, format="json"
            )

        assert response.status_code == status.HTTP_200_OK, response.data
        assert Issue.objects.get(pk=story.id).estimate_point_id is None
        assert json.loads(issue_activity.delay.call_args.kwargs["requested_data"])["estimate_point"] is None
