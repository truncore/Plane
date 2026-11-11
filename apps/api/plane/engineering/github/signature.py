# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""GitHub webhook signatures: X-Hub-Signature-256 is an HMAC SHA-256 of the raw body with the secret."""

# Python imports
import hashlib
import hmac


def sign_body(secret, body):
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signature_matches(secret, body, signature):
    if not secret or not signature:
        return False
    return hmac.compare_digest(sign_body(secret, body), signature)
