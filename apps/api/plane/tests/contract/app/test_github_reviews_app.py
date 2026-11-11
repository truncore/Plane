# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Personal GitHub accounts, and reviewing and merging a work item's pull request from Plane."""

from unittest import mock

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Issue, Project, ProjectMember, State, WorkspaceMember
from plane.engineering.models import GitHubAccount, PullRequest
from plane.engineering.serializers import GitHubConnectionSerializer
from plane.tests.factories import UserFactory
from plane.tests.github_fakes import REQUEST_PATH, FakeGitHub, response

REPOSITORY = "/repos/truncore/plane"
ACCOUNT_URL = "/api/users/me/github/"


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    State.objects.create(name="Todo", group="unstarted", sequence=25000, project=project, default=True)
    State.objects.create(name="Done", group="completed", sequence=45000, project=project)
    data = {"repository_owner": "truncore", "repository_name": "plane", "token": "project-token", "webhook_secret": "s"}
    serializer = GitHubConnectionSerializer(data=data, context={"project_id": project.id})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return project


@pytest.fixture
def record(project):
    item = Issue.objects.create(name="Pay by link", project=project, workspace=project.workspace)
    return PullRequest.objects.create(
        issue=item,
        project=project,
        repository_full_name="truncore/plane",
        number=7,
        title="[SCRUM-1] Pay by link",
        url="https://github.com/truncore/plane/pull/7",
        head_branch="feat/scrum-1",
        base_branch="main",
    )


@pytest.fixture
def url(record):
    base = f"/api/workspaces/{record.workspace.slug}/projects/{record.project_id}/issues/{record.issue_id}"
    return lambda action="": f"{base}/github/pull-requests/{record.id}/{action}"


@pytest.fixture
def my_account(create_user):
    account = GitHubAccount(user=create_user, login="mariam")
    account.token = "personal-token"
    account.save()
    return account


@pytest.fixture(autouse=True)
def activity():
    with (
        mock.patch("plane.engineering.work_items.issue_activity"),
        mock.patch("plane.engineering.work_items.model_activity"),
    ):
        yield


def github_pull_request(author="octocat", mergeable_state="clean", draft=False, merged=False):
    return {
        "number": 7,
        "title": "[SCRUM-1] Pay by link",
        "html_url": "https://github.com/truncore/plane/pull/7",
        "state": "closed" if merged else "open",
        "draft": draft,
        "merged": merged,
        "mergeable_state": mergeable_state,
        "updated_at": timezone.now().isoformat(),
        "head": {"ref": "feat/scrum-1", "sha": "abc123"},
        "base": {"ref": "main"},
        "user": {"login": author},
        "requested_reviewers": [{"login": "lina"}],
    }


def details_routes(pull_request, reviews=()):
    return {
        ("GET", f"{REPOSITORY}/pulls/7"): response(json=pull_request),
        ("GET", f"{REPOSITORY}/pulls/7/reviews"): response(json=list(reviews)),
        ("GET", f"{REPOSITORY}/commits/abc123/check-runs"): response(
            json={"check_runs": [{"name": "tests", "status": "completed", "conclusion": "success", "html_url": "u"}]}
        ),
    }


@pytest.mark.contract
@pytest.mark.django_db
class TestPersonalAccount:
    def test_connect_checks_the_token_and_never_returns_it(self, session_client, create_user):
        github = FakeGitHub({("GET", "/user"): response(json={"login": "mariam-h"})})
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.put(ACCOUNT_URL, {"token": "personal-token"}, format="json")

        assert result.status_code == status.HTTP_200_OK
        assert result.data["login"] == "mariam-h"
        account = GitHubAccount.objects.get(user=create_user)
        assert account.token == "personal-token" and "personal-token" not in account.encrypted_token
        assert github.calls[0][2]["headers"]["Authorization"] == "Bearer personal-token"
        assert session_client.get(ACCOUNT_URL).data["login"] == "mariam-h"

    def test_rejected_token_is_not_saved(self, session_client, create_user):
        with mock.patch(REQUEST_PATH, side_effect=FakeGitHub({("GET", "/user"): response(401)})):
            result = session_client.put(ACCOUNT_URL, {"token": "wrong"}, format="json")

        assert result.data["code"] == "bad_token"
        assert not GitHubAccount.objects.exists()

    def test_disconnect(self, session_client, my_account):
        assert session_client.delete(ACCOUNT_URL).status_code == status.HTTP_204_NO_CONTENT
        assert session_client.get(ACCOUNT_URL).data["login"] is None


