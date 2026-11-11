# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.engineering.views import (
    GitHubAccountEndpoint,
    WorkItemPullRequestDetailsEndpoint,
    WorkItemPullRequestMergeEndpoint,
    WorkItemPullRequestReviewEndpoint,
    WorkItemPullRequestReviewersEndpoint,
    GitHubConnectionEndpoint,
    GitHubConnectionTestEndpoint,
    GitHubWebhookEndpoint,
    StoryProgressEndpoint,
    WorkItemBranchesEndpoint,
    WorkItemGitHubEndpoint,
    WorkItemPullRequestCreateEndpoint,
    WorkItemPullRequestPreviewEndpoint,
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
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/branches/",
        WorkItemBranchesEndpoint.as_view(),
        name="work-item-github-branches",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/preview/",
        WorkItemPullRequestPreviewEndpoint.as_view(),
        name="work-item-github-preview",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/pull-requests/",
        WorkItemPullRequestCreateEndpoint.as_view(),
        name="work-item-github-pull-requests",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/pull-requests/<uuid:pull_request_id>/",
        WorkItemPullRequestDetailsEndpoint.as_view(),
        name="work-item-pull-request",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/pull-requests/<uuid:pull_request_id>/reviews/",
        WorkItemPullRequestReviewEndpoint.as_view(),
        name="work-item-pull-request-review",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/pull-requests/<uuid:pull_request_id>/reviewers/",
        WorkItemPullRequestReviewersEndpoint.as_view(),
        name="work-item-pull-request-reviewers",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/github/pull-requests/<uuid:pull_request_id>/merge/",
        WorkItemPullRequestMergeEndpoint.as_view(),
        name="work-item-pull-request-merge",
    ),
    path("users/me/github/", GitHubAccountEndpoint.as_view(), name="user-github-account"),
    path("github/webhook/", GitHubWebhookEndpoint.as_view(), name="github-webhook"),
]
