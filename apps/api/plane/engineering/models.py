# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import uuid

# Django imports
from django.conf import settings
from django.db import models
from django.db.models import Q

# Module imports
from plane.db.mixins import TimeAuditModel
from plane.db.models import ProjectBaseModel
from plane.license.utils.encryption import decrypt_data, encrypt_data


class WorkflowMode(models.TextChoices):
    TRUNK_BASED = "trunk_based", "Trunk-based"
    FEATURE_BRANCHES = "feature_branches", "Feature branches"


class GitHubConnection(ProjectBaseModel):
    """A project's link to one GitHub repository.

    The token and webhook secret are stored encrypted and never sent back to the browser.
    Kept separate from how Plane talks to GitHub, so a GitHub App can later supply the token instead.
    """

    repository_owner = models.CharField(max_length=100)
    repository_name = models.CharField(max_length=100)
    encrypted_token = models.TextField()
    encrypted_webhook_secret = models.TextField()
    workflow_mode = models.CharField(max_length=30, choices=WorkflowMode.choices, default=WorkflowMode.TRUNK_BASED)
    # The trunk in trunk-based mode, otherwise the default branch pull requests go into
    base_branch = models.CharField(max_length=255, default="main")
    # Where a work item moves when its pull request is opened or reopened, and when all are merged
    review_state = models.ForeignKey("db.State", on_delete=models.SET_NULL, null=True, related_name="+")
    merged_state = models.ForeignKey("db.State", on_delete=models.SET_NULL, null=True, related_name="+")
    # Trunk-based warnings
    branch_age_limit_days = models.PositiveSmallIntegerField(default=2)
    large_pr_lines = models.PositiveIntegerField(default=400)

    class Meta:
        db_table = "engineering_github_connections"
        constraints = [
            models.UniqueConstraint(
                fields=["project"],
                condition=Q(deleted_at__isnull=True),
                name="github_connection_unique_project_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return f"{self.repository_full_name} <{self.project_id}>"

    @property
    def repository_full_name(self):
        return f"{self.repository_owner}/{self.repository_name}"

    @property
    def token(self):
        return decrypt_data(self.encrypted_token)

    @token.setter
    def token(self, value):
        self.encrypted_token = encrypt_data(value)

    @property
    def webhook_secret(self):
        return decrypt_data(self.encrypted_webhook_secret)

    @webhook_secret.setter
    def webhook_secret(self, value):
        self.encrypted_webhook_secret = encrypt_data(value)


class PullRequestState(models.TextChoices):
    OPEN = "open", "Open"
    DRAFT = "draft", "Draft"
    MERGED = "merged", "Merged"
    CLOSED = "closed", "Closed"


class PullRequest(ProjectBaseModel):
    """A GitHub pull request linked to a work item, kept up to date from webhook events."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="pull_requests")
    repository_full_name = models.CharField(max_length=201)
    number = models.PositiveIntegerField()
    title = models.CharField(max_length=1024)
    url = models.URLField(max_length=1024)
    head_branch = models.CharField(max_length=255)
    base_branch = models.CharField(max_length=255)
    state = models.CharField(max_length=20, choices=PullRequestState.choices, default=PullRequestState.OPEN)
    author_login = models.CharField(max_length=100, blank=True)
    additions = models.PositiveIntegerField(null=True)
    deletions = models.PositiveIntegerField(null=True)
    changed_files = models.PositiveIntegerField(null=True)
    merged_at = models.DateTimeField(null=True)
    closed_at = models.DateTimeField(null=True)
    # GitHub's own last-change time, to ignore events that arrive out of order
    github_updated_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "engineering_pull_requests"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "repository_full_name", "number"],
                condition=Q(deleted_at__isnull=True),
                name="pull_request_unique_issue_repository_number_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return f"{self.repository_full_name}#{self.number}"


class LinkedCommit(ProjectBaseModel):
    """A commit on the trunk that mentions a work item."""

    issue = models.ForeignKey("db.Issue", on_delete=models.CASCADE, related_name="linked_commits")
    repository_full_name = models.CharField(max_length=201)
    sha = models.CharField(max_length=40)
    branch = models.CharField(max_length=255)
    message = models.TextField()
    url = models.URLField(max_length=1024)
    author_name = models.CharField(max_length=255, blank=True)
    author_login = models.CharField(max_length=100, blank=True)
    committed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "engineering_linked_commits"
        ordering = ("-committed_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["issue", "sha"],
                condition=Q(deleted_at__isnull=True),
                name="linked_commit_unique_issue_sha_when_deleted_at_null",
            )
        ]

    def __str__(self):
        return self.sha[:7]


class DeliveryStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class GitHubWebhookDelivery(TimeAuditModel):
    """A verified webhook from GitHub. The unique delivery id stops a redelivered event from applying twice."""

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    delivery_id = models.CharField(max_length=100, unique=True)
    event = models.CharField(max_length=50)
    payload = models.JSONField()
    connection_ids = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.RECEIVED)
    error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "engineering_github_webhook_deliveries"

    def __str__(self):
        return f"{self.event} {self.delivery_id}"


class GitHubAccount(TimeAuditModel):
    """A person's own GitHub access, so reviews, merges and new pull requests happen as them.

    Either a GitHub App user token (expires, has a refresh token) or a pasted personal token (no expiry).
    """

    id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="github_account")
    login = models.CharField(max_length=100)
    encrypted_token = models.TextField()
    encrypted_refresh_token = models.TextField(blank=True, default="")
    expires_at = models.DateTimeField(null=True)

    class Meta:
        db_table = "engineering_github_accounts"

    def __str__(self):
        return self.login

    @property
    def token(self):
        return decrypt_data(self.encrypted_token)

    @token.setter
    def token(self, value):
        self.encrypted_token = encrypt_data(value)

    @property
    def refresh_token(self):
        return decrypt_data(self.encrypted_refresh_token)

    @refresh_token.setter
    def refresh_token(self, value):
        self.encrypted_refresh_token = encrypt_data(value)
