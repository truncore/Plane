# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A stand-in for the GitHub API in tests: patch ``REQUEST_PATH`` with a ``FakeGitHub``."""

from unittest import mock

REQUEST_PATH = "plane.engineering.github.client.requests.request"
API = "https://api.github.com"


def response(status_code=200, json=None):
    fake = mock.Mock(status_code=status_code, ok=status_code < 400, headers={}, content=b"{}")
    fake.json.return_value = json if json is not None else {}
    return fake


class FakeGitHub:
    """Answers GitHub API requests by (method, path) with canned responses, and records them."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, **kwargs):
        path = url.removeprefix(API)
        self.calls.append((method, path, kwargs))
        return self.routes[(method, path)]
