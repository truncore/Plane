/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import path from "node:path";
import { test as base } from "@playwright/test";
import type { APIRequestContext, Page } from "@playwright/test";

// Created by `python manage.py seed_engineering_demo`.
export const DEMO = {
  email: "mariam@example.com",
  password: "Truncore-Demo-2026",
  workspaceSlug: "truncore-demo",
  projectName: "Payments",
  projectIdentifier: "PAY",
  // The placeholder GitHub connection the seed gives the demo project
  github: {
    repository_owner: "truncore",
    repository_name: "plane-demo",
    token: "demo-token-replace-me",
    webhook_secret: "demo-webhook-secret",
  },
};

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";
const TEST_ITEM_PREFIX = "[e2e]";

/** Name for a work item a test creates. Such items are deleted before and after every test. */
export const testItemName = (label: string) => `${TEST_ITEM_PREFIX} ${label}`;

const workspaceUrl = `${API_URL}/api/workspaces/${DEMO.workspaceSlug}`;

export async function getDemoProjectId(request: APIRequestContext) {
  const projects: { id: string; identifier: string }[] = await (await request.get(`${workspaceUrl}/projects/`)).json();
  const projectId = projects.find((project) => project.identifier === DEMO.projectIdentifier)?.id;
  if (!projectId) throw new Error("Demo project not found. Run `python manage.py seed_engineering_demo` first.");
  return projectId;
}

/**
 * Put the demo project back as the seed left it, through the same API the app uses: delete the test
 * work items, clear the work item filters the demo admin has saved, and restore the GitHub connection.
 */
async function resetDemoProject(request: APIRequestContext) {
  const projectId = await getDemoProjectId(request);

  await request.patch(`${workspaceUrl}/projects/${projectId}/user-properties/`, { data: { rich_filters: {} } });
  await request.delete(`${workspaceUrl}/projects/${projectId}/github/`);
  await request.put(`${workspaceUrl}/projects/${projectId}/github/`, { data: DEMO.github });

  const search = await request.get(`${workspaceUrl}/projects/${projectId}/search-issues/`, {
    params: { search: TEST_ITEM_PREFIX },
  });
  const workItems: { id: string; name: string }[] = await search.json();
  const testItems = workItems.filter((item) => item.name.startsWith(TEST_ITEM_PREFIX));
  const responses = await Promise.all(
    testItems.map((item) => request.delete(`${workspaceUrl}/projects/${projectId}/issues/${item.id}/`))
  );
  const failed = responses.find((response) => !response.ok());
  if (failed) throw new Error(`Could not delete a test work item: ${failed.status()} ${failed.url()}`);
}

/** Playwright's `test`, plus a clean demo project before and after every test. */
export const test = base.extend<{ demoProjectReset: void }>({
  demoProjectReset: [
    async ({ request }, use) => {
      await resetDemoProject(request);
      await use();
      await resetDemoProject(request);
    },
    { auto: true },
  ],
});

const EVIDENCE_DIR = path.resolve(import.meta.dirname, "../../../docs/phase-evidence");

/** Save a full-page screenshot as evidence for a phase, e.g. docs/phase-evidence/phase-1/01-create.png */
export async function saveEvidence(page: Page, phase: string, name: string) {
  await page.screenshot({ path: path.join(EVIDENCE_DIR, `phase-${phase}`, `${name}.png`), fullPage: true });
}

/** A work item's row in the list or board layout. */
export const workItemRow = (page: Page, name: string) =>
  page.locator('[id^="issue-"]').filter({ hasText: name }).first();

/** Open a work item's own page from its row in the current list. */
export async function openWorkItemPage(page: Page, name: string) {
  const identifier = await workItemRow(page, name)
    .getByText(new RegExp(`^${DEMO.projectIdentifier}-\\d+$`))
    .innerText();
  await page.goto(`/${DEMO.workspaceSlug}/browse/${identifier}/`);
  // The first visit compiles the page in development, which can take much longer than an assertion.
  await page.getByText(identifier).first().waitFor({ timeout: 180_000 });
}

/** Open one of the demo project's pages from the sidebar, e.g. "Work items" or "Cycles". */
export async function openProjectPage(page: Page, pageName: string) {
  await page.goto(`/${DEMO.workspaceSlug}/`);
  const sidebar = page.getByRole("complementary", { name: "Main sidebar" });
  const link = sidebar.getByRole("link", { name: pageName, exact: true });
  const project = sidebar.getByText(DEMO.projectName, { exact: true });
  await project.waitFor();
  if (!(await link.isVisible())) await project.click();
  await link.click();
}
