# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Rules that make User Stories and Tasks behave differently.

- Story points go on User Stories only.
- A Task's parent is a User Story (or nothing); a User Story has no parent.

Only what a request changes is checked, so older data that breaks a rule can still be edited.
"""

# Third party imports
from rest_framework import serializers

# Module imports
from plane.db.models import Issue, ProjectIssueType
from plane.db.models.issue_type import BUILT_IN_WORK_ITEM_TYPE_SOURCE

USER_STORY = "user_story"
TASK = "task"

POINTS_ON_TASK = "Story points can only be set on User Stories."
STORY_WITH_PARENT = "A User Story can't be a sub-work item. Remove its parent first."
TASK_PARENT_NOT_STORY = "A Task can only be a sub-work item of a User Story."
STORY_WITH_TASKS = "This User Story has tasks under it. Move them to another story before making it a Task."


def work_item_type_key(issue_type):
    """The built-in key ("user_story" or "task") of a work item type, or None for any other type."""
    if issue_type is None or issue_type.external_source != BUILT_IN_WORK_ITEM_TYPE_SOURCE:
        return None
    return issue_type.external_id


def default_work_item_type(project_id):
    link = ProjectIssueType.objects.filter(project_id=project_id, is_default=True).select_related("issue_type").first()
    return link.issue_type if link else None


def apply_work_item_rules(attrs, project_id, instance=None):
    """Check a create or update of a work item (or draft) against the type rules.

    Raises a ValidationError when the change breaks a rule. Changing a work item with points to a Task
    clears its points; the cleared fields are returned so callers can record them in the activity history.
    """
    current_type = instance.type if instance else default_work_item_type(project_id)
    new_type = attrs.get("type", current_type)
    type_changed = instance is not None and new_type != current_type
    key = work_item_type_key(new_type)
    parent = attrs.get("parent", instance.parent if instance else None)
    checks_parent = "parent" in attrs or type_changed
    cleared = {}

    if key == USER_STORY and checks_parent and parent is not None:
        raise serializers.ValidationError(STORY_WITH_PARENT)

    if key == TASK:
        if attrs.get("estimate_point") is not None:
            raise serializers.ValidationError(POINTS_ON_TASK)
        if checks_parent and parent is not None and work_item_type_key(parent.type) != USER_STORY:
            raise serializers.ValidationError(TASK_PARENT_NOT_STORY)
        if type_changed:
            if isinstance(instance, Issue) and Issue.issue_objects.filter(parent=instance).exists():
                raise serializers.ValidationError(STORY_WITH_TASKS)
            if instance.estimate_point_id is not None and "estimate_point" not in attrs:
                attrs["estimate_point"] = None
                cleared["estimate_point"] = None

    return cleared


def sub_work_items_error(parent, sub_work_items):
    """Why the work items in the ``sub_work_items`` queryset can't be moved under ``parent``, or None."""
    if work_item_type_key(parent.type) != USER_STORY:
        return TASK_PARENT_NOT_STORY
    if sub_work_items.filter(
        type__external_source=BUILT_IN_WORK_ITEM_TYPE_SOURCE, type__external_id=USER_STORY
    ).exists():
        return STORY_WITH_PARENT
    return None
