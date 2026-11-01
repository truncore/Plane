# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import migrations

# Frozen copy of plane.db.models.issue_type.BUILT_IN_WORK_ITEM_TYPES: migrations must not import live models.
SOURCE = "plane"
BUILT_IN_TYPES = [
    {"external_id": "user_story", "name": "User Story", "is_default": False},
    {"external_id": "task", "name": "Task", "is_default": True},
]
BATCH_SIZE = 500


def seed_built_in_types(apps, schema_editor):
    """Give every project the built-in types and make Task the type of every untyped work item."""
    Issue = apps.get_model("db", "Issue")
    IssueType = apps.get_model("db", "IssueType")
    Project = apps.get_model("db", "Project")
    ProjectIssueType = apps.get_model("db", "ProjectIssueType")

    types_by_workspace = {}
    for project in Project._base_manager.only("id", "workspace_id").iterator(chunk_size=BATCH_SIZE):
        workspace_types = types_by_workspace.get(project.workspace_id)
        if workspace_types is None:
            workspace_types = [
                (
                    IssueType._base_manager.get_or_create(
                        workspace_id=project.workspace_id,
                        external_source=SOURCE,
                        external_id=built_in["external_id"],
                        defaults={"name": built_in["name"], "is_default": built_in["is_default"]},
                    )[0],
                    built_in["is_default"],
                )
                for built_in in BUILT_IN_TYPES
            ]
            types_by_workspace[project.workspace_id] = workspace_types

        for issue_type, is_default in workspace_types:
            ProjectIssueType._base_manager.get_or_create(
                project_id=project.id,
                issue_type_id=issue_type.id,
                deleted_at=None,
                defaults={"workspace_id": project.workspace_id, "is_default": is_default},
            )
            if is_default:
                Issue._base_manager.filter(project_id=project.id, type__isnull=True).update(type_id=issue_type.id)


def remove_built_in_types(apps, schema_editor):
    Issue = apps.get_model("db", "Issue")
    IssueType = apps.get_model("db", "IssueType")
    ProjectIssueType = apps.get_model("db", "ProjectIssueType")

    built_in_types = IssueType._base_manager.filter(external_source=SOURCE)
    Issue._base_manager.filter(type__in=built_in_types).update(type_id=None)
    ProjectIssueType._base_manager.filter(issue_type__in=built_in_types).delete()
    built_in_types.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("db", "0125_reset_project_deploy_board_identity"),
    ]

    operations = [
        migrations.RunPython(seed_built_in_types, remove_built_in_types),
    ]
