# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""User Stories and Tasks: points on stories only, Story > Task hierarchy, story progress."""

import json
from unittest import mock

import pytest
from rest_framework import status

from plane.db.models import Estimate, EstimatePoint, Issue, IssueType, Project, ProjectMember, State
from plane.engineering.work_item_rules import (
    POINTS_ON_TASK,
    STORY_WITH_PARENT,
    STORY_WITH_TASKS,
    TASK_PARENT_NOT_STORY,
)


def built_in_type(workspace, key):
    return IssueType.objects.get(workspace=workspace, external_source="plane", external_id=key)


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def point(project):
    estimate = Estimate.objects.create(name="Fibonacci", type="points", project=project)
    return EstimatePoint.objects.create(estimate=estimate, key=3, value="3", project=project)


@pytest.fixture
def make_item(workspace, project):
    def make(name, key, **fields):
        return Issue.objects.create(
            name=name, workspace=workspace, project=project, type=built_in_type(workspace, key), **fields
        )

    return make


@pytest.fixture
def issues_url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"


@pytest.fixture
def issue_activity():
    with (
        mock.patch("plane.app.views.issue.base.issue_activity") as issue_activity,
        mock.patch("plane.app.views.issue.base.model_activity"),
    ):
        yield issue_activity


def error_text(response):
    return json.dumps(response.data)


