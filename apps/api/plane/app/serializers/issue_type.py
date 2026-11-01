# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from .base import BaseSerializer
from plane.db.models import IssueType


class IssueTypeSerializer(BaseSerializer):
    key = serializers.CharField(source="external_id", read_only=True)

    class Meta:
        model = IssueType
        fields = ["id", "name", "key", "is_default"]
        read_only_fields = fields
