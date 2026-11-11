# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.utils import timezone

# Third party imports
from celery import shared_task

# Module imports
from plane.engineering.github.sync import EVENT_HANDLERS
from plane.engineering.models import DeliveryStatus, GitHubConnection, GitHubWebhookDelivery
from plane.utils.exception_logger import log_exception


@shared_task
def process_github_delivery(delivery_id):
    """Apply a verified GitHub webhook delivery to every project connected to its repository."""
    delivery = GitHubWebhookDelivery.objects.get(pk=delivery_id)
    connections = GitHubConnection.objects.filter(pk__in=delivery.connection_ids).select_related(
        "project", "review_state", "merged_state"
    )
    try:
        for connection in connections:
            EVENT_HANDLERS[delivery.event](connection, delivery.payload, delivery.delivery_id)
        delivery.status = DeliveryStatus.PROCESSED
    except Exception as error:
        log_exception(error)
        delivery.status = DeliveryStatus.FAILED
        delivery.error = str(error)
    delivery.processed_at = timezone.now()
    delivery.save(update_fields=["status", "error", "processed_at"])
