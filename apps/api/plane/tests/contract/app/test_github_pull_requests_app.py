# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Opening a pull request from a work item: branches, preview with trunk-based warnings, creation, errors."""

from datetime import timedelta
from unittest import mock

import pytest
import requests
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Issue, IssueLink, Project, ProjectMember, State, WorkspaceMember
from plane.engineering.models import GitHubConnection, PullRequest
from plane.engineering.serializers import GitHubConnectionSerializer
from plane.tests.factories import UserFactory
from plane.tests.github_fakes import REQUEST_PATH, FakeGitHub, response


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    State.objects.create(name="Todo", group="unstarted", sequence=25000, project=project, default=True)
    State.objects.create(name="Done", group="completed", sequence=45000, project=project)
    return project


@pytest.fixture
def connection(project):
    data = {"repository_owner": "truncore", "repository_name": "plane", "token": "token", "webhook_secret": "secret"}
    serializer = GitHubConnectionSerializer(data=data, context={"project_id": project.id})
    serializer.is_valid(raise_exception=True)
    return serializer.save()


@pytest.fixture
def item(project):
    return Issue.objects.create(name="Pay by link", project=project, workspace=project.workspace)


@pytest.fixture
def url(item):
    work_item_url = f"/api/workspaces/{item.workspace.slug}/projects/{item.project_id}/issues/{item.id}"
    return lambda action: f"{work_item_url}/github/{action}/"


@pytest.fixture(autouse=True)
def activity():
    with (
        mock.patch("plane.engineering.work_items.issue_activity") as issue_activity,
        mock.patch("plane.engineering.work_items.model_activity"),
    ):
        yield issue_activity


def branches_graphql(*names_and_dates):
    nodes = [{"name": name, "target": {"committedDate": date}} for name, date in names_and_dates]
    return response(json={"data": {"repository": {"refs": {"nodes": nodes}}}})


def comparison(ahead_by=2, days_old=1, lines=(100, 20)):
    first_commit = (timezone.now() - timedelta(days=days_old)).isoformat()
    return response(
        json={
            "ahead_by": ahead_by,
            "commits": [{"commit": {"committer": {"date": first_commit}}}],
            "files": [{"additions": lines[0], "deletions": lines[1]}],
        }
    )


def created_pull_request(number=7):
    return response(
        201,
        {
            "number": number,
            "title": "[SCRUM-1] Pay by link",
            "html_url": f"https://github.com/truncore/plane/pull/{number}",
            "state": "open",
            "draft": False,
            "merged": False,
            "updated_at": timezone.now().isoformat(),
            "head": {"ref": "feat/scrum-1-pay-by-link"},
            "base": {"ref": "main"},
            "user": {"login": "truncore-bot"},
        },
    )


@pytest.mark.contract
@pytest.mark.django_db
class TestBranches:
    def test_branches_naming_the_work_item_come_first(self, session_client, connection, item, url):
        github = FakeGitHub(
            {
                ("POST", "/graphql"): branches_graphql(
                    ("main", "2026-11-10T10:00:00Z"),
                    (f"feat/scrum-{item.sequence_id}-pay-by-link", "2026-11-09T10:00:00Z"),
                    ("feat/scrum-99-other", "2026-11-08T10:00:00Z"),
                )
            }
        )
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.get(url("branches"))

        assert result.status_code == status.HTTP_200_OK, result.data
        assert [(b["name"], b["suggested"]) for b in result.data["branches"]] == [
            (f"feat/scrum-{item.sequence_id}-pay-by-link", True),
            ("main", False),
            ("feat/scrum-99-other", False),
        ]
        assert result.data["base_branch"] == "main"
        assert (result.data["branch_age_limit_days"], result.data["large_pr_lines"]) == (2, 400)

    def test_missing_repository_is_explained(self, session_client, connection, url):
        github = FakeGitHub({("POST", "/graphql"): response(json={"errors": [{"type": "NOT_FOUND"}]})})
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.get(url("branches"))

        assert result.data["code"] == "repository_not_found"

    def test_not_connected(self, session_client, item, url):
        result = session_client.get(url("branches"))

        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert result.data["code"] == "not_connected"


@pytest.mark.contract
@pytest.mark.django_db
class TestPreview:
    def preview(self, client, url, routes, head="feat/x", base="main"):
        with mock.patch(REQUEST_PATH, side_effect=FakeGitHub(routes)):
            return client.get(url("preview"), {"base": base, "head": head})

    def routes(self, compare, existing=()):
        return {
            ("GET", "/repos/truncore/plane/compare/main...feat/x"): compare,
            ("GET", "/repos/truncore/plane/pulls"): response(json=list(existing)),
        }

    def test_small_fresh_branch(self, session_client, connection, url):
        result = self.preview(session_client, url, self.routes(comparison()))

        assert result.status_code == status.HTTP_200_OK, result.data
        assert result.data == {
            "ahead_by": 2,
            "changed_files": 1,
            "changed_lines": 120,
            "branch_age_days": 1,
            "is_old_branch": False,
            "is_large": False,
            "existing_pull_request_url": None,
        }

    def test_trunk_based_warns_about_old_branches_and_large_changes(self, session_client, connection, url):
        result = self.preview(session_client, url, self.routes(comparison(days_old=5, lines=(380, 60))))

        assert (result.data["is_old_branch"], result.data["is_large"]) == (True, True)

    def test_feature_branch_projects_get_no_trunk_warnings(self, session_client, connection, url):
        GitHubConnection.objects.filter(pk=connection.pk).update(workflow_mode="feature_branches")

        result = self.preview(session_client, url, self.routes(comparison(days_old=5, lines=(380, 60))))

        assert (result.data["is_old_branch"], result.data["is_large"]) == (False, False)

    def test_existing_pull_request_is_reported(self, session_client, connection, url):
        existing = [{"html_url": "https://github.com/truncore/plane/pull/3"}]

        result = self.preview(session_client, url, self.routes(comparison(), existing))

        assert result.data["existing_pull_request_url"] == "https://github.com/truncore/plane/pull/3"

    @pytest.mark.parametrize("head", ["main", "bad..name", "has space"])
    def test_bad_branches_are_rejected_before_calling_github(self, session_client, connection, url, head):
        with mock.patch(REQUEST_PATH) as request:
            result = session_client.get(url("preview"), {"base": "main", "head": head})

        assert result.status_code == status.HTTP_400_BAD_REQUEST
        request.assert_not_called()


