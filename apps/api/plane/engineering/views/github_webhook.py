# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import json

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

# Module imports
from plane.engineering.github.signature import signature_matches
from plane.engineering.github.sync import EVENT_HANDLERS
from plane.engineering.models import GitHubConnection, GitHubWebhookDelivery
from plane.engineering.tasks import process_github_delivery


class GitHubWebhookThrottle(SimpleRateThrottle):
    """GitHub can send bursts (one event per push or pull request change), so it gets its own limit."""

    scope = "github_webhook"
    rate = "600/minute"

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class GitHubWebhookEndpoint(APIView):
    """Receives GitHub webhooks. Requests are trusted only when signed with a connected project's secret."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [GitHubWebhookThrottle]

    def post(self, request):
        body = request.body
        try:
            payload = json.loads(body)
        except ValueError:
            return Response({"error": "The body isn't JSON."}, status=status.HTTP_400_BAD_REQUEST)

        owner, _, name = ((payload.get("repository") or {}).get("full_name") or "").partition("/")
        signature = request.headers.get("X-Hub-Signature-256", "")
        connections = [
            connection
            for connection in GitHubConnection.objects.filter(
                repository_owner__iexact=owner, repository_name__iexact=name
            )
            if signature_matches(connection.webhook_secret, body, signature)
        ]
        if not connections:
            return Response(
                {"error": "The signature doesn't match a connected project."}, status=status.HTTP_401_UNAUTHORIZED
            )

        event = request.headers.get("X-GitHub-Event", "")
        if event == "ping":
            return Response({"status": "pong"}, status=status.HTTP_200_OK)
        if event not in EVENT_HANDLERS:
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        if not delivery_id:
            return Response({"error": "The X-GitHub-Delivery header is missing."}, status=status.HTTP_400_BAD_REQUEST)
        delivery, created = GitHubWebhookDelivery.objects.get_or_create(
            delivery_id=delivery_id,
            defaults={
                "event": event,
                "payload": payload,
                "connection_ids": [str(connection.id) for connection in connections],
            },
        )
        if not created:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)
        process_github_delivery.delay(str(delivery.id))
        return Response({"status": "queued"}, status=status.HTTP_202_ACCEPTED)
