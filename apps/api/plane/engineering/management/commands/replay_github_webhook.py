# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Send a signed GitHub webhook to this Plane, so GitHub features can be tested without a public URL.

Examples:
    python manage.py replay_github_webhook pr-opened --work-item PAY-1 --number 7
    python manage.py replay_github_webhook pr-merged --work-item PAY-1 --number 7
    python manage.py replay_github_webhook push-fixes --work-item PAY-5
    python manage.py replay_github_webhook --file saved-payload.json --event pull_request --project PAY
"""

# Python imports
import json
import uuid

# Django imports
from django.core.management.base import BaseCommand, CommandError

# Third party imports
import requests

# Module imports
from plane.engineering.github.samples import SAMPLES, sample_payload
from plane.engineering.github.signature import sign_body
from plane.engineering.models import GitHubConnection


class Command(BaseCommand):
    help = "Send a sample (or saved) GitHub webhook, signed with the project's webhook secret, to this Plane"

    def add_arguments(self, parser):
        parser.add_argument("sample", nargs="?", choices=sorted(SAMPLES), help="Which sample event to send")
        parser.add_argument("--work-item", help="The work item the sample is about, e.g. PAY-12")
        parser.add_argument("--number", type=int, default=1, help="Pull request number (default 1)")
        parser.add_argument("--branch", help="Pull request branch (default feat/<work-item>-sample)")
        parser.add_argument("--file", help="Send this saved payload instead of a sample")
        parser.add_argument("--event", choices=["pull_request", "push", "ping"], help="The event of --file")
        parser.add_argument("--project", help="Project identifier, e.g. PAY (taken from --work-item if omitted)")
        parser.add_argument("--workspace", help="Workspace slug, when several workspaces use the identifier")
        parser.add_argument("--url", default="http://localhost:8000/api/github/webhook/", help="Webhook URL")

    def handle(self, *args, **options):
        if options["file"]:
            if not options["event"]:
                raise CommandError("--file needs --event.")
            connection = self.get_connection(options["project"], options["workspace"])
            with open(options["file"], encoding="utf-8") as file:
                event, payload = options["event"], json.load(file)
        else:
            if not options["sample"] or not options["work_item"]:
                raise CommandError("Name a sample and --work-item, or pass --file and --event.")
            project = options["project"] or options["work_item"].rsplit("-", 1)[0]
            connection = self.get_connection(project, options["workspace"])
            event, payload = sample_payload(
                options["sample"], connection, options["work_item"].upper(), options["number"], options["branch"]
            )

        body = json.dumps(payload).encode()
        response = requests.post(
            options["url"],
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Event": event,
                "X-GitHub-Delivery": str(uuid.uuid4()),
                "X-Hub-Signature-256": sign_body(connection.webhook_secret, body),
            },
            timeout=30,
        )
        self.stdout.write(f"{event} → {connection.repository_full_name}: {response.status_code} {response.text}")
        if not response.ok:
            raise CommandError("The webhook was rejected.")

    def get_connection(self, identifier, workspace_slug):
        if not identifier:
            raise CommandError("Pass --project (or --work-item).")
        connections = GitHubConnection.objects.filter(project__identifier__iexact=identifier)
        if workspace_slug:
            connections = connections.filter(workspace__slug=workspace_slug)
        if connections.count() != 1:
            raise CommandError(
                f"Found {connections.count()} projects with identifier {identifier} connected to GitHub. "
                "Connect one in Project settings → GitHub, or pass --workspace."
            )
        return connections.get()
