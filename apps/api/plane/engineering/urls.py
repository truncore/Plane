# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.engineering.views import StoryProgressEndpoint

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/story-progress/",
        StoryProgressEndpoint.as_view(),
        name="project-story-progress",
    ),
]
