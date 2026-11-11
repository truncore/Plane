# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GitHub webhooks: signature checks, dedupe, and how pull requests and trunk pushes move work items."""

import json
from datetime import timedelta
from io import StringIO
from unittest import mock

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import BotTypeEnum, Issue, IssueComment, IssueLink, Project, ProjectMember, State, WorkspaceMember
from plane.engineering.github.samples import pull_request_payload, push_payload
from plane.engineering.github.signature import sign_body, signature_matches
from plane.engineering.github.sync import closed_sequence_ids, mentioned_sequence_ids, moves_forward
from plane.engineering.models import GitHubConnection, GitHubWebhookDelivery, LinkedCommit, PullRequest
from plane.engineering.serializers import GitHubConnectionSerializer
from plane.engineering.tasks import process_github_delivery
from plane.tests.factories import UserFactory

URL = "/api/github/webhook/"
SECRET = "webhook-secret"
REPOSITORY = "truncore/plane"


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(name="Scrum", identifier="SCRUM", workspace=workspace, created_by=create_user)
    ProjectMember.objects.create(project=project, member=create_user, workspace=workspace, role=20)
    for name, group, sequence in [
        ("Backlog", "backlog", 15000),
        ("Todo", "unstarted", 25000),
        ("In Progress", "started", 35000),
        ("Done", "completed", 45000),
        ("Cancelled", "cancelled", 55000),
    ]:
        State.objects.create(name=name, group=group, sequence=sequence, project=project, default=name == "Backlog")
    return project


@pytest.fixture
def connection(project):
    data = {"repository_owner": "truncore", "repository_name": "plane", "token": "token", "webhook_secret": SECRET}
    serializer = GitHubConnectionSerializer(data=data, context={"project_id": project.id})
    serializer.is_valid(raise_exception=True)
    return serializer.save()


@pytest.fixture
def state(project):
    return lambda name: State.objects.get(project=project, name=name)


@pytest.fixture
def work_item(project, state):
    def make(name="Story", state_name="Todo"):
        return Issue.objects.create(name=name, project=project, workspace=project.workspace, state=state(state_name))

    return make


@pytest.fixture(autouse=True)
def run_tasks_inline():
    """Process deliveries straight away and capture activity calls instead of queueing them."""
    with (
        mock.patch.object(process_github_delivery, "delay", side_effect=process_github_delivery) as delay,
        mock.patch("plane.engineering.work_items.issue_activity") as issue_activity,
        mock.patch("plane.engineering.work_items.model_activity"),
    ):
        yield delay, issue_activity


def deliver(event, payload, secret=SECRET, delivery_id=None, client=None):
    body = json.dumps(payload).encode()
    return (client or APIClient()).post(
        URL,
        data=body,
        content_type="application/json",
        HTTP_X_GITHUB_EVENT=event,
        HTTP_X_GITHUB_DELIVERY=delivery_id or str(timezone.now().timestamp()),
        HTTP_X_HUB_SIGNATURE_256=sign_body(secret, body),
    )


def pr_event(item, action, number=1, branch=None, **options):
    branch = branch or f"feat/scrum-{item.sequence_id}-checkout"
    return pull_request_payload(REPOSITORY, number, branch, f"Checkout for SCRUM-{item.sequence_id}", action, **options)


def reload(item):
    return Issue.objects.select_related("state").get(pk=item.pk)


