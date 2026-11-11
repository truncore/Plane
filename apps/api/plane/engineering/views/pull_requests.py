# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue
from plane.engineering.github.client import GitHubError
from plane.engineering.github.pull_requests import open_pull_request, preview_pull_request, work_item_branches
from plane.engineering.serializers import (
    CreatePullRequestSerializer,
    PullRequestBranchesSerializer,
    PullRequestSerializer,
)

from .github import get_connection, github_error_response, not_connected_response


class WorkItemPullRequestBaseEndpoint(BaseAPIView):
    """Shared lookups for opening a pull request from a work item. Only people who can edit work items may."""

    def get_work_item(self, slug, project_id, issue_id):
        return (
            Issue.issue_objects.filter(workspace__slug=slug, project_id=project_id, pk=issue_id)
            .select_related("project", "state", "workspace")
            .first()
        )


class WorkItemBranchesEndpoint(WorkItemPullRequestBaseEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        connection = get_connection(slug, project_id)
        issue = self.get_work_item(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)
        if connection is None:
            return not_connected_response()
        try:
            branches = work_item_branches(connection, issue)
        except GitHubError as error:
            return github_error_response(error)
        return Response(
            {
                "branches": branches,
                "base_branch": connection.base_branch,
                "workflow_mode": connection.workflow_mode,
                "branch_age_limit_days": connection.branch_age_limit_days,
                "large_pr_lines": connection.large_pr_lines,
            },
            status=status.HTTP_200_OK,
        )


class WorkItemPullRequestPreviewEndpoint(WorkItemPullRequestBaseEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        connection = get_connection(slug, project_id)
        if connection is None:
            return not_connected_response()
        serializer = PullRequestBranchesSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            preview = preview_pull_request(connection, **serializer.validated_data)
        except GitHubError as error:
            return github_error_response(error)
        return Response(preview, status=status.HTTP_200_OK)


class WorkItemPullRequestCreateEndpoint(WorkItemPullRequestBaseEndpoint):
    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def post(self, request, slug, project_id, issue_id):
        connection = get_connection(slug, project_id)
        issue = self.get_work_item(slug, project_id, issue_id)
        if issue is None:
            return Response({"error": "Work item not found."}, status=status.HTTP_404_NOT_FOUND)
        if connection is None:
            return not_connected_response()
        serializer = CreatePullRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            record = open_pull_request(connection, issue, request.user, **serializer.validated_data)
        except GitHubError as error:
            return github_error_response(error)
        return Response(PullRequestSerializer(record).data, status=status.HTTP_201_CREATED)
