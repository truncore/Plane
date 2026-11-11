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
  | "github_error";

export type TGitHubError = {
  code: TGitHubErrorCode;
  error: string;
};
