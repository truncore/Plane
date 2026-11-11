# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.engineering.github.client import GitHubClient, GitHubError
from plane.engineering.github.reviews import (
    merge_pull_request,
    pull_request_details,
    request_reviewers,
    review_pull_request,
)
from plane.engineering.models import GitHubAccount, PullRequest
from plane.engineering.serializers import (
    GitHubAccountSerializer,
    MergeSerializer,
    RequestReviewersSerializer,
    ReviewSerializer,
)

from .github import get_connection, github_error_response, not_connected_response


class GitHubAccountEndpoint(BaseAPIView):
    """The signed-in person's own GitHub account. The token is checked with GitHub, stored encrypted, never returned."""

    def account_response(self, account, status_code=status.HTTP_200_OK):
        return Response({"login": account.login if account else None}, status=status_code)

    def get(self, request):
        return self.account_response(GitHubAccount.objects.filter(user=request.user).first())

    def put(self, request):
        serializer = GitHubAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        token = serializer.validated_data["token"]
        try:
            login = GitHubClient(token).get_user()["login"]
        except GitHubError as error:
            return github_error_response(error)
        account = GitHubAccount.objects.filter(user=request.user).first() or GitHubAccount(user=request.user)
        account.login = login
        account.token = token
        account.save()
        return self.account_response(account)

    def delete(self, request):
        GitHubAccount.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WorkItemPullRequestActionEndpoint(BaseAPIView):
    """Base for a pull request linked to a work item. Only people who can edit work items may act on it."""

    def run(self, slug, project_id, issue_id, pull_request_id, action):
        connection = get_connection(slug, project_id)
        if connection is None:
            return not_connected_response()
        record = (
            PullRequest.objects.filter(
                workspace__slug=slug, project_id=project_id, issue_id=issue_id, pk=pull_request_id
            )
            .select_related("issue__state", "issue__workspace")
            .first()
        )
        if record is None:
            return Response({"error": "Pull request not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            return action(connection, record)
        except GitHubError as error:
            return github_error_response(error)


class WorkItemPullRequestDetailsEndpoint(WorkItemPullRequestActionEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id, pull_request_id):
        def details(connection, record):
            return Response(pull_request_details(connection, record, request.user), status=status.HTTP_200_OK)

        return self.run(slug, project_id, issue_id, pull_request_id, details)


class WorkItemPullRequestReviewEndpoint(WorkItemPullRequestActionEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id, pull_request_id):
        serializer = ReviewSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        def review(connection, record):
            review_pull_request(connection, record, request.user, **serializer.validated_data)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return self.run(slug, project_id, issue_id, pull_request_id, review)


class WorkItemPullRequestReviewersEndpoint(WorkItemPullRequestActionEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id, pull_request_id):
        serializer = RequestReviewersSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        def ask(connection, record):
            request_reviewers(connection, record, request.user, **serializer.validated_data)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return self.run(slug, project_id, issue_id, pull_request_id, ask)


class WorkItemPullRequestMergeEndpoint(WorkItemPullRequestActionEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id, pull_request_id):
        serializer = MergeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        def merge(connection, record):
            merge_pull_request(connection, record, request.user, **serializer.validated_data)
            return Response(status=status.HTTP_204_NO_CONTENT)

        return self.run(slug, project_id, issue_id, pull_request_id, merge)
