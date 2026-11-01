# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Built-in work item types: project seeding, API read/write, filtering and activity history."""

import importlib
import json
from unittest import mock
from uuid import uuid4

import pytest
from django.apps import apps
from rest_framework import status

from plane.bgtasks.issue_activities_task import track_type, update_issue_activity
from plane.db.models import (
    Issue,
    IssueActivity,
    IssueType,
    Project,
    ProjectIssueType,
    ProjectMember,
    State,
    Workspace,
)
from plane.tests.factories import UserFactory

ISSUE_ACTIVITY_PATH = "plane.app.views.issue.base.issue_activity"
MODEL_ACTIVITY_PATH = "plane.app.views.issue.base.model_activity"


def built_in_type(workspace, key):
    return IssueType.objects.get(workspace=workspace, external_source="plane", external_id=key)


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    return project


@pytest.fixture
def issues_url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/issues/"


@pytest.fixture
def activity_tasks():
    with mock.patch(ISSUE_ACTIVITY_PATH) as issue_activity, mock.patch(MODEL_ACTIVITY_PATH) as model_activity:
        yield issue_activity, model_activity


@pytest.fixture
def foreign_type(create_user):
    """A built-in type that belongs to another workspace."""
    workspace = Workspace.objects.create(name="Other", owner=create_user, slug=f"other-{uuid4().hex[:8]}")
    Project.objects.create(name="Other", identifier="OTHER", workspace=workspace, created_by=create_user)
    return built_in_type(workspace, "user_story")


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectTypeSeeding:
    def test_new_project_gets_both_types_with_task_as_default(self, workspace, project):
        links = ProjectIssueType.objects.filter(project=project)

        assert {link.issue_type.external_id: link.is_default for link in links} == {"user_story": False, "task": True}
        assert built_in_type(workspace, "task").is_default is True
        assert built_in_type(workspace, "user_story").is_default is False

    def test_projects_in_a_workspace_share_the_types(self, workspace, project, create_user):
        second = Project.objects.create(name="Two", identifier="TWO", workspace=workspace, created_by=create_user)

        assert IssueType.objects.filter(workspace=workspace).count() == 2
        assert ProjectIssueType.objects.filter(project=second).count() == 2

    def test_updating_a_project_does_not_add_types(self, workspace, project):
        project.name = "Renamed"
        project.save()

        assert ProjectIssueType.objects.filter(project=project).count() == 2


@pytest.mark.contract
@pytest.mark.django_db
class TestSeedMigration:
    migration = importlib.import_module("plane.db.migrations.0126_seed_built_in_work_item_types")

    def clear_types(self):
        Issue._base_manager.update(type_id=None)
        ProjectIssueType._base_manager.all().delete()
        IssueType._base_manager.all().delete()

    def test_existing_project_and_work_items_are_seeded(self, workspace, project):
        issue = Issue.objects.create(name="Old", workspace=workspace, project=project)
        archived = Issue.objects.create(name="Archived", workspace=workspace, project=project, archived_at="2026-01-01")
        self.clear_types()

        self.migration.seed_built_in_types(apps, None)

        task = built_in_type(workspace, "task")
        assert ProjectIssueType.objects.filter(project=project).count() == 2
        assert Issue.all_objects.get(pk=issue.pk).type_id == task.id
        assert Issue.all_objects.get(pk=archived.pk).type_id == task.id

    def test_running_twice_changes_nothing(self, workspace, project):
        self.clear_types()

        self.migration.seed_built_in_types(apps, None)
        self.migration.seed_built_in_types(apps, None)

        assert IssueType.objects.filter(workspace=workspace).count() == 2
        assert ProjectIssueType.objects.filter(project=project).count() == 2

    def test_existing_type_on_a_work_item_is_kept(self, workspace, project):
        story = built_in_type(workspace, "user_story")
        issue = Issue.objects.create(name="Story", workspace=workspace, project=project, type=story)

        self.migration.seed_built_in_types(apps, None)

        assert Issue.objects.get(pk=issue.pk).type_id == story.id

    def test_reverse_removes_the_types(self, workspace, project):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)

        self.migration.remove_built_in_types(apps, None)

        assert IssueType.objects.filter(workspace=workspace).count() == 0
        assert ProjectIssueType.objects.filter(project=project).count() == 0
        assert Issue.objects.get(pk=issue.pk).type_id is None