@pytest.mark.contract
@pytest.mark.django_db
class TestDetails:
    def test_reviews_checks_and_what_i_can_do(self, session_client, record, url, my_account):
        reviews = [
            {"user": {"login": "omar"}, "state": "APPROVED"},
            {"user": {"login": "omar"}, "state": "COMMENTED"},
            {"user": {"login": "sara"}, "state": "APPROVED"},
            {"user": {"login": "sara"}, "state": "CHANGES_REQUESTED"},
        ]
        github = FakeGitHub(details_routes(github_pull_request(), reviews))
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.get(url())

        assert result.status_code == status.HTTP_200_OK, result.data
        assert result.data["reviewers"] == [
            {"login": "omar", "state": "APPROVED"},
            {"login": "sara", "state": "CHANGES_REQUESTED"},
            {"login": "lina", "state": "PENDING"},
        ]
        assert result.data["checks"] == [{"name": "tests", "status": "completed", "conclusion": "success", "url": "u"}]
        assert result.data["files_url"] == "https://github.com/truncore/plane/pull/7/files"
        assert (result.data["acting_as"], result.data["can_review"], result.data["can_merge"]) == ("mariam", True, True)
        assert github.calls[0][2]["headers"]["Authorization"] == "Bearer personal-token"

    @pytest.mark.parametrize(
        "pull_request, can_review, can_merge",
        [
            (github_pull_request(author="mariam"), False, True),
            (github_pull_request(mergeable_state="dirty"), True, False),
            (github_pull_request(draft=True, mergeable_state="draft"), True, False),
        ],
        ids=["own pull request", "merge conflicts", "draft"],
    )
    def test_actions_follow_github_rules(self, session_client, url, my_account, pull_request, can_review, can_merge):
        with mock.patch(REQUEST_PATH, side_effect=FakeGitHub(details_routes(pull_request))):
            result = session_client.get(url())

        assert (result.data["can_review"], result.data["can_merge"]) == (can_review, can_merge)

    def test_without_a_personal_account_it_reads_with_the_project_token(self, session_client, url):
        github = FakeGitHub(details_routes(github_pull_request()))
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.get(url())

        assert (result.data["acting_as"], result.data["can_review"], result.data["can_merge"]) == (None, False, False)
        assert github.calls[0][2]["headers"]["Authorization"] == "Bearer project-token"


@pytest.mark.contract
@pytest.mark.django_db
class TestActions:
    def test_actions_need_a_personal_account(self, session_client, url):
        with mock.patch(REQUEST_PATH) as request:
            result = session_client.post(url("reviews/"), {"event": "APPROVE"}, format="json")

        assert result.data["code"] == "no_personal_account"
        request.assert_not_called()

    def test_approve(self, session_client, url, my_account):
        github = FakeGitHub({("POST", f"{REPOSITORY}/pulls/7/reviews"): response(json={})})
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.post(url("reviews/"), {"event": "APPROVE"}, format="json")

        assert result.status_code == status.HTTP_204_NO_CONTENT
        assert github.calls[0][2]["json"] == {"event": "APPROVE", "body": ""}
        assert github.calls[0][2]["headers"]["Authorization"] == "Bearer personal-token"

    def test_requesting_changes_needs_a_comment(self, session_client, url, my_account):
        result = session_client.post(url("reviews/"), {"event": "REQUEST_CHANGES"}, format="json")

        assert result.status_code == status.HTTP_400_BAD_REQUEST
        assert "body" in result.data

    def test_request_reviewers(self, session_client, url, my_account):
        github = FakeGitHub({("POST", f"{REPOSITORY}/pulls/7/requested_reviewers"): response(json={})})
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.post(url("reviewers/"), {"reviewers": ["omar-f"]}, format="json")

        assert result.status_code == status.HTTP_204_NO_CONTENT
        assert github.calls[0][2]["json"] == {"reviewers": ["omar-f"]}

    def test_reviewer_names_are_checked(self, session_client, url, my_account):
        result = session_client.post(url("reviewers/"), {"reviewers": ["../admin"]}, format="json")

        assert result.status_code == status.HTTP_400_BAD_REQUEST

    def test_merge_moves_the_work_item_to_done(self, session_client, record, url, my_account):
        github = FakeGitHub(
            {
                ("PUT", f"{REPOSITORY}/pulls/7/merge"): response(json={"merged": True}),
                ("GET", f"{REPOSITORY}/pulls/7"): response(json=github_pull_request(merged=True)),
            }
        )
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.post(url("merge/"), {"method": "squash"}, format="json")

        assert result.status_code == status.HTTP_204_NO_CONTENT, result.data
        assert github.calls[0][2]["json"] == {"merge_method": "squash"}
        record.refresh_from_db()
        assert record.state == "merged"
        assert Issue.objects.get(pk=record.issue_id).state.name == "Done"

    def test_merge_refused_by_github_is_explained(self, session_client, url, my_account):
        github = FakeGitHub({("PUT", f"{REPOSITORY}/pulls/7/merge"): response(405)})
        with mock.patch(REQUEST_PATH, side_effect=github):
            result = session_client.post(url("merge/"), {"method": "merge"}, format="json")

        assert result.data["code"] == "not_mergeable"

    def test_unknown_merge_method(self, session_client, url, my_account):
        result = session_client.post(url("merge/"), {"method": "fast-forward"}, format="json")

        assert result.status_code == status.HTTP_400_BAD_REQUEST

    def test_guests_cannot_act(self, workspace, project, url):
        guest = UserFactory()
        WorkspaceMember.objects.create(workspace=workspace, member=guest, role=5)
        ProjectMember.objects.create(project=project, member=guest, workspace=workspace, role=5)
        client = APIClient()
        client.force_authenticate(user=guest)

        with mock.patch(REQUEST_PATH) as request:
            responses = [client.get(url()), client.post(url("merge/"), {"method": "merge"}, format="json")]

        assert {r.status_code for r in responses} == {status.HTTP_403_FORBIDDEN}
        request.assert_not_called()
