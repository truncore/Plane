# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Project GitHub settings: secrets stay secret, defaults, validation, permissions and the connection test."""

from unittest import mock

import pytest
import requests
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Project, ProjectMember, State, WorkspaceMember
from plane.engineering.github.client import is_valid_branch
from plane.engineering.models import GitHubConnection
from plane.tests.factories import UserFactory

REQUEST_PATH = "plane.engineering.github.client.requests.request"
TOKEN = "github_pat_secret_token"
SECRET = "webhook-secret-value"


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    State.objects.create(name="In Progress", group="started", sequence=35000, project=project)
    State.objects.create(name="Done", group="completed", sequence=45000, project=project)
    return project


@pytest.fixture
def url(workspace, project):
    return f"/api/workspaces/{workspace.slug}/projects/{project.id}/github/"


@pytest.fixture
def connect(session_client, url):
    def connect(**overrides):
        data = {"repository_owner": "truncore", "repository_name": "plane", "token": TOKEN, "webhook_secret": SECRET}
        return session_client.put(url, {**data, **overrides}, format="json")

    return connect


def github_response(status_code=200, json=None, headers=None):
    response = mock.Mock(status_code=status_code, ok=status_code < 400, headers=headers or {}, content=b"{}")
    response.json.return_value = json or {}
    return response


REPOSITORY = {"full_name": "truncore/plane", "private": True, "default_branch": "main", "permissions": {"push": True}}


@pytest.mark.contract
@pytest.mark.django_db
class TestGitHubSettings:
    def test_not_connected_shows_the_webhook_url(self, session_client, url):
        response = session_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["connection"] is None
        assert response.data["webhook_url"].endswith("/api/github/webhook/")

    def test_connect_stores_secrets_encrypted_and_never_returns_them(self, connect, project):
        response = connect()

        assert response.status_code == status.HTTP_200_OK, response.data
        settings = response.data["connection"]
        assert settings["has_token"] and settings["has_webhook_secret"]
        assert TOKEN not in str(response.data) and SECRET not in str(response.data)
        connection = GitHubConnection.objects.get(project=project)
        assert TOKEN not in connection.encrypted_token
        assert connection.token == TOKEN and connection.webhook_secret == SECRET

    def test_connect_uses_trunk_based_mode_and_default_states(self, connect, project):
        settings = connect().data["connection"]

        review_state = State.objects.get(pk=settings["review_state_id"])
        assert (review_state.name, review_state.group) == ("In Review", "started")
        assert State.objects.get(pk=settings["merged_state_id"]).name == "Done"
        assert settings["workflow_mode"] == "trunk_based"
        assert settings["base_branch"] == "main"
        assert (settings["branch_age_limit_days"], settings["large_pr_lines"]) == (2, 400)

    def test_existing_in_review_state_is_reused(self, connect, project):
        existing = State.objects.create(name="In review", group="started", sequence=36000, project=project)

        settings = connect().data["connection"]

        assert settings["review_state_id"] == existing.id
        assert State.objects.filter(project=project, name__iexact="in review").count() == 1

    def test_first_connect_needs_token_and_secret(self, connect):
        response = connect(token="", webhook_secret="")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "token" in response.data

    def test_blank_token_on_update_keeps_the_saved_one(self, connect, session_client, url, project):
        connect()

        response = session_client.put(url, {"token": "", "base_branch": "develop"}, format="json")

        assert response.status_code == status.HTTP_200_OK, response.data
        connection = GitHubConnection.objects.get(project=project)
        assert connection.token == TOKEN
        assert connection.base_branch == "develop"

    def test_new_token_replaces_the_saved_one(self, connect, session_client, url, project):
        connect()

        session_client.put(url, {"token": "new-token"}, format="json")

        assert GitHubConnection.objects.get(project=project).token == "new-token"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"repository_owner": "bad owner"},
            {"repository_name": ".."},
            {"repository_name": "x/../../admin"},
            {"base_branch": "feature/../main"},
            {"base_branch": "has space"},
            {"workflow_mode": "waterfall"},
        ],
    )
    def test_invalid_input_is_rejected(self, connect, overrides):
        assert connect(**overrides).status_code == status.HTTP_400_BAD_REQUEST

    def test_mapping_states_must_fit_their_group(self, connect, project):
        done = State.objects.get(project=project, name="Done")

        response = connect(review_state_id=str(done.id))

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "review_state_id" in response.data

    def test_mapping_state_from_another_project_is_rejected(self, connect, workspace, create_user):
        other = Project.objects.create(name="Other", identifier="OTHER", workspace=workspace, created_by=create_user)
        foreign = State.objects.create(name="Shipped", group="completed", project=other)

        assert connect(merged_state_id=str(foreign.id)).status_code == status.HTTP_400_BAD_REQUEST

    def test_disconnect(self, connect, session_client, url, project):
        connect()

        assert session_client.delete(url).status_code == status.HTTP_204_NO_CONTENT
        assert not GitHubConnection.objects.filter(project=project).exists()
        assert session_client.get(url).data["connection"] is None