@pytest.mark.contract
@pytest.mark.django_db
class TestCreateAndUpdate:
    def test_create_without_type_uses_task(self, session_client, workspace, issues_url, activity_tasks):
        response = session_client.post(issues_url, {"name": "Item"}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["type_id"] == built_in_type(workspace, "task").id

    def test_create_with_null_type_uses_task(self, session_client, workspace, issues_url, activity_tasks):
        response = session_client.post(issues_url, {"name": "Item", "type_id": None}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["type_id"] == built_in_type(workspace, "task").id

    def test_create_user_story(self, session_client, workspace, issues_url, activity_tasks):
        story = built_in_type(workspace, "user_story")

        response = session_client.post(issues_url, {"name": "Story", "type_id": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["type_id"] == story.id
        assert Issue.objects.get(pk=response.data["id"]).type_id == story.id

    def test_create_rejects_type_from_another_workspace(self, session_client, issues_url, foreign_type, activity_tasks):
        response = session_client.post(issues_url, {"name": "Item", "type_id": str(foreign_type.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_raw_type_field_is_read_only(self, session_client, workspace, issues_url, activity_tasks):
        story = built_in_type(workspace, "user_story")

        response = session_client.post(issues_url, {"name": "Item", "type": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        assert response.data["type_id"] == built_in_type(workspace, "task").id

    def test_sub_work_item_can_be_a_task_under_a_story(
        self, session_client, workspace, project, issues_url, activity_tasks
    ):
        story = Issue.objects.create(
            name="Story", workspace=workspace, project=project, type=built_in_type(workspace, "user_story")
        )

        response = session_client.post(issues_url, {"name": "Sub", "parent_id": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_201_CREATED, response.data
        child = Issue.objects.get(pk=response.data["id"])
        assert child.parent_id == story.id
        assert child.type_id == built_in_type(workspace, "task").id

    def test_update_switches_type_and_reports_the_change(
        self, session_client, workspace, project, issues_url, activity_tasks
    ):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)
        story = built_in_type(workspace, "user_story")

        response = session_client.patch(f"{issues_url}{issue.id}/", {"type_id": str(story.id)}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, getattr(response, "data", None)
        assert Issue.objects.get(pk=issue.pk).type_id == story.id
        call = activity_tasks[0].delay.call_args.kwargs
        assert json.loads(call["requested_data"])["type_id"] == str(story.id)
        assert json.loads(call["current_instance"])["type_id"] == str(built_in_type(workspace, "task").id)

    def test_update_with_null_type_keeps_the_type(self, session_client, workspace, project, issues_url, activity_tasks):
        story = built_in_type(workspace, "user_story")
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project, type=story)

        response = session_client.patch(f"{issues_url}{issue.id}/", {"type_id": None}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, getattr(response, "data", None)
        assert Issue.objects.get(pk=issue.pk).type_id == story.id

    def test_update_rejects_type_from_another_workspace(
        self, session_client, workspace, project, issues_url, foreign_type, activity_tasks
    ):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)

        response = session_client.patch(f"{issues_url}{issue.id}/", {"type_id": str(foreign_type.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert Issue.objects.get(pk=issue.pk).type_id == built_in_type(workspace, "task").id


@pytest.mark.contract
@pytest.mark.django_db
class TestReadAndFilter:
    @pytest.fixture
    def typed_issues(self, workspace, project):
        story = Issue.objects.create(
            name="Story", workspace=workspace, project=project, type=built_in_type(workspace, "user_story")
        )
        task = Issue.objects.create(name="Task", workspace=workspace, project=project)
        return story, task

    @staticmethod
    def result_ids(response):
        assert response.status_code == status.HTTP_200_OK, response.data
        return {str(row["id"]) for row in response.data["results"]}

    def test_list_returns_type_id(self, session_client, workspace, issues_url, typed_issues):
        response = session_client.get(issues_url)

        rows = {str(row["id"]): row["type_id"] for row in response.data["results"]}
        assert rows[str(typed_issues[0].id)] == built_in_type(workspace, "user_story").id
        assert rows[str(typed_issues[1].id)] == built_in_type(workspace, "task").id

    def test_detail_returns_type_id(self, session_client, workspace, issues_url, typed_issues):
        response = session_client.get(f"{issues_url}{typed_issues[0].id}/")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert str(response.data["type_id"]) == str(built_in_type(workspace, "user_story").id)

    def test_sub_issue_list_returns_type_id(self, session_client, workspace, issues_url, typed_issues):
        story, task = typed_issues
        task.parent = story
        task.save()

        response = session_client.get(f"{issues_url}{story.id}/sub-issues/")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["sub_issues"][0]["type_id"] == built_in_type(workspace, "task").id

    def test_rich_filter_by_type(self, session_client, workspace, issues_url, typed_issues):
        story_type = built_in_type(workspace, "user_story")

        response = session_client.get(issues_url, {"filters": json.dumps({"type_id__in": str(story_type.id)})})

        assert self.result_ids(response) == {str(typed_issues[0].id)}

    def test_rich_filter_by_several_types(self, session_client, workspace, issues_url, typed_issues):
        type_ids = ",".join(str(built_in_type(workspace, key).id) for key in ("user_story", "task"))

        response = session_client.get(issues_url, {"filters": json.dumps({"type_id__in": type_ids})})

        assert self.result_ids(response) == {str(issue.id) for issue in typed_issues}

    def test_query_param_filter_by_type(self, session_client, workspace, issues_url, typed_issues):
        task_type = built_in_type(workspace, "task")

        response = session_client.get(issues_url, {"type_id": str(task_type.id)})

        assert self.result_ids(response) == {str(typed_issues[1].id)}

    def test_state_type_filter_keeps_its_meaning(self, session_client, workspace, project, issues_url, typed_issues):
        backlog = State.objects.create(name="Backlog", group="backlog", project=project, workspace=workspace)
        story, task = typed_issues
        story.state = backlog
        story.save()

        response = session_client.get(issues_url, {"type": "backlog"})

        assert self.result_ids(response) == {str(story.id)}


@pytest.mark.contract
@pytest.mark.django_db
class TestActivity:
    def track(self, workspace, project, issue, requested, current):
        activities = []
        track_type(
            requested_data=requested,
            current_instance=current,
            issue_id=issue.id,
            project_id=project.id,
            workspace_id=workspace.id,
            actor_id=project.created_by_id,
            issue_activities=activities,
            epoch=1,
        )
        return activities

    def test_type_change_is_recorded(self, workspace, project):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)
        task = built_in_type(workspace, "task")
        story = built_in_type(workspace, "user_story")

        activities = self.track(workspace, project, issue, {"type_id": str(story.id)}, {"type_id": str(task.id)})

        assert len(activities) == 1
        activity = activities[0]
        assert (activity.field, activity.verb) == ("type", "updated")
        assert (activity.old_value, activity.new_value) == ("Task", "User Story")
        assert (activity.old_identifier, activity.new_identifier) == (task.id, story.id)

    def test_same_type_records_nothing(self, workspace, project):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)
        task_id = str(built_in_type(workspace, "task").id)

        assert self.track(workspace, project, issue, {"type_id": task_id}, {"type_id": task_id}) == []

    def test_empty_type_records_nothing(self, workspace, project):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)
        task_id = str(built_in_type(workspace, "task").id)

        assert self.track(workspace, project, issue, {"type_id": None}, {"type_id": task_id}) == []

    def test_update_activity_routes_type_id_to_the_tracker(self, workspace, project, create_user):
        issue = Issue.objects.create(name="Item", workspace=workspace, project=project)
        activities = []

        update_issue_activity(
            requested_data=json.dumps({"type_id": str(built_in_type(workspace, "user_story").id)}),
            current_instance=json.dumps({"type_id": str(built_in_type(workspace, "task").id)}),
            issue_id=issue.id,
            project_id=project.id,
            workspace_id=workspace.id,
            actor_id=create_user.id,
            issue_activities=activities,
            epoch=1,
        )
        IssueActivity.objects.bulk_create(activities)

        assert IssueActivity.objects.get(issue=issue, field="type").new_value == "User Story"


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkspaceTypesEndpoint:
    def test_lists_built_in_types_with_keys(self, session_client, workspace, project):
        response = session_client.get(f"/api/workspaces/{workspace.slug}/issue-types/")

        assert response.status_code == status.HTTP_200_OK, response.data
        assert [(row["key"], row["is_default"]) for row in response.data] == [("user_story", False), ("task", True)]

    def test_non_member_is_forbidden(self, api_client, workspace, project):
        api_client.force_authenticate(user=UserFactory())

        response = api_client.get(f"/api/workspaces/{workspace.slug}/issue-types/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
@pytest.mark.django_db
class TestDrafts:
    def test_draft_keeps_its_type(self, session_client, workspace, project):
        story = built_in_type(workspace, "user_story")

        created = session_client.post(
            f"/api/workspaces/{workspace.slug}/draft-issues/",
            {"name": "Draft", "project_id": str(project.id), "type_id": str(story.id)},
            format="json",
        )

        assert created.status_code == status.HTTP_201_CREATED, created.data
        assert str(created.data["type_id"]) == str(story.id)

    def test_draft_rejects_type_from_another_workspace(self, session_client, workspace, project, foreign_type):
        response = session_client.post(
            f"/api/workspaces/{workspace.slug}/draft-issues/",
            {"name": "Draft", "project_id": str(project.id), "type_id": str(foreign_type.id)},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
