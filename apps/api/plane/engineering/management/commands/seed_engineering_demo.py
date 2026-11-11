# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Create a small demo workspace for local development and browser tests. Safe to run repeatedly."""

# Python imports
import time
import uuid
from datetime import timedelta

# Django imports
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

# Module imports
from plane.app.permissions import ROLE
from plane.db.models import (
    Cycle,
    CycleIssue,
    Estimate,
    EstimatePoint,
    Issue,
    IssueActivity,
    IssueAssignee,
    IssueType,
    Profile,
    Project,
    ProjectIdentifier,
    ProjectMember,
    State,
    User,
    Workspace,
    WorkspaceMember,
)
from plane.db.models.issue_type import BUILT_IN_WORK_ITEM_TYPE_SOURCE
from plane.db.models.state import DEFAULT_STATES

DEMO_PASSWORD = "Truncore-Demo-2026"
DEMO_WORKSPACE = {"slug": "truncore-demo", "name": "Truncore Demo"}
DEMO_PROJECT = {"identifier": "PAY", "name": "Payments"}
DEMO_USERS = [
    {"email": "mariam@example.com", "first_name": "Mariam", "last_name": "Hassan", "role": ROLE.ADMIN},
    {"email": "omar@example.com", "first_name": "Omar", "last_name": "Farouk", "role": ROLE.MEMBER},
    {"email": "lina@example.com", "first_name": "Lina", "last_name": "Nasser", "role": ROLE.MEMBER},
]
FIBONACCI_POINTS = ["1", "2", "3", "5", "8", "13"]
# Points go on stories only (team rule); tasks are sub-work items of their story.
DEMO_STORIES = [
    {
        "name": "As a customer I can pay with a saved card",
        "points": "8",
        "state": "In Progress",
        "assignee": 1,
        "tasks": [
            ("Store card tokens securely", "Done"),
            ("Add saved-card picker to checkout", "In Progress"),
            ("Write payment API tests", "Todo"),
        ],
    },
    {
        "name": "As a customer I get an email receipt",
        "points": "3",
        "state": "Todo",
        "assignee": 2,
        "tasks": [("Design the receipt template", "Todo"), ("Send the receipt after payment", "Todo")],
    },
    {
        "name": "As an admin I can refund a payment",
        "points": "5",
        "state": "Done",
        "assignee": 0,
        "tasks": [("Refund endpoint", "Done"), ("Refund button in the admin panel", "Done")],
    },
]


class Command(BaseCommand):
    help = "Create (or top up) the Truncore Demo workspace used for local development and browser tests"

    @transaction.atomic
    def handle(self, *args, **options):
        users = [self.get_user(user) for user in DEMO_USERS]
        admin = users[0]
        workspace = self.get_workspace(admin, users)
        project = self.get_project(workspace, admin, users)
        cycle = self.get_cycle(project, admin)
        self.create_stories(project, cycle, users)

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo workspace ready: /{workspace.slug}/ - sign in as {admin.email} with password {DEMO_PASSWORD}"
            )
        )

    def get_user(self, data):
        user = User.objects.filter(email=data["email"]).first()
        if user is None:
            user = User(
                email=data["email"],
                username=uuid.uuid4().hex,
                first_name=data["first_name"],
                last_name=data["last_name"],
                display_name=data["first_name"].lower(),
                is_password_autoset=False,
            )
            user.set_password(DEMO_PASSWORD)
            user.save()
        return user

    def get_workspace(self, admin, users):
        workspace, _ = Workspace.objects.get_or_create(
            slug=DEMO_WORKSPACE["slug"], defaults={"name": DEMO_WORKSPACE["name"], "owner": admin}
        )
        for user, data in zip(users, DEMO_USERS):
            WorkspaceMember.objects.get_or_create(
                workspace=workspace, member=user, defaults={"role": data["role"].value}
            )
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.is_onboarded = True
            profile.is_tour_completed = True
            profile.onboarding_step = {key: True for key in profile.onboarding_step}
            profile.last_workspace_id = workspace.id
            profile.save()
        return workspace

    def get_project(self, workspace, admin, users):
        project = Project.objects.filter(workspace=workspace, identifier=DEMO_PROJECT["identifier"]).first()
        if project is None:
            project = Project(
                workspace=workspace,
                name=DEMO_PROJECT["name"],
                identifier=DEMO_PROJECT["identifier"],
                project_lead=admin,
                cycle_view=True,
                module_view=True,
            )
            project.save(created_by_id=admin.id)
            ProjectIdentifier.objects.create(name=project.identifier, project=project, workspace=workspace)
            State.objects.bulk_create(
                [
                    State(
                        name=state["name"],
                        color=state["color"],
                        sequence=state["sequence"],
                        group=state["group"],
                        default=state.get("default", False),
                        project=project,
                        workspace=workspace,
                        created_by=admin,
                    )
                    for state in DEFAULT_STATES
                ]
            )
        for user, data in zip(users, DEMO_USERS):
            ProjectMember.objects.get_or_create(project=project, member=user, defaults={"role": data["role"].value})

        if project.estimate is None:
            estimate = Estimate.objects.create(name="Fibonacci", type="points", project=project, last_used=True)
            EstimatePoint.objects.bulk_create(
                [
                    EstimatePoint(estimate=estimate, key=key, value=value, project=project, workspace=workspace)
                    for key, value in enumerate(FIBONACCI_POINTS, start=1)
                ]
            )
            project.estimate = estimate
            project.save(update_fields=["estimate"])
        return project

    def get_cycle(self, project, admin):
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cycle, _ = Cycle.objects.get_or_create(
            project=project,
            name="Sprint 1",
            defaults={
                "start_date": today - timedelta(days=3),
                "end_date": today + timedelta(days=11),
                "owned_by": admin,
            },
        )
        return cycle

    def create_stories(self, project, cycle, users):
        states = {state.name: state for state in State.objects.filter(project=project)}
        points = {point.value: point for point in EstimatePoint.objects.filter(estimate=project.estimate)}
        types = {
            issue_type.external_id: issue_type
            for issue_type in IssueType.objects.filter(
                workspace=project.workspace, external_source=BUILT_IN_WORK_ITEM_TYPE_SOURCE
            )
        }

        for story_data in DEMO_STORIES:
            assignee = users[story_data["assignee"]]
            story = self.get_work_item(
                project,
                story_data["name"],
                assignee,
                state=states[story_data["state"]],
                type=types["user_story"],
                estimate_point=points[story_data["points"]],
            )
            CycleIssue.objects.get_or_create(cycle=cycle, issue=story, project=project)
            for task_name, task_state in story_data["tasks"]:
                self.get_work_item(
                    project, task_name, assignee, state=states[task_state], type=types["task"], parent=story
                )

    def get_work_item(self, project, name, assignee, **fields):
        work_item = Issue.objects.filter(project=project, name=name).first()
        if work_item is None:
            work_item = Issue(project=project, name=name, **fields)
            work_item.save(created_by_id=assignee.id)
            IssueAssignee.objects.create(issue=work_item, assignee=assignee, project=project)
            IssueActivity.objects.create(
                issue=work_item,
                project=project,
                workspace=project.workspace,
                verb="created",
                comment="created the work item",
                actor=assignee,
                epoch=time.time(),
            )
        return work_item
