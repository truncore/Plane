# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Connecting a personal GitHub account through the GitHub App: sign-in, token refresh and disconnect."""

from datetime import timedelta
from unittest import mock
from urllib.parse import parse_qs, urlparse

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from plane.engineering.github.client import GitHubError
from plane.engineering.github.oauth import usable_token
from plane.engineering.models import GitHubAccount
from plane.tests.github_fakes import REQUEST_PATH, FakeGitHub, response

START_URL = "/api/github/oauth/start/"
CALLBACK_URL = "/api/github/oauth/callback/"
TOKEN_POST_PATH = "plane.engineering.github.oauth.requests.post"
REVOKE_PATH = "plane.engineering.github.oauth.requests.delete"
TOKENS = {"access_token": "ghu_new", "refresh_token": "ghr_new", "expires_in": 28800}


@pytest.fixture
def github_app(monkeypatch):
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "Iv1.client")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "app-secret")


@pytest.fixture
def client(create_user):
    client = APIClient()
    client.force_login(create_user)
    return client


def start(client):
    """Begin connecting and return the state Plane sent to GitHub."""
    redirect = client.get(START_URL)
    return parse_qs(urlparse(redirect["Location"]).query)["state"][0]


def github_user(login="mariam-h"):
    return FakeGitHub({("GET", "/user"): response(json={"login": login})})


def oauth_account(user, expires_in_minutes):
    account = GitHubAccount(
        user=user, login="mariam-h", expires_at=timezone.now() + timedelta(minutes=expires_in_minutes)
    )
    account.token = "ghu_old"
    account.refresh_token = "ghr_old"
    account.save()
    return account


@pytest.mark.contract
@pytest.mark.django_db
class TestConnect:
    def test_start_sends_the_person_to_github_with_a_state(self, client, github_app):
        redirect = client.get(START_URL)

        assert redirect.status_code == 302
        url = urlparse(redirect["Location"])
        query = parse_qs(url.query)
        assert f"{url.netloc}{url.path}" == "github.com/login/oauth/authorize"
        assert query["client_id"] == ["Iv1.client"]
        assert query["redirect_uri"] == ["http://testserver/api/github/oauth/callback/"]
        assert len(query["state"][0]) > 30

    def test_success_stores_both_tokens_encrypted(self, client, github_app, create_user):
        state = start(client)
        with (
            mock.patch(TOKEN_POST_PATH, return_value=response(json=TOKENS)) as token_post,
            mock.patch(REQUEST_PATH, side_effect=github_user()),
        ):
            redirect = client.get(CALLBACK_URL, {"code": "one-time-code", "state": state})

        assert redirect["Location"].endswith("/settings/profile/github?github=connected")
        assert token_post.call_args.kwargs["data"]["code"] == "one-time-code"
        account = GitHubAccount.objects.get(user=create_user)
        assert (account.login, account.token, account.refresh_token) == ("mariam-h", "ghu_new", "ghr_new")
        assert "ghu_new" not in account.encrypted_token and "ghr_new" not in account.encrypted_refresh_token
        assert timedelta(hours=7) < account.expires_at - timezone.now() <= timedelta(hours=8)
        assert client.get("/api/users/me/github/").data["login"] == "mariam-h"

    def test_denied_consent(self, client, github_app):
        state = start(client)

        redirect = client.get(CALLBACK_URL, {"error": "access_denied", "state": state})

        assert redirect["Location"].endswith("?github=denied")
        assert not GitHubAccount.objects.exists()

    @pytest.mark.parametrize("state", ["", "forged-state"])
    def test_wrong_state_is_refused_without_calling_github(self, client, github_app, state):
        start(client)
        with mock.patch(TOKEN_POST_PATH) as token_post:
            redirect = client.get(CALLBACK_URL, {"code": "code", "state": state})

        assert redirect["Location"].endswith("?github=error")
        token_post.assert_not_called()

    def test_a_state_works_only_once(self, client, github_app):
        state = start(client)
        with (
            mock.patch(TOKEN_POST_PATH, return_value=response(json=TOKENS)),
            mock.patch(REQUEST_PATH, side_effect=github_user()),
        ):
            client.get(CALLBACK_URL, {"code": "code", "state": state})
            replay = client.get(CALLBACK_URL, {"code": "code", "state": state})

        assert replay["Location"].endswith("?github=error")

    def test_code_github_rejects(self, client, github_app):
        state = start(client)
        rejected = response(json={"error": "bad_verification_code", "error_description": "The code is incorrect"})
        with mock.patch(TOKEN_POST_PATH, return_value=rejected):
            redirect = client.get(CALLBACK_URL, {"code": "old", "state": state})

        assert redirect["Location"].endswith("?github=error")
        assert not GitHubAccount.objects.exists()

    def test_without_the_github_app_people_paste_a_token_instead(self, client, monkeypatch):
        monkeypatch.delenv("GITHUB_APP_CLIENT_ID", raising=False)

        assert client.get("/api/users/me/github/").data["oauth_available"] is False
        assert client.get(START_URL)["Location"].endswith("?github=error")

    def test_signed_out_visitors_cannot_connect(self, github_app):
        assert APIClient().get(START_URL)["Location"].endswith("?github=error")