@pytest.mark.contract
@pytest.mark.django_db
class TestPointsOnStoriesOnly:
    def test_story_can_have_points(self, session_client, workspace, issues_url, point, issue_activity):
        story = built_in_type(workspace, "user_story")

        response = session_client.post(
            issues_url, {"name": "Story", "type_id": str(story.id), "estimate_point": str(point.id)}, format="json"
        )

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert Issue.objects.get(pk=response.data["id"]).estimate_point_id == point.id

    def test_task_cannot_be_created_with_points(self, session_client, issues_url, point, issue_activity):
        response = session_client.post(issues_url, {"name": "Task", "estimate_point": str(point.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert POINTS_ON_TASK in error_text(response)

    def test_task_cannot_be_given_points(self, session_client, issues_url, point, make_item, issue_activity):
        task = make_item("Task", "task")

        response = session_client.patch(f"{issues_url}{task.id}/", {"estimate_point": str(point.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert POINTS_ON_TASK in error_text(response)

    def test_story_switched_to_task_loses_its_points_in_the_history(
        self, session_client, workspace, issues_url, point, make_item, issue_activity
    ):
        story = make_item("Story", "user_story", estimate_point=point)

        response = session_client.patch(
            f"{issues_url}{story.id}/", {"type_id": str(built_in_type(workspace, "task").id)}, format="json"
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT, response.data
        assert Issue.objects.get(pk=story.id).estimate_point_id is None
        requested_data = json.loads(issue_activity.delay.call_args.kwargs["requested_data"])
        assert requested_data["estimate_point"] is None

    def test_older_task_with_points_can_still_be_edited(
        self, session_client, issues_url, point, make_item, issue_activity
    ):
        task = make_item("Task", "task", estimate_point=point)

        response = session_client.patch(f"{issues_url}{task.id}/", {"name": "Renamed"}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, response.data
        assert Issue.objects.get(pk=task.id).estimate_point_id == point.id


@pytest.mark.contract
@pytest.mark.django_db
class TestHierarchy:
    def test_task_under_a_story(self, session_client, issues_url, make_item, issue_activity):
        story = make_item("Story", "user_story")

        response = session_client.post(issues_url, {"name": "Task", "parent_id": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data

    def test_task_cannot_go_under_a_task(self, session_client, issues_url, make_item, issue_activity):
        task = make_item("Task", "task")

        response = session_client.post(issues_url, {"name": "Sub task", "parent_id": str(task.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert TASK_PARENT_NOT_STORY in error_text(response)

    def test_story_cannot_have_a_parent(self, session_client, workspace, issues_url, make_item, issue_activity):
        parent = make_item("Story", "user_story")
        story = built_in_type(workspace, "user_story")

        response = session_client.post(
            issues_url, {"name": "Child story", "type_id": str(story.id), "parent_id": str(parent.id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert STORY_WITH_PARENT in error_text(response)

    def test_task_with_a_parent_cannot_become_a_story(
        self, session_client, workspace, issues_url, make_item, issue_activity
    ):
        task = make_item("Task", "task", parent=make_item("Story", "user_story"))

        response = session_client.patch(
            f"{issues_url}{task.id}/", {"type_id": str(built_in_type(workspace, "user_story").id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert STORY_WITH_PARENT in error_text(response)

    def test_story_with_tasks_cannot_become_a_task(
        self, session_client, workspace, issues_url, make_item, issue_activity
    ):
        story = make_item("Story", "user_story")
        make_item("Task", "task", parent=story)

        response = session_client.patch(
            f"{issues_url}{story.id}/", {"type_id": str(built_in_type(workspace, "task").id)}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert STORY_WITH_TASKS in error_text(response)

    def test_removing_a_parent_is_always_allowed(self, session_client, issues_url, make_item, issue_activity):
        task = make_item("Task", "task", parent=make_item("Task parent", "task"))

        response = session_client.patch(f"{issues_url}{task.id}/", {"parent_id": None}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, response.data


@pytest.mark.contract
@pytest.mark.django_db
class TestAddExistingSubWorkItems:
    @pytest.fixture
    def sub_issues_url(self, workspace, project):
        return lambda parent: f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/{parent.id}/sub-issues/"

    def test_tasks_can_be_added_to_a_story(self, session_client, make_item, sub_issues_url):
        story = make_item("Story", "user_story")
        task = make_item("Task", "task")

        with mock.patch("plane.app.views.issue.sub_issue.issue_activity"):
            response = session_client.post(sub_issues_url(story), {"sub_issue_ids": [str(task.id)]}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert Issue.objects.get(pk=task.id).parent_id == story.id

    def test_nothing_can_be_added_to_a_task(self, session_client, make_item, sub_issues_url):
        task = make_item("Task", "task")
        other = make_item("Other task", "task")

        response = session_client.post(sub_issues_url(task), {"sub_issue_ids": [str(other.id)]}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == TASK_PARENT_NOT_STORY
        assert Issue.objects.get(pk=other.id).parent_id is None

    def test_a_story_cannot_be_added_to_a_story(self, session_client, make_item, sub_issues_url):
        story = make_item("Story", "user_story")
        other = make_item("Other story", "user_story")

        response = session_client.post(sub_issues_url(story), {"sub_issue_ids": [str(other.id)]}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["error"] == STORY_WITH_PARENT


@pytest.mark.contract
@pytest.mark.django_db
class TestDraftRules:
    def test_task_draft_cannot_have_points(self, session_client, workspace, project, point):
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/draft-issues/",
            {"name": "Draft", "project_id": str(project.id), "estimate_point": str(point.id)},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert POINTS_ON_TASK in error_text(response)


@pytest.mark.contract
@pytest.mark.django_db
class TestStoryPickers:
    def test_search_can_list_only_stories(self, session_client, workspace, project, make_item):
        make_item("Story to pick", "user_story")
        make_item("Task to skip", "task")

        response = session_client.get(
            f"/api/workspaces/{workspace.slug}/projects/{project.id}/search-issues/",
            {"search": "to", "work_item_type": "user_story"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert [item["name"] for item in response.data] == ["Story to pick"]


@pytest.mark.contract
@pytest.mark.django_db
class TestStoryProgress:
    def test_counts_done_tasks_per_story(self, session_client, workspace, project, make_item):
        done = State.objects.create(name="Done", group="completed", project=project)
        todo = State.objects.create(name="Todo", group="unstarted", project=project)
        story = make_item("Story", "user_story")
        make_item("Done task", "task", parent=story, state=done)
        make_item("Open task", "task", parent=story, state=todo)
        make_item("Story without tasks", "user_story")

        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{project.id}/story-progress/")

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {str(story.id): {"total": 2, "completed": 1}}

    def test_requires_project_membership(self, session_client, workspace, create_user):
        other = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace, created_by=create_user)

        response = session_client.get(f"/api/workspaces/{workspace.slug}/projects/{other.id}/story-progress/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
