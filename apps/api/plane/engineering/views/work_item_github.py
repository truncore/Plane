# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.engineering.models import LinkedCommit, PullRequest
from plane.engineering.serializers import LinkedCommitSerializer, PullRequestSerializer


class WorkItemGitHubEndpoint(BaseAPIView):
    """The pull requests and trunk commits linked to a work item."""

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id, issue_id):
        scope = {"workspace__slug": slug, "project_id": project_id, "issue_id": issue_id}
        return Response(
            {
                "pull_requests": PullRequestSerializer(PullRequest.objects.filter(**scope), many=True).data,
                "commits": LinkedCommitSerializer(LinkedCommit.objects.filter(**scope), many=True).data,
            },
            status=status.HTTP_200_OK,
        )
