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
    "no_commits": "The branch has no commits that aren't already in the base branch.",
    "pr_exists": "An open pull request already exists for this branch.",
    "protected_branch": "GitHub refused because of the branch's protection rules.",
    "no_personal_account": "Connect your own GitHub account in your profile settings to do this as yourself.",
    "not_mergeable": "GitHub says the pull request can't be merged right now.",
    "github_error": "GitHub returned an unexpected error.",
}

# GitHub's validation messages (status 422) that have a clearer meaning
VALIDATION_ERRORS = {
    "no commits between": "no_commits",
    "pull request already exists": "pr_exists",
    "protected": "protected_branch",
}

BRANCHES_QUERY = """
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    refs(refPrefix: "refs/heads/", first: 100, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
      nodes { name target { ... on Commit { committedDate } } }
    }
  }
}
"""


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
    def __init__(self, token, owner=None, repository=None):
        """A client for one repository; without one, only account-level calls such as get_user work."""
        if owner is not None and not is_valid_repository(owner, repository):
            raise ValueError("Invalid repository")
        self.owner = owner
        self.repository = repository
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
        if response.status_code == 405:
            return GitHubError("not_mergeable")
        try:
            body = response.json()
        except ValueError:
            body = {}
        detail = body.get("message")
        if response.status_code == 422:
            messages = " ".join([detail or ""] + [error.get("message", "") for error in body.get("errors", [])]).lower()
            for phrase, code in VALIDATION_ERRORS.items():
                if phrase in messages:
                    return GitHubError(code)
        return GitHubError("github_error", f"{ERROR_MESSAGES['github_error']} ({response.status_code}: {detail})")

    def get_repository(self):
        return self.request("GET", self.repository_path)

    def get_branch(self, branch):
        if not is_valid_branch(branch):
            raise GitHubError("branch_not_found")
        return self.request("GET", f"{self.repository_path}/branches/{quote(branch)}", not_found="branch_not_found")

    def list_branches(self):
        """The 100 most recently changed branches, newest first, with the time of their last commit."""
        data = self.request(
            "POST",
            "/graphql",
            json={"query": BRANCHES_QUERY, "variables": {"owner": self.owner, "name": self.repository}},
        )
        if data.get("errors"):
            not_found = any(error.get("type") == "NOT_FOUND" for error in data["errors"])
            raise GitHubError("repository_not_found" if not_found else "github_error")
        return [
            {"name": node["name"], "last_commit_at": node["target"].get("committedDate")}
            for node in data["data"]["repository"]["refs"]["nodes"]
        ]

    def compare(self, base, head):
        """Commits and changed files on `head` that aren't on `base`."""
        if not (is_valid_branch(base) and is_valid_branch(head)):
            raise GitHubError("branch_not_found")
        return self.request(
            "GET", f"{self.repository_path}/compare/{quote(base)}...{quote(head)}", not_found="branch_not_found"
        )

    def find_open_pull_request(self, base, head):
        pulls = self.request(
            "GET",
            f"{self.repository_path}/pulls",
            params={"state": "open", "base": base, "head": f"{self.owner}:{head}"},
        )
        return pulls[0] if pulls else None

    def create_pull_request(self, base, head, title, body):
        return self.request(
            "POST", f"{self.repository_path}/pulls", json={"base": base, "head": head, "title": title, "body": body}
        )

    def get_user(self):
        return self.request("GET", "/user")

    def get_pull_request(self, number):
        return self.request("GET", f"{self.repository_path}/pulls/{number}")

    def list_reviews(self, number):
        return self.request("GET", f"{self.repository_path}/pulls/{number}/reviews", params={"per_page": 100})

    def list_check_runs(self, sha):
        return self.request("GET", f"{self.repository_path}/commits/{sha}/check-runs", params={"per_page": 100})[
            "check_runs"
        ]

    def create_review(self, number, event, body):
        return self.request(
            "POST", f"{self.repository_path}/pulls/{number}/reviews", json={"event": event, "body": body}
        )

    def request_reviewers(self, number, reviewers):
        return self.request(
            "POST", f"{self.repository_path}/pulls/{number}/requested_reviewers", json={"reviewers": reviewers}
        )

    def merge_pull_request(self, number, method):
        return self.request("PUT", f"{self.repository_path}/pulls/{number}/merge", json={"merge_method": method})
