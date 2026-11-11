# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db.models import Count, Q

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions import ROLE, allow_permission
from plane.app.views.base import BaseAPIView
from plane.db.models import Issue, StateGroup
from plane.db.models.issue_type import BUILT_IN_WORK_ITEM_TYPE_SOURCE
from plane.engineering.work_item_rules import USER_STORY


class StoryProgressEndpoint(BaseAPIView):
    """How many of each User Story's tasks are done, for every story in a project."""

    use_read_replica = True

    @allow_permission([ROLE.ADMIN, ROLE.MEMBER])
    def get(self, request, slug, project_id):
        rows = (
            Issue.issue_objects.filter(
                workspace__slug=slug,
                project_id=project_id,
                parent__type__external_source=BUILT_IN_WORK_ITEM_TYPE_SOURCE,
                parent__type__external_id=USER_STORY,
            )
            .values("parent_id")
            .annotate(total=Count("id"), completed=Count("id", filter=Q(state__group=StateGroup.COMPLETED.value)))
        )
        progress = {str(row["parent_id"]): {"total": row["total"], "completed": row["completed"]} for row in rows}
        return Response(progress, status=status.HTTP_200_OK)
