# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import secrets

# Django imports
from django.http import HttpResponseRedirect
from django.views import View

# Module imports
from plane.engineering.github import oauth
from plane.engineering.github.client import GitHubClient, GitHubError
from plane.engineering.models import GitHubAccount
from plane.utils.host import base_host

CALLBACK_PATH = "/api/github/oauth/callback/"
STATE_SESSION_KEY = "github_app_oauth_state"


def profile_redirect(request, result):
    """Back to the person's GitHub account settings, saying how connecting went."""
    return HttpResponseRedirect(f"{base_host(request=request, is_app=True)}/settings/profile/github?github={result}")


class GitHubOAuthStartEndpoint(View):
    """Sends the signed-in person to GitHub to let Plane act as them through the GitHub App."""

    def get(self, request):
        if not request.user.is_authenticated or not oauth.is_available():
            return profile_redirect(request, "error")
        state = secrets.token_urlsafe(32)
        request.session[STATE_SESSION_KEY] = state
        return HttpResponseRedirect(oauth.authorize_url(state, request.build_absolute_uri(CALLBACK_PATH)))


class GitHubOAuthCallbackEndpoint(View):
    """GitHub sends the person back here with a one-time code, which Plane swaps for their tokens."""

    def get(self, request):
        expected_state = request.session.pop(STATE_SESSION_KEY, None)
        state = request.GET.get("state", "")
        if not request.user.is_authenticated or not expected_state or not secrets.compare_digest(expected_state, state):
            return profile_redirect(request, "error")
        if request.GET.get("error") or not request.GET.get("code"):
            return profile_redirect(request, "denied")
        try:
            tokens = oauth.exchange_code(request.GET["code"], request.build_absolute_uri(CALLBACK_PATH))
            login = GitHubClient(tokens["access_token"]).get_user()["login"]
        except GitHubError:
            return profile_redirect(request, "error")

        account = GitHubAccount.objects.filter(user=request.user).first() or GitHubAccount(user=request.user)
        account.login = login
        oauth.save_tokens(account, tokens)
        account.save()
        return profile_redirect(request, "connected")
