# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The demo seed builds a usable scrum project and can be run repeatedly."""

from io import StringIO

import pytest
from django.core.management import call_command

from plane.db.models import Cycle, CycleIssue, Issue, Project, User, Workspace
from plane.engineering.models import GitHubConnection
from plane.engineering.management.commands.seed_engineering_demo import DEMO_PASSWORD, DEMO_STORIES, DEMO_USERS


def seed():
    call_command("seed_engineering_demo", stdout=StringIO())
    return Project.objects.get(workspace__slug="truncore-demo", identifier="PAY")


@pytest.mark.unit
@pytest.mark.django_db
class TestSeedEngineeringDemo:
    def test_users_can_sign_in_and_land_in_the_workspace(self):
        project = seed()

        for data in DEMO_USERS:
            user = User.objects.get(email=data["email"])
            assert user.check_password(DEMO_PASSWORD)
            assert user.profile.is_onboarded
            assert user.profile.last_workspace_id == project.workspace_id

    def test_stories_have_points_and_tasks_do_not(self):
        project = seed()

        stories = Issue.objects.filter(project=project, type__external_id="user_story")
        tasks = Issue.objects.filter(project=project, type__external_id="task")
        assert stories.count() == len(DEMO_STORIES)
        assert all(story.estimate_point is not None for story in stories)
        assert tasks.count() == sum(len(story["tasks"]) for story in DEMO_STORIES)
        assert all(task.parent in stories and task.estimate_point is None for task in tasks)

    def test_stories_use_the_story_template(self):
        project = seed()

        for story in Issue.objects.filter(project=project, type__external_id="user_story"):
            assert story.description_html.startswith("<p>As a")
            assert "<h3>Acceptance criteria</h3>" in story.description_html

    def test_project_has_fibonacci_estimate_and_a_current_cycle(self):
        project = seed()

        assert project.estimate.type == "points"
        assert sorted(int(point.value) for point in project.estimate.points.all()) == [1, 2, 3, 5, 8, 13]
        cycle = Cycle.objects.get(project=project)
        assert CycleIssue.objects.filter(cycle=cycle).count() == len(DEMO_STORIES)

    def test_project_is_connected_to_a_placeholder_repository(self):
        project = seed()

        connection = GitHubConnection.objects.get(project=project)
        assert connection.repository_full_name == "truncore/plane-demo"
        assert connection.workflow_mode == "trunk_based"
        assert (connection.review_state.name, connection.review_state.group) == ("In Review", "started")

    def test_running_twice_creates_nothing_new(self):
        seed()
        counts = (User.objects.count(), Workspace.objects.count(), Issue.all_objects.count(), Cycle.objects.count())

        seed()

        assert counts == (
            User.objects.count(),
            Workspace.objects.count(),
            Issue.all_objects.count(),
            Cycle.objects.count(),
        )
