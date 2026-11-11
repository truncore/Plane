# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.engineering.views import (
    GitHubConnectionEndpoint,
    GitHubConnectionTestEndpoint,
    GitHubWebhookEndpoint,
    StoryProgressEndpoint,
    WorkItemGitHubEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/story-progress/",
        StoryProgressEndpoint.as_view(),
        name="project-story-progress",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/github/",
        GitHubConnectionEndpoint.as_view(),
        name="project-github-connection",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/github/test/",
        GitHubConnectionTestEndpoint.as_view(),
        name="project-github-connection-test",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/",
        WorkItemGitHubEndpoint.as_view(),
        name="work-item-github",
    ),
    path("github/webhook/", GitHubWebhookEndpoint.as_view(), name="github-webhook"),
]
