# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Signing a person in with Truncore's GitHub App, so Plane acts on GitHub as them.

GitHub App user tokens expire after 8 hours and come with a refresh token. Both are stored encrypted on the
person's GitHubAccount and refreshed automatically before use.
"""

# Python imports
import os
from datetime import timedelta
from urllib.parse import urlencode

# Django imports
from django.utils import timezone

# Third party imports
import requests

# Module imports
from plane.engineering.github.client import TIMEOUT_SECONDS, GitHubError

GITHUB_OAUTH_URL = "https://github.com/login/oauth"
GITHUB_API_URL = "https://api.github.com"
# Refresh a little early so a token never expires halfway through a request
REFRESH_MARGIN = timedelta(minutes=5)


def app_credentials():
    return os.environ.get("GITHUB_APP_CLIENT_ID"), os.environ.get("GITHUB_APP_CLIENT_SECRET")


def is_available():
    """Whether the GitHub App is configured; without it people paste a personal token instead."""
    return all(app_credentials())


def install_url():
    """Where people add the GitHub App to more repositories; its actions only work where it is installed."""
    slug = os.environ.get("GITHUB_APP_SLUG")
    return f"https://github.com/apps/{slug}/installations/new" if slug else None


def authorize_url(state, redirect_uri):
    client_id, _ = app_credentials()
    return f"{GITHUB_OAUTH_URL}/authorize?" + urlencode(
        {"client_id": client_id, "redirect_uri": redirect_uri, "state": state}
    )


def request_tokens(**grant):
    """Ask GitHub for user tokens. GitHub answers 200 even on failure, with an "error" field."""
    client_id, client_secret = app_credentials()
    try:
        response = requests.post(
            f"{GITHUB_OAUTH_URL}/access_token",
            data={"client_id": client_id, "client_secret": client_secret, **grant},
            headers={"Accept": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
        tokens = response.json()
    except (requests.RequestException, ValueError):
        raise GitHubError("unreachable")
    if not response.ok or "access_token" not in tokens:
        raise GitHubError("bad_token", tokens.get("error_description"))
    return tokens


def exchange_code(code, redirect_uri):
    return request_tokens(code=code, redirect_uri=redirect_uri)


def save_tokens(account, tokens):
    account.token = tokens["access_token"]
    account.refresh_token = tokens.get("refresh_token", "")
    expires_in = tokens.get("expires_in")
    account.expires_at = timezone.now() + timedelta(seconds=int(expires_in)) if expires_in else None


def usable_token(account):
    """The account's token, refreshed first when it is about to expire.

    A refresh that fails (revoked, or unused for six months) disconnects the account: the person has to
    connect again.
    """
    if account.expires_at is None or account.expires_at > timezone.now() + REFRESH_MARGIN:
        return account.token
    try:
        tokens = request_tokens(grant_type="refresh_token", refresh_token=account.refresh_token)
    except GitHubError:
        account.delete()
        raise GitHubError("reconnect_github")
    save_tokens(account, tokens)
    account.save()
    return account.token


def revoke(account):
    """Withdraw Plane's access on GitHub. Best effort: the account is deleted in Plane either way."""
    client_id, client_secret = app_credentials()
    if not (account.refresh_token and client_id and client_secret):
        return
    try:
        requests.delete(
            f"{GITHUB_API_URL}/applications/{client_id}/grant",
            auth=(client_id, client_secret),
            json={"access_token": account.token},
            headers={"Accept": "application/vnd.github+json"},
            timeout=TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        pass