@pytest.mark.contract
@pytest.mark.django_db
class TestTokens:
    def test_a_fresh_token_is_used_as_it_is(self, github_app, create_user):
        account = oauth_account(create_user, expires_in_minutes=60)

        with mock.patch(TOKEN_POST_PATH) as token_post:
            assert usable_token(account) == "ghu_old"
        token_post.assert_not_called()

    def test_an_expiring_token_is_refreshed_and_saved(self, github_app, create_user):
        account = oauth_account(create_user, expires_in_minutes=2)

        with mock.patch(TOKEN_POST_PATH, return_value=response(json=TOKENS)) as token_post:
            assert usable_token(account) == "ghu_new"

        assert token_post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
        assert token_post.call_args.kwargs["data"]["refresh_token"] == "ghr_old"
        saved = GitHubAccount.objects.get(pk=account.pk)
        assert (saved.token, saved.refresh_token) == ("ghu_new", "ghr_new")

    def test_a_failed_refresh_asks_the_person_to_reconnect(self, github_app, create_user):
        account = oauth_account(create_user, expires_in_minutes=-1)

        with mock.patch(TOKEN_POST_PATH, return_value=response(json={"error": "bad_refresh_token"})):
            with pytest.raises(GitHubError) as error:
                usable_token(account)

        assert error.value.code == "reconnect_github"
        assert not GitHubAccount.objects.exists()

    def test_pasted_tokens_never_refresh(self, create_user):
        account = GitHubAccount(user=create_user, login="mariam-h")
        account.token = "github_pat_x"
        account.save()

        assert usable_token(account) == "github_pat_x"


@pytest.mark.contract
@pytest.mark.django_db
def test_disconnect_revokes_the_grant_on_github(client, github_app, create_user):
    oauth_account(create_user, expires_in_minutes=60)

    with mock.patch(REVOKE_PATH) as revoke:
        client.delete("/api/users/me/github/")

    assert revoke.call_args.args[0] == "https://api.github.com/applications/Iv1.client/grant"
    assert revoke.call_args.kwargs["auth"] == ("Iv1.client", "app-secret")
    assert revoke.call_args.kwargs["json"] == {"access_token": "ghu_old"}
    assert not GitHubAccount.objects.exists()


@pytest.mark.contract
@pytest.mark.django_db
def test_install_link_for_more_repositories(client, github_app, monkeypatch):
    monkeypatch.setenv("GITHUB_APP_SLUG", "truncore-plane")

    data = client.get("/api/users/me/github/").data

    assert data["install_url"] == "https://github.com/apps/truncore-plane/installations/new"