@pytest.mark.contract
@pytest.mark.django_db
class TestGitHubSettingsPermissions:
    @pytest.fixture
    def member_client(self, workspace, project):
        member = UserFactory()
        WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
        ProjectMember.objects.create(project=project, member=member, workspace=workspace, role=15)
        client = APIClient()
        client.force_authenticate(user=member)
        return client

    def test_member_sees_settings_without_secrets_but_cannot_change_them(self, connect, member_client, url):
        connect()

        response = member_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert TOKEN not in str(response.data)
        assert member_client.put(url, {"base_branch": "dev"}, format="json").status_code == status.HTTP_403_FORBIDDEN
        assert member_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
        assert member_client.post(f"{url}test/").status_code == status.HTTP_403_FORBIDDEN

    def test_non_member_cannot_see_settings(self, connect, workspace, url):
        outsider = UserFactory()
        WorkspaceMember.objects.create(workspace=workspace, member=outsider, role=15)
        client = APIClient()
        client.force_authenticate(user=outsider)

        assert client.get(url).status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
@pytest.mark.django_db
class TestConnectionTest:
    @pytest.fixture
    def test_url(self, url):
        return f"{url}test/"

    def test_not_connected(self, session_client, test_url):
        response = session_client.post(test_url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "not_connected"

    def test_success_checks_repository_and_base_branch(self, connect, session_client, test_url):
        connect()

        with mock.patch(REQUEST_PATH, side_effect=[github_response(json=REPOSITORY), github_response()]) as request:
            response = session_client.post(test_url)

        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data == {"repository": "truncore/plane", "private": True, "default_branch": "main"}
        urls = [call.args[1] for call in request.call_args_list]
        assert urls == [
            "https://api.github.com/repos/truncore/plane",
            "https://api.github.com/repos/truncore/plane/branches/main",
        ]
        assert request.call_args.kwargs["headers"]["Authorization"] == f"Bearer {TOKEN}"

    @pytest.mark.parametrize(
        "responses, code",
        [
            ([github_response(401)], "bad_token"),
            ([github_response(404)], "repository_not_found"),
            ([github_response(403, headers={"x-ratelimit-remaining": "0"})], "rate_limited"),
            ([github_response(json={**REPOSITORY, "permissions": {"push": False}})], "no_push_permission"),
            ([github_response(json=REPOSITORY), github_response(404)], "branch_not_found"),
            ([requests.ConnectionError()], "unreachable"),
        ],
    )
    def test_failures_have_a_clear_reason(self, connect, session_client, test_url, responses, code):
        connect()

        with mock.patch(REQUEST_PATH, side_effect=responses):
            response = session_client.post(test_url)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == code
        assert response.data["error"]


@pytest.mark.unit
@pytest.mark.parametrize(
    "name, valid",
    [
        ("main", True),
        ("feat/PAY-12-reset-password", True),
        ("release-1.2", True),
        ("-main", False),
        ("feat//x", False),
        ("a..b", False),
        ("ends/", False),
        ("x.lock", False),
        ("with space", False),
        ("with~tilde", False),
        ("", False),
    ],
)
def test_branch_names(name, valid):
    assert is_valid_branch(name) is valid
