# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The public API applies the same work item type rules as the web app."""

from uuid import uuid4

import pytest
from rest_framework import status

from plane.db.models import Issue, IssueType, Project, ProjectMember, Workspace


def built_in_type(workspace, key):
    return IssueType.objects.get(workspace=workspace, external_source="plane", external_id=key)


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def issues_url(workspace, project):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/"


@pytest.mark.contract
@pytest.mark.django_db
class TestExternalWorkItemTypes:
    def test_create_without_type_uses_task(self, api_key_client, workspace, issues_url):
        response = api_key_client.post(issues_url, {"name": "Item"}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.objects.get(pk=response.data["id"]).type_id == built_in_type(workspace, "task").id

    def test_create_user_story(self, api_key_client, workspace, issues_url):
        story = built_in_type(workspace, "user_story")

        response = api_key_client.post(issues_url, {"name": "Story", "type_id": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.objects.get(pk=response.data["id"]).type_id == story.id

    def test_type_from_another_workspace_is_rejected(self, api_key_client, issues_url, create_user):
        other = Workspace.objects.create(name="Other", owner=create_user, slug=f"other-{uuid4().hex[:8]}")
        Project.objects.create(name="Other", identifier="OTHER", workspace=other, created_by=create_user)

        response = api_key_client.post(
            issues_url, {"name": "Item", "type_id": str(built_in_type(other, "user_story").id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
