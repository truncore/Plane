/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TCreatePullRequest,
  TGitHubConnectionCheck,
  TGitHubConnectionPayload,
  TGitHubSettings,
  TPullRequest,
  TPullRequestPreview,
  TWorkItemBranches,
  TWorkItemGitHub,
} from "@plane/types";
// services
import { APIService } from "@/services/api.service";

export class GitHubService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  private settingsUrl(workspaceSlug: string, projectId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/github/`;
  }

  async getSettings(workspaceSlug: string, projectId: string): Promise<TGitHubSettings> {
    return this.get(this.settingsUrl(workspaceSlug, projectId))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async saveSettings(
    workspaceSlug: string,
    projectId: string,
    data: Partial<TGitHubConnectionPayload>
  ): Promise<TGitHubSettings> {
    return this.put(this.settingsUrl(workspaceSlug, projectId), data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async disconnect(workspaceSlug: string, projectId: string): Promise<void> {
    return this.delete(this.settingsUrl(workspaceSlug, projectId))
      .then(() => undefined)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async testConnection(workspaceSlug: string, projectId: string): Promise<TGitHubConnectionCheck> {
    return this.post(`${this.settingsUrl(workspaceSlug, projectId)}test/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  private workItemUrl(workspaceSlug: string, projectId: string, workItemId: string) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${workItemId}/github/`;
  }

  async getWorkItemGitHub(workspaceSlug: string, projectId: string, workItemId: string): Promise<TWorkItemGitHub> {
    return this.get(this.workItemUrl(workspaceSlug, projectId, workItemId))
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async getBranches(workspaceSlug: string, projectId: string, workItemId: string): Promise<TWorkItemBranches> {
    return this.get(`${this.workItemUrl(workspaceSlug, projectId, workItemId)}branches/`)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async previewPullRequest(
    workspaceSlug: string,
    projectId: string,
    workItemId: string,
    branches: Pick<TCreatePullRequest, "base" | "head">
  ): Promise<TPullRequestPreview> {
    return this.get(`${this.workItemUrl(workspaceSlug, projectId, workItemId)}preview/`, branches)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  async createPullRequest(
    workspaceSlug: string,
    projectId: string,
    workItemId: string,
    data: TCreatePullRequest
  ): Promise<TPullRequest> {
    return this.post(`${this.workItemUrl(workspaceSlug, projectId, workItemId)}pull-requests/`, data)
      .then((response) => response?.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
