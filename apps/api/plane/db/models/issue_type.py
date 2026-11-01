# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.db import models, transaction
from django.db.models import Q
from django.db.models.signals import post_save
from django.dispatch import receiver

# Module imports
from .project import Project, ProjectBaseModel
from .base import BaseModel
from .workspace import Workspace

# Built-in work item types are identified by external_source + external_id, never by name.
BUILT_IN_WORK_ITEM_TYPE_SOURCE = "plane"
BUILT_IN_WORK_ITEM_TYPES = [
    {"external_id": "user_story", "name": "User Story", "is_default": False},
    {"external_id": "task", "name": "Task", "is_default": True},
]


class IssueType(BaseModel):
    workspace = models.ForeignKey("db.Workspace", related_name="issue_types", on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    logo_props = models.JSONField(default=dict)
    is_epic = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    level = models.FloatField(default=0)
    external_source = models.CharField(max_length=255, null=True, blank=True)
    external_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Issue Type"
        verbose_name_plural = "Issue Types"
        db_table = "issue_types"

    def __str__(self):
        return self.name


class ProjectIssueType(ProjectBaseModel):
    issue_type = models.ForeignKey("db.IssueType", related_name="project_issue_types", on_delete=models.CASCADE)
    level = models.PositiveIntegerField(default=0)
    is_default = models.BooleanField(default=False)

    class Meta:
        unique_together = ["project", "issue_type", "deleted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "issue_type"],
                condition=Q(deleted_at__isnull=True),
                name="project_issue_type_unique_project_issue_type_when_deleted_at_null",
            )
        ]
        verbose_name = "Project Issue Type"
        verbose_name_plural = "Project Issue Types"
        db_table = "project_issue_types"
        ordering = ("project", "issue_type")

    def __str__(self):
        return f"{self.project} - {self.issue_type}"


def ensure_project_work_item_types(project):
    """Link the workspace's built-in work item types to the project, creating them if needed."""
    with transaction.atomic():
        # Serialize per workspace so concurrent project creation cannot duplicate the built-in types.
        Workspace.objects.select_for_update().filter(pk=project.workspace_id).first()
        for built_in_type in BUILT_IN_WORK_ITEM_TYPES:
            issue_type, _ = IssueType.objects.get_or_create(
                workspace_id=project.workspace_id,
                external_source=BUILT_IN_WORK_ITEM_TYPE_SOURCE,
                external_id=built_in_type["external_id"],
                defaults={"name": built_in_type["name"], "is_default": built_in_type["is_default"]},
            )
            ProjectIssueType.objects.get_or_create(
                project=project,
                issue_type=issue_type,
                defaults={"is_default": built_in_type["is_default"]},
            )


@receiver(post_save, sender=Project)
def create_project_work_item_types(sender, instance, created, **kwargs):
    if created:
        ensure_project_work_item_types(instance)
