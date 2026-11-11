# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models
from django.db.models import Q

# Module imports
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
