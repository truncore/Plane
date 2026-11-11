/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { createHmac, randomUUID } from "node:crypto";
import type { APIRequestContext } from "@playwright/test";
import { API_URL, DEMO, getDemoProjectId } from "./helpers";

const REPOSITORY = `${DEMO.github.repository_owner}/${DEMO.github.repository_name}`;

type TPullRequestEvent = {
  number: number;
  branch: string;
  action: "opened" | "reopened" | "ready_for_review" | "closed";
  draft?: boolean;
  merged?: boolean;
};

/** Create a work item through the API, as a test fixture. */
export async function createWorkItem(request: APIRequestContext, name: string) {
  const projectId = await getDemoProjectId(request);
  const response = await request.post(`${API_URL}/api/workspaces/${DEMO.workspaceSlug}/projects/${projectId}/issues/`, {
    data: { name },
  });
  const { id, sequence_id } = (await response.json()) as { id: string; sequence_id: number };
  return { id, key: `${DEMO.projectIdentifier}-${sequence_id}` };
}

/** Send a webhook exactly as GitHub would, signed with the demo project's webhook secret. */
async function sendEvent(request: APIRequestContext, event: string, payload: object) {
  const body = JSON.stringify(payload);
  const signature = createHmac("sha256", DEMO.github.webhook_secret).update(body).digest("hex");
  const response = await request.post(`${API_URL}/api/github/webhook/`, {
    data: body,
    headers: {
      "Content-Type": "application/json",
      "X-GitHub-Event": event,
      "X-GitHub-Delivery": randomUUID(),
      "X-Hub-Signature-256": `sha256=${signature}`,
    },
  });
  if (response.status() !== 202) throw new Error(`Webhook rejected: ${response.status()} ${await response.text()}`);
}

export async function sendPullRequestEvent(request: APIRequestContext, title: string, event: TPullRequestEvent) {
  const now = new Date().toISOString();
  const closed = event.action === "closed";
  await sendEvent(request, "pull_request", {
    action: event.action,
    repository: { full_name: REPOSITORY },
    pull_request: {
      number: event.number,
      title,
      html_url: `https://github.com/${REPOSITORY}/pull/${event.number}`,
      state: closed ? "closed" : "open",
      draft: event.draft ?? false,
      merged: event.merged ?? false,
      merged_at: event.merged ? now : null,
      closed_at: closed ? now : null,
      updated_at: now,
      head: { ref: event.branch },
      base: { ref: "main" },
      user: { login: "octocat" },
    },
  });
}

export async function sendTrunkPush(request: APIRequestContext, message: string) {
  await sendEvent(request, "push", {
    ref: "refs/heads/main",
    repository: { full_name: REPOSITORY },
    commits: [
      {
        id: randomUUID().replaceAll("-", "").padEnd(40, "0"),
        message,
        url: `https://github.com/${REPOSITORY}/commit/e2e`,
        timestamp: new Date().toISOString(),
        author: { name: "Octo Cat", username: "octocat" },
      },
    ],
  });
}