@pytest.mark.contract
@pytest.mark.django_db
class TestCreatePullRequest:
    def create(self, client, url, github_response, **data):
        github = FakeGitHub({("POST", "/repos/truncore/plane/pulls"): github_response})
        payload = {"base": "main", "head": "feat/scrum-1-pay-by-link", "title": "[SCRUM-1] Pay by link", **data}
        with mock.patch(REQUEST_PATH, side_effect=github):
            return client.post(url("pull-requests"), payload, format="json"), github

    def test_opens_links_and_moves_the_work_item(self, session_client, connection, item, url, create_user, activity):
        result, github = self.create(session_client, url, created_pull_request(), body="Work item: http://plane/x")

        assert result.status_code == status.HTTP_201_CREATED, result.data
        method, path, kwargs = github.calls[0]
        assert kwargs["json"] == {
            "base": "main",
            "head": "feat/scrum-1-pay-by-link",
            "title": "[SCRUM-1] Pay by link",
            "body": "Work item: http://plane/x",
        }
        record = PullRequest.objects.get(issue=item)
        assert (record.number, record.state) == (7, "open")
        assert IssueLink.objects.filter(issue=item, url=record.url).exists()
        item.refresh_from_db()
        assert item.state.name == "In Review"
        state_update = next(c for c in activity.delay.call_args_list if c.kwargs["type"] == "issue.activity.updated")
        assert state_update.kwargs["actor_id"] == str(create_user.id)

    @pytest.mark.parametrize(
        "message, code",
        [
            ("No commits between main and feat/scrum-1-pay-by-link", "no_commits"),
            ("A pull request already exists for truncore:feat/scrum-1-pay-by-link.", "pr_exists"),
            ("Protected branch update failed for refs/heads/main", "protected_branch"),
        ],
    )
    def test_github_validation_errors_are_explained(self, session_client, connection, item, url, message, code):
        rejected = response(422, {"message": "Validation Failed", "errors": [{"message": message}]})

        result, _ = self.create(session_client, url, rejected)

        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert result.data["code"] == code
        assert not PullRequest.objects.exists()

    def test_bad_token(self, session_client, connection, item, url):
        result, _ = self.create(session_client, url, response(401))

        assert result.data["code"] == "bad_token"

    def test_github_unreachable(self, session_client, connection, item, url):
        with mock.patch(REQUEST_PATH, side_effect=requests.ConnectionError()):
            result = session_client.post(
                url("pull-requests"), {"base": "main", "head": "feat/x", "title": "x"}, format="json"
            )

        assert result.data["code"] == "unreachable"

    def test_not_connected(self, session_client, item, url):
        result = session_client.post(
            url("pull-requests"), {"base": "main", "head": "feat/x", "title": "x"}, format="json"
        )

        assert result.data["code"] == "not_connected"

    def test_title_is_required(self, session_client, connection, item, url):
        result = session_client.post(url("pull-requests"), {"base": "main", "head": "feat/x"}, format="json")

        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "title" in result.data


@pytest.mark.contract
@pytest.mark.django_db
class TestWhoCanOpenPullRequests:
    def client_with_role(self, workspace, project, role):
        user = UserFactory()
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=max(role, 5))
        if role:
            ProjectMember.objects.create(project=project, member=user, workspace=workspace, role=role)
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    @pytest.mark.parametrize("role", [5, 0], ids=["guest", "not a project member"])
    def test_without_edit_access_nothing_reaches_github(self, workspace, project, connection, item, url, role):
        client = self.client_with_role(workspace, project, role)

        with mock.patch(REQUEST_PATH) as request:
            responses = [
                client.get(url("branches")),
                client.get(url("preview"), {"base": "main", "head": "feat/x"}),
                client.post(url("pull-requests"), {"base": "main", "head": "feat/x", "title": "x"}, format="json"),
            ]

        assert {r.status_code for r in responses} == {status.HTTP_403_FORBIDDEN}
        request.assert_not_called()

    def test_project_members_can_open_them(self, workspace, project, connection, item, url):
        client = self.client_with_role(workspace, project, 15)

        with mock.patch(REQUEST_PATH, side_effect=FakeGitHub({("POST", "/graphql"): branches_graphql()})):
            assert client.get(url("branches")).status_code == status.HTTP_200_OK
