# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party modules
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import WorkspaceEntityPermission
from plane.app.serializers import IssueTypeSerializer
from plane.app.views.base import BaseAPIView
from plane.db.models import IssueType


class WorkspaceIssueTypesEndpoint(BaseAPIView):
    permission_classes = [WorkspaceEntityPermission]
    use_read_replica = True

    def get(self, request, slug):
        issue_types = IssueType.objects.filter(workspace__slug=slug, is_active=True).order_by("is_default", "name")
        return Response(IssueTypeSerializer(issue_types, many=True).data, status=status.HTTP_200_OK)
