# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from plane.app.serializers.base import BaseSerializer
from plane.db.models import Project, State, StateGroup
from plane.engineering.github.client import is_valid_branch, is_valid_repository
from plane.engineering.github.connection import default_review_state, first_state
from plane.engineering.models import GitHubConnection, LinkedCommit, PullRequest

SECRET_FIELDS = ("token", "webhook_secret")


class GitHubConnectionSerializer(BaseSerializer):
    """Project GitHub settings. The token and webhook secret can be written but are never read back."""

    token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    webhook_secret = serializers.CharField(write_only=True, required=False, allow_blank=True)
    review_state_id = serializers.PrimaryKeyRelatedField(
        source="review_state", queryset=State.objects.all(), required=False
    )
    merged_state_id = serializers.PrimaryKeyRelatedField(
        source="merged_state", queryset=State.objects.all(), required=False
    )
    repository_full_name = serializers.CharField(read_only=True)
    has_token = serializers.SerializerMethodField()
    has_webhook_secret = serializers.SerializerMethodField()

    class Meta:
        model = GitHubConnection
        fields = [
            "id",
            "repository_owner",
            "repository_name",
            "repository_full_name",
            "workflow_mode",
            "base_branch",
            "review_state_id",
            "merged_state_id",
            "branch_age_limit_days",
            "large_pr_lines",
            "token",
            "webhook_secret",
            "has_token",
            "has_webhook_secret",
        ]
        read_only_fields = ["id"]

    def get_has_token(self, connection):
        return bool(connection.encrypted_token)

    def get_has_webhook_secret(self, connection):
        return bool(connection.encrypted_webhook_secret)

    def validate(self, attrs):
        owner = attrs.get("repository_owner", getattr(self.instance, "repository_owner", None))
        name = attrs.get("repository_name", getattr(self.instance, "repository_name", None))
        if not is_valid_repository(owner, name):
            raise serializers.ValidationError(
                {"repository": "Enter the repository as owner/name, e.g. truncore/plane."}
            )
        if "base_branch" in attrs and not is_valid_branch(attrs["base_branch"]):
            raise serializers.ValidationError({"base_branch": "This isn't a valid branch name."})

        project_id = str(self.context["project_id"])
        for field, group in (("review_state", StateGroup.STARTED), ("merged_state", StateGroup.COMPLETED)):
            state = attrs.get(field)
            if state and (str(state.project_id) != project_id or state.group != group.value):
                raise serializers.ValidationError(
                    {f"{field}_id": f"Pick a state from this project's {group.label} group."}
                )

        if self.instance is None:
            for field in SECRET_FIELDS:
                if not attrs.get(field):
                    raise serializers.ValidationError({field: "This field is required."})
        return attrs

    def create(self, validated_data):
        project = Project.objects.get(pk=self.context["project_id"])
        validated_data.setdefault("review_state", default_review_state(project))
        validated_data.setdefault("merged_state", first_state(project, StateGroup.COMPLETED))
        connection = GitHubConnection(project=project)
        return self.update(connection, validated_data)

    def update(self, connection, validated_data):
        # A blank secret on update keeps the saved one
        for field in SECRET_FIELDS:
            value = validated_data.pop(field, "")
            if value:
                setattr(connection, field, value)
        for field, value in validated_data.items():
            setattr(connection, field, value)
        connection.save()
        return connection


class PullRequestSerializer(BaseSerializer):
    class Meta:
        model = PullRequest
        fields = [
            "id",
            "repository_full_name",
            "number",
            "title",
            "url",
            "head_branch",
            "base_branch",
            "state",
            "author_login",
            "additions",
            "deletions",
            "changed_files",
            "merged_at",
            "closed_at",
            "created_at",
        ]
        read_only_fields = fields


class LinkedCommitSerializer(BaseSerializer):
    class Meta:
        model = LinkedCommit
        fields = [
            "id",
            "repository_full_name",
            "sha",
            "branch",
            "message",
            "url",
            "author_name",
            "author_login",
            "committed_at",
        ]
        read_only_fields = fields
