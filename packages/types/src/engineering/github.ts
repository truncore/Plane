/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TWorkflowMode = "trunk_based" | "feature_branches";

/** A project's GitHub settings as the API returns them: secrets are only reported as set or not. */
export type TGitHubConnection = {
  id: string;
  repository_owner: string;
  repository_name: string;
  repository_full_name: string;
  workflow_mode: TWorkflowMode;
  base_branch: string;
  review_state_id: string;
  merged_state_id: string;
  branch_age_limit_days: number;
  large_pr_lines: number;
  has_token: boolean;
  has_webhook_secret: boolean;
};

export type TGitHubSettings = {
  connection: TGitHubConnection | null;
  webhook_url: string;
};

/** What the settings form sends. A blank token or webhook secret keeps the saved one. */
export type TGitHubConnectionPayload = Omit<
  TGitHubConnection,
  "id" | "repository_full_name" | "has_token" | "has_webhook_secret"
> & {
  token: string;
  webhook_secret: string;
};

export type TGitHubConnectionCheck = {
  repository: string;
  private: boolean;
  default_branch: string;
};

export type TGitHubErrorCode =
  | "not_connected"
  | "bad_token"
  | "forbidden"
  | "rate_limited"
  | "unreachable"
  | "repository_not_found"
  | "branch_not_found"
  | "no_push_permission"
  | "no_commits"
  | "pr_exists"
  | "protected_branch"
  | "no_personal_account"
  | "not_mergeable"
  | "github_error";

export type TGitHubError = {
  code: TGitHubErrorCode;
  error: string;
};

export type TPullRequestState = "open" | "draft" | "merged" | "closed";

/** A GitHub pull request linked to a work item. */
export type TPullRequest = {
  id: string;
  repository_full_name: string;
  number: number;
  title: string;
  url: string;
  head_branch: string;
  base_branch: string;
  state: TPullRequestState;
  author_login: string;
  additions: number | null;
  deletions: number | null;
  changed_files: number | null;
  merged_at: string | null;
  closed_at: string | null;
  created_at: string;
};

/** A commit on the trunk that mentions a work item. */
export type TLinkedCommit = {
  id: string;
  repository_full_name: string;
  sha: string;
  branch: string;
  message: string;
  url: string;
  author_name: string;
  author_login: string;
  committed_at: string | null;
};

export type TWorkItemGitHub = {
  pull_requests: TPullRequest[];
  commits: TLinkedCommit[];
};

export type TGitHubBranch = {
  name: string;
  last_commit_at: string | null;
  /** The branch name mentions the work item, e.g. feat/PAY-12-reset-password */
  suggested: boolean;
};

export type TWorkItemBranches = {
  branches: TGitHubBranch[];
  base_branch: string;
  workflow_mode: TWorkflowMode;
  branch_age_limit_days: number;
  large_pr_lines: number;
};

/** What a pull request from a branch would contain, with the trunk-based warnings. */
export type TPullRequestPreview = {
  ahead_by: number;
  changed_files: number;
  changed_lines: number;
  branch_age_days: number;
  is_old_branch: boolean;
  is_large: boolean;
  existing_pull_request_url: string | null;
};

export type TCreatePullRequest = {
  base: string;
  head: string;
  title: string;
  body: string;
};

/** The signed-in person's own GitHub account; null login when not connected. */
export type TGitHubAccount = {
  login: string | null;
};

export type TReviewVerdict = "APPROVED" | "CHANGES_REQUESTED" | "COMMENTED" | "DISMISSED" | "PENDING";
export type TReviewEvent = "APPROVE" | "REQUEST_CHANGES" | "COMMENT";
export type TMergeMethod = "merge" | "squash" | "rebase";

/** A pull request's live status on GitHub, and what the signed-in person may do with it. */
export type TPullRequestDetails = {
  url: string;
  files_url: string;
  state: TPullRequestState;
  /** GitHub's mergeable_state: clean, unstable, blocked, behind, dirty, draft, has_hooks or unknown */
  mergeable_state: string;
  reviewers: { login: string; state: TReviewVerdict }[];
  checks: { name: string; status: string; conclusion: string | null; url: string }[];
  acting_as: string | null;
  can_review: boolean;
  can_merge: boolean;
};
