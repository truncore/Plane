# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.engineering.github.client import GitHubError
from plane.engineering.github.connection import check_connection
from plane.engineering.models import GitHubConnection
from plane.engineering.serializers import GitHubConnectionSerializer

WEBHOOK_PATH = "/api/github/webhook/"


def get_connection(slug, project_id):
    return GitHubConnection.objects.filter(workspace__slug=slug, project_id=project_id).first()


def github_error_response(error):
    return Response({"code": error.code, "error": error.message}, status=status.HTTP_400_BAD_REQUEST)


def not_connected_response():
    return Response(
        {"code": "not_connected", "error": "Connect this project to GitHub in its settings first."},
        status=status.HTTP_400_BAD_REQUEST,
    )


class GitHubConnectionEndpoint(BaseAPIView):
    """A project's GitHub settings. Members can see whether GitHub is connected; admins change it."""

    def settings_response(self, request, connection, status_code=status.HTTP_200_OK):
        return Response(
            {
                "connection": GitHubConnectionSerializer(connection).data if connection else None,
                "webhook_url": request.build_absolute_uri(WEBHOOK_PATH),
            },
            status=status_code,
        )

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        return self.settings_response(request, get_connection(slug, project_id))

    @allow_permission([ROLE.ADMIN])
    def put(self, request, slug, project_id):
        connection = get_connection(slug, project_id)
        serializer = GitHubConnectionSerializer(
            connection, data=request.data, partial=connection is not None, context={"project_id": project_id}
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return self.settings_response(request, serializer.save())

    @allow_permission([ROLE.ADMIN])
    def delete(self, request, slug, project_id):
        connection = get_connection(slug, project_id)
        if connection:
            connection.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GitHubConnectionTestEndpoint(BaseAPIView):
    @allow_permission([ROLE.ADMIN])
    def post(self, request, slug, project_id):
        connection = get_connection(slug, project_id)
        if connection is None:
            return not_connected_response()
        try:
            return Response(check_connection(connection), status=status.HTTP_200_OK)
        except GitHubError as error:
            return github_error_response(error)