@pytest.mark.contract
@pytest.mark.django_db
class TestWebhookEndpoint:
    def test_wrong_signature_is_rejected(self, connection, work_item):
        response = deliver("pull_request", pr_event(work_item(), "opened"), secret="not-the-secret")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert not GitHubWebhookDelivery.objects.exists()

    def test_missing_signature_is_rejected(self, connection, work_item):
        body = json.dumps(pr_event(work_item(), "opened")).encode()
        response = APIClient().post(URL, data=body, content_type="application/json", HTTP_X_GITHUB_EVENT="pull_request")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_signature_covers_the_exact_body(self, connection, work_item):
        payload = pr_event(work_item(), "opened")
        body = json.dumps(payload).encode()
        tampered = body.replace(b'"opened"', b'"closed"')
        response = APIClient().post(
            URL,
            data=tampered,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_GITHUB_DELIVERY="d-1",
            HTTP_X_HUB_SIGNATURE_256=sign_body(SECRET, body),
        )

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_unknown_repository_is_rejected(self, connection):
        payload = pull_request_payload("someone/else", 1, "main", "x", "opened")

        assert deliver("pull_request", payload).status_code == status.HTTP_401_UNAUTHORIZED

    def test_body_must_be_json(self, connection):
        response = APIClient().post(URL, data=b"not json", content_type="application/json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_ping_and_unhandled_events(self, connection):
        repository = {"repository": {"full_name": REPOSITORY}}

        assert deliver("ping", repository).data == {"status": "pong"}
        assert deliver("issues", repository).data == {"status": "ignored"}

    def test_redelivery_is_applied_once(self, connection, work_item, run_tasks_inline):
        delay, _ = run_tasks_inline
        payload = pr_event(work_item(), "opened")

        first = deliver("pull_request", payload, delivery_id="same-id")
        second = deliver("pull_request", payload, delivery_id="same-id")

        assert first.status_code == status.HTTP_202_ACCEPTED
        assert second.data == {"status": "duplicate"}
        assert delay.call_count == 1
        assert GitHubWebhookDelivery.objects.get(delivery_id="same-id").status == "processed"

    def test_unauthenticated_requests_are_not_limited_by_the_anonymous_rate(self, connection):
        repository = {"repository": {"full_name": REPOSITORY}}

        responses = [deliver("ping", repository) for _ in range(35)]

        assert {response.status_code for response in responses} == {status.HTTP_200_OK}


@pytest.mark.contract
@pytest.mark.django_db
class TestPullRequestEvents:
    def test_opened_moves_to_in_review_as_the_github_bot(self, connection, work_item, run_tasks_inline):
        _, issue_activity = run_tasks_inline
        item = work_item()

        deliver("pull_request", pr_event(item, "opened"))

        assert reload(item).state.name == "In Review"
        record = PullRequest.objects.get(issue=item)
        assert (record.number, record.state, record.repository_full_name) == (1, "open", REPOSITORY)
        assert IssueLink.objects.filter(issue=item, url=record.url).exists()
        bot = WorkspaceMember.objects.get(workspace=item.workspace, member__is_bot=True).member
        assert bot.bot_type == BotTypeEnum.GITHUB and bot.display_name == "GitHub"
        state_update = next(
            c for c in issue_activity.delay.call_args_list if c.kwargs["type"] == "issue.activity.updated"
        )
        assert state_update.kwargs["actor_id"] == str(bot.id)
        assert json.loads(state_update.kwargs["requested_data"]) == {"state": str(reload(item).state_id)}

    def test_matches_the_work_item_id_in_a_lowercase_branch(self, connection, work_item):
        item = work_item()
        payload = pr_event(item, "opened", branch=f"fix/scrum-{item.sequence_id}")
        payload["pull_request"]["title"] = "No id in the title"

        deliver("pull_request", payload)

        assert reload(item).state.name == "In Review"

    def test_other_ids_are_ignored(self, connection, work_item):
        item = work_item()
        payload = pr_event(item, "opened", branch="feat/other-1-x")
        payload["pull_request"]["title"] = "SCRUM-999 and XSCRUM-1"

        deliver("pull_request", payload)

        assert reload(item).state.name == "Todo"
        assert not PullRequest.objects.exists()

    def test_draft_changes_nothing_until_ready(self, connection, work_item):
        item = work_item()

        deliver("pull_request", pr_event(item, "opened", draft=True))
        assert reload(item).state.name == "Todo"
        assert PullRequest.objects.get(issue=item).state == "draft"

        deliver("pull_request", pr_event(item, "ready_for_review"))
        assert reload(item).state.name == "In Review"

    def test_merged_moves_to_done(self, connection, work_item):
        item = work_item()

        deliver("pull_request", pr_event(item, "opened"))
        deliver("pull_request", pr_event(item, "closed", merged=True))

        assert reload(item).state.name == "Done"
        assert PullRequest.objects.get(issue=item).state == "merged"

    def test_done_only_when_every_open_pull_request_is_merged(self, connection, work_item):
        item = work_item()
        deliver("pull_request", pr_event(item, "opened", number=1))
        deliver("pull_request", pr_event(item, "opened", number=2))

        deliver("pull_request", pr_event(item, "closed", number=1, merged=True))
        assert reload(item).state.name == "In Review"

        deliver("pull_request", pr_event(item, "closed", number=2, merged=True))
        assert reload(item).state.name == "Done"

    def test_closed_without_merging_keeps_the_state_and_comments(self, connection, work_item):
        item = work_item()
        deliver("pull_request", pr_event(item, "opened"))

        deliver("pull_request", pr_event(item, "closed"), delivery_id="closed-1")
        deliver("pull_request", pr_event(item, "closed"), delivery_id="closed-1")

        assert reload(item).state.name == "In Review"
        comments = IssueComment.objects.filter(issue=item, external_source="github")
        assert comments.count() == 1
        assert "closed without merging" in comments.get().comment_html

    def test_a_closed_pull_request_does_not_block_done(self, connection, work_item):
        item = work_item()
        deliver("pull_request", pr_event(item, "opened", number=1))
        deliver("pull_request", pr_event(item, "closed", number=1))
        deliver("pull_request", pr_event(item, "opened", number=2))

        deliver("pull_request", pr_event(item, "closed", number=2, merged=True))

        assert reload(item).state.name == "Done"

    @pytest.mark.parametrize("state_name", ["Done", "Cancelled"])
    def test_never_moves_backwards_or_out_of_cancelled(self, connection, work_item, state_name):
        item = work_item(state_name=state_name)

        deliver("pull_request", pr_event(item, "reopened"))

        assert reload(item).state.name == state_name

    def test_stored_pull_request_matches_after_the_title_changes(self, connection, work_item):
        item = work_item()
        deliver("pull_request", pr_event(item, "opened", draft=True))
        payload = pr_event(item, "ready_for_review", branch="renamed-branch")
        payload["pull_request"]["title"] = "Renamed"

        deliver("pull_request", payload)

        assert reload(item).state.name == "In Review"
        assert PullRequest.objects.get(issue=item).title == "Renamed"

    def test_an_older_event_arriving_late_is_ignored(self, connection, work_item):
        item = work_item()
        merged = pr_event(item, "closed", merged=True)
        late = pr_event(item, "opened")
        late["pull_request"]["updated_at"] = (timezone.now() - timedelta(minutes=5)).isoformat()

        deliver("pull_request", merged)
        deliver("pull_request", late)

        assert PullRequest.objects.get(issue=item).state == "merged"
        assert reload(item).state.name == "Done"


@pytest.mark.contract
@pytest.mark.django_db
class TestTrunkPushes:
    def push(self, item, message, branch="main"):
        return deliver("push", push_payload(REPOSITORY, branch, [message.format(id=f"SCRUM-{item.sequence_id}")]))

    def test_fixes_completes_and_links_the_commit(self, connection, work_item):
        item = work_item()

        self.push(item, "Add receipts, fixes {id}")

        assert reload(item).state.name == "Done"
        commit = LinkedCommit.objects.get(issue=item)
        assert (commit.branch, commit.author_login) == ("main", "octocat")

    def test_a_mention_starts_an_unstarted_item(self, connection, work_item):
        item = work_item()

        self.push(item, "{id}: first slice")

        assert reload(item).state.name == "In Progress"

    def test_a_mention_does_not_move_a_started_item(self, connection, work_item):
        item = work_item(state_name="In Progress")
        deliver("pull_request", pr_event(item, "opened"))

        self.push(item, "{id}: follow-up")

        assert reload(item).state.name == "In Review"

    def test_pushes_to_other_branches_are_ignored(self, connection, work_item):
        item = work_item()

        self.push(item, "fixes {id}", branch="feat/x")

        assert reload(item).state.name == "Todo"
        assert not LinkedCommit.objects.exists()

    def test_feature_branch_projects_ignore_pushes(self, connection, work_item):
        GitHubConnection.objects.filter(pk=connection.pk).update(workflow_mode="feature_branches")
        item = work_item()

        self.push(item, "fixes {id}")

        assert reload(item).state.name == "Todo"


@pytest.mark.contract
@pytest.mark.django_db
class TestWorkItemGitHub:
    def test_lists_pull_requests_and_commits(self, session_client, connection, work_item):
        item = work_item()
        deliver("pull_request", pr_event(item, "opened"))
        deliver("push", push_payload(REPOSITORY, "main", [f"SCRUM-{item.sequence_id} part one"]))

        response = session_client.get(
            f"/api/workspaces/{item.workspace.slug}/projects/{item.project_id}/issues/{item.id}/github/"
        )

        assert response.status_code == status.HTTP_200_OK
        assert [pr["number"] for pr in response.data["pull_requests"]] == [1]
        assert response.data["commits"][0]["message"] == f"SCRUM-{item.sequence_id} part one"

    def test_non_members_cannot_see_them(self, connection, work_item, workspace):
        item = work_item()
        outsider = UserFactory()
        WorkspaceMember.objects.create(workspace=workspace, member=outsider, role=15)
        client = APIClient()
        client.force_authenticate(user=outsider)

        response = client.get(f"/api/workspaces/{workspace.slug}/projects/{item.project_id}/issues/{item.id}/github/")

        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.contract
@pytest.mark.django_db
def test_replay_command_sends_a_correctly_signed_sample(connection, work_item):
    item = work_item()
    with mock.patch("plane.engineering.management.commands.replay_github_webhook.requests.post") as post:
        post.return_value = mock.Mock(ok=True, status_code=202, text="queued")
        call_command("replay_github_webhook", "pr-opened", work_item=f"SCRUM-{item.sequence_id}", stdout=StringIO())

    headers, body = post.call_args.kwargs["headers"], post.call_args.kwargs["data"]
    assert headers["X-GitHub-Event"] == "pull_request"
    assert signature_matches(SECRET, body, headers["X-Hub-Signature-256"])
    assert json.loads(body)["pull_request"]["title"] == f"[SCRUM-{item.sequence_id}] Sample pull request"


@pytest.mark.unit
class TestMatching:
    def test_mentions(self):
        assert mentioned_sequence_ids("feat/pay-12-reset and PAY-3, XPAY-4, PAY-55x", "PAY") == {12, 3}

    def test_closing_keywords(self):
        assert closed_sequence_ids("Fixes PAY-1, closes: PAY-2 and done PAY-3; see PAY-4", "PAY") == {1, 2, 3}

    def test_forward_only(self):
        started = State(group="started", sequence=35000)
        review = State(group="started", sequence=36000)
        done = State(group="completed", sequence=45000)
        cancelled = State(group="cancelled", sequence=55000)

        assert moves_forward(started, review) and moves_forward(review, done)
        assert not moves_forward(done, review)
        assert not moves_forward(review, review)
        assert not moves_forward(cancelled, done)
