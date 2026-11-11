/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createWorkItem } from "./github";
import { API_URL, DEMO, getDemoProjectId, openWorkItemByKey, saveEvidence, test, testItemName } from "./helpers";

const DAY = 24 * 60 * 60 * 1000;

/**
 * Answer the dialog's GitHub calls in the browser, as GitHub would through Plane. The real endpoints are
 * covered by backend tests with GitHub mocked; this checks the dialog itself.
 */
async function mockGitHub(page: Page, branch: string, preview: object) {
  const created: { body?: Record<string, string> } = {};
  await page.route("**/github/branches/", (route) =>
    route.fulfill({
      json: {
        branches: [
          { name: branch, last_commit_at: new Date(Date.now() - DAY).toISOString(), suggested: true },
          {
            name: "feat/old-experiment",
            last_commit_at: new Date(Date.now() - 9 * DAY).toISOString(),
            suggested: false,
          },
        ],
        base_branch: "main",
        workflow_mode: "trunk_based",
        branch_age_limit_days: 2,
        large_pr_lines: 400,
      },
    })
  );
  await page.route("**/github/preview/**", (route) => route.fulfill({ json: preview }));
  await page.route("**/github/pull-requests/", async (route) => {
    created.body = route.request().postDataJSON();
    await route.fulfill({ status: 201, json: { id: "pr", number: 77, state: "open" } });
  });
  return created;
}

test("open a pull request from a work item", async ({ page, request }) => {
  const dialog = page.getByTestId("create-pr-dialog");
  const createButton = page.getByRole("button", { name: "Create pull request" });

  await test.step("with the placeholder token, GitHub's refusal is explained", async () => {
    const item = await createWorkItem(request, testItemName("Story: pay by bank link"));
    await openWorkItemByKey(page, item.key);
    await page.getByRole("button", { name: "Create PR" }).click();
    await expect(dialog).toContainText(/GitHub rejected the token|Plane couldn't reach GitHub/);
    await expect(createButton).toBeDisabled();
    await saveEvidence(page, "4", "01-bad-token");
    await page.keyboard.press("Escape");
  });

  await test.step("pick the suggested branch, see the warnings and create it", async () => {
    const item = await createWorkItem(request, testItemName("Story: pay by QR code"));
    const branch = `feat/${item.key.toLowerCase()}-qr-code`;
    const created = await mockGitHub(page, branch, {
      ahead_by: 3,
      changed_files: 6,
      changed_lines: 520,
      branch_age_days: 4,
      is_old_branch: true,
      is_large: true,
      existing_pull_request_url: null,
    });
    await openWorkItemByKey(page, item.key);
    await page.getByRole("button", { name: "Create PR" }).click();

    await expect(page.getByTestId("create-pr-branch-select")).toHaveText(branch);
    await expect(page.getByRole("textbox", { name: "Title" })).toHaveValue(`[${item.key}] [e2e] Story: pay by QR code`);
    await expect(page.getByRole("textbox", { name: "Description" })).toHaveValue(
      new RegExp(`Work item: \\[${item.key}\\]\\(.*/${DEMO.workspaceSlug}/browse/${item.key}/\\)`)
    );
    await expect(page.getByTestId("create-pr-summary")).toHaveText("3 commits ahead · 520 lines changed in 6 files");
    await expect(dialog).toContainText("This branch started 4 days ago, past the 2-day limit");
    await expect(dialog).toContainText("changes 520 lines, more than the 400-line limit");
    await page.getByTestId("create-pr-branch-select").click();
    await expect(
      page.getByRole("option", { name: /feat\/old-experiment .*older than the branch age limit/ })
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await saveEvidence(page, "4", "02-dialog-with-warnings");

    await createButton.click();
    await expect(page.getByText("Pull request #77 opened.").first()).toBeVisible();
    expect(created.body).toMatchObject({
      base: "main",
      head: branch,
      title: `[${item.key}] [e2e] Story: pay by QR code`,
    });
    await page.unrouteAll();
  });

  await test.step("a branch with nothing new can't be turned into a pull request", async () => {
    const item = await createWorkItem(request, testItemName("Story: pay later"));
    await mockGitHub(page, `feat/${item.key.toLowerCase()}-pay-later`, {
      ahead_by: 0,
      changed_files: 0,
      changed_lines: 0,
      branch_age_days: 0,
      is_old_branch: false,
      is_large: false,
      existing_pull_request_url: null,
    });
    await openWorkItemByKey(page, item.key);
    await page.getByRole("button", { name: "Create PR" }).click();
    await expect(dialog).toContainText("This branch has no commits that aren't already in the base branch.");
    await expect(createButton).toBeDisabled();
    await saveEvidence(page, "4", "03-no-commits");
    await page.keyboard.press("Escape");
    await page.unrouteAll();
  });

  await test.step("a project without GitHub explains who can connect it", async () => {
    const projectId = await getDemoProjectId(request);
    await request.delete(`${API_URL}/api/workspaces/${DEMO.workspaceSlug}/projects/${projectId}/github/`);
    const item = await createWorkItem(request, testItemName("Story: pay by voucher"));
    await openWorkItemByKey(page, item.key);
    await page.getByRole("button", { name: "Create PR" }).click();
    await expect(dialog).toContainText("This project isn't connected to GitHub yet.");
    await saveEvidence(page, "4", "04-not-connected");
  });
});
