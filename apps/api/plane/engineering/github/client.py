# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""A small client for the GitHub REST API.

Failures raise GitHubError with a short ``code`` the web app translates, and an English ``message``
for API users.
"""

# Python imports
import re
from urllib.parse import quote

# Third party imports
import requests

GITHUB_API_URL = "https://api.github.com"
TIMEOUT_SECONDS = 10

OWNER_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
# Git's branch name rules, simplified: no spaces, control characters or special characters, no "..",
# not starting with "-" or "/", not ending with "/", "." or ".lock"
BRANCH_PATTERN = re.compile(
    r"^(?![-/])(?!.*\.\.)(?!.*//)(?!.*@\{)[^\s~^:?*\[\\\x00-\x1f\x7f]{1,255}(?<![/.])(?<!\.lock)$"
)

ERROR_MESSAGES = {
    "bad_token": "GitHub rejected the token. It may be wrong, expired or revoked.",
    "forbidden": "The token isn't allowed to do this. Check its repository access and permissions.",
    "rate_limited": "GitHub's rate limit was reached. Try again in a few minutes.",
    "unreachable": "Plane couldn't reach GitHub. Check the server's internet connection and try again.",
    "repository_not_found": "GitHub couldn't find the repository, or the token has no access to it.",
    "branch_not_found": "The branch doesn't exist in the repository.",
    "no_push_permission": "The token can read the repository but can't push to it, so it can't open pull requests.",
    "github_error": "GitHub returned an unexpected error.",
}


class GitHubError(Exception):
    def __init__(self, code, detail=None):
        self.code = code
        self.message = detail or ERROR_MESSAGES[code]
        super().__init__(self.message)


def is_valid_repository(owner, name):
    return (
        bool(OWNER_PATTERN.match(owner or ""))
        and bool(REPOSITORY_PATTERN.match(name or ""))
        and name not in (".", "..")
    )


def is_valid_branch(name):
    return bool(BRANCH_PATTERN.match(name or ""))


class GitHubClient:
    def __init__(self, token, owner, repository):
        if not is_valid_repository(owner, repository):
            raise ValueError("Invalid repository")
        self.repository_path = f"/repos/{owner}/{repository}"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def request(self, method, path, not_found="repository_not_found", **kwargs):
        try:
            response = requests.request(
                method, f"{GITHUB_API_URL}{path}", headers=self.headers, timeout=TIMEOUT_SECONDS, **kwargs
            )
        except requests.RequestException:
            raise GitHubError("unreachable")
        if response.ok:
            return response.json() if response.content else None
        raise self.error_for(response, not_found)

    @staticmethod
    def error_for(response, not_found):
        if response.status_code == 401:
            return GitHubError("bad_token")
        if response.status_code in (403, 429) and response.headers.get("x-ratelimit-remaining") == "0":
            return GitHubError("rate_limited")
        if response.status_code == 403:
            return GitHubError("forbidden")
        if response.status_code == 404:
            return GitHubError(not_found)
        try:
            detail = response.json().get("message")
        except ValueError:
            detail = None
        return GitHubError("github_error", f"{ERROR_MESSAGES['github_error']} ({response.status_code}: {detail})")

    def get_repository(self):
        return self.request("GET", self.repository_path)

    def get_branch(self, branch):
        if not is_valid_branch(branch):
            raise GitHubError("branch_not_found")
        return self.request(
            "GET", f"{self.repository_path}/branches/{quote(branch, safe='')}", not_found="branch_not_found"
        )
