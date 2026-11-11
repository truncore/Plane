/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createWorkItem, sendPullRequestEvent } from "./github";
import { API_URL, DEMO, getDemoProjectId, openWorkItemByKey, saveEvidence, test, testItemName } from "./helpers";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

const DETAILS = /\/github\/pull-requests\/[0-9a-f-]{36}\/$/;

/** Answer the pull request panel's GitHub calls in the browser; the endpoints have backend tests. */
async function mockPullRequestDetails(page: Page, actingAs: string | null) {
  const sent: Record<string, unknown> = {};
  await page.route(DETAILS, (route) =>
    route.fulfill({
      json: {
        url: "https://github.com/truncore/plane-demo/pull/1",
        files_url: "https://github.com/truncore/plane-demo/pull/1/files",
        state: "open",
        mergeable_state: "clean",
        reviewers: [
          { login: "omar-farouk", state: "APPROVED" },
          { login: "lina-nasser", state: "PENDING" },
        ],
        checks: [{ name: "tests", status: "completed", conclusion: "success", url: "https://github.com" }],
        acting_as: actingAs,
        can_review: !!actingAs,
        can_merge: !!actingAs,
      },
    })
  );
  await Promise.all(
    ["reviews", "reviewers", "merge"].map((action) =>
      page.route(new RegExp(`/github/pull-requests/[0-9a-f-]{36}/${action}/$`), async (route) => {
        sent[action] = route.request().postDataJSON();
        await route.fulfill({ status: 204 });
      })
    )
  );
  return sent;
}

test("review and merge from Plane, and copy a branch name", async ({ page, request }) => {
  const runId = Date.now().toString().slice(-6);

  await test.step("a personal GitHub token is checked with GitHub before it is saved", async () => {
    await page.goto("/settings/profile/github");
    await page.getByLabel("Personal access token").fill("github_pat_not_a_real_token");
    await page.getByRole("button", { name: "Connect", exact: true }).click();
    await expect(page.getByText(/GitHub rejected the token|Plane couldn't reach GitHub/)).toBeVisible();
    await saveEvidence(page, "4b", "01-personal-account-bad-token");
  });

  const item = await createWorkItem(request, testItemName(`Story ${runId}: reset password`));

  await test.step("copy the branch name", async () => {
    await openWorkItemByKey(page, item.key);
    await page.getByRole("button", { name: "Copy branch name" }).click();
    const expected = `feat/${item.key.toLowerCase()}-e2e-story-${runId}-reset-password`;
    await expect(page.getByText(expected).first()).toBeVisible();
    expect(await page.evaluate("navigator.clipboard.readText()")).toBe(expected);
    await saveEvidence(page, "4b", "02-copy-branch-name");
  });

  await sendPullRequestEvent(request, `[${item.key}] Reset password`, {
    number: Number(runId),
    branch: `feat/${item.key.toLowerCase()}-reset-password`,
    action: "opened",
  });

  await test.step("without a personal account, the panel says how to connect one", async () => {
    // The webhook is applied in the background: wait until the work item lists the pull request
    const projectId = await getDemoProjectId(request);
    const githubUrl = `${API_URL}/api/workspaces/${DEMO.workspaceSlug}/projects/${projectId}/issues/${item.id}/github/`;
    await expect
      .poll(
        async () => ((await (await request.get(githubUrl)).json()) as { pull_requests: unknown[] }).pull_requests.length
      )
      .toBe(1);
    await mockPullRequestDetails(page, null);
    await page.reload();
    await page.getByRole("button", { name: "Details" }).click();
    await expect(page.getByText("Connect your own GitHub account to review and merge from Plane.")).toBeVisible();
    await page.unrouteAll();
  });

  await test.step("see reviews, checks and mergeability, approve and merge", async () => {
    const sent = await mockPullRequestDetails(page, "mariam-h");
    await page.reload();
    await page.getByRole("button", { name: "Details" }).click();
    const panel = page.getByTestId("pull-request-details");
    await expect(panel).toContainText("Ready to merge.");
    await expect(panel).toContainText("omar-farouk");
    await expect(panel).toContainText("Approved");
    await expect(panel).toContainText("Waiting");
    await expect(panel).toContainText("tests");
    await expect(panel).toContainText("Actions run as your GitHub account mariam-h.");
    await saveEvidence(page, "4b", "03-pull-request-panel");

    await panel.getByLabel("Comment").fill("Looks good");
    await panel.getByRole("button", { name: "Approve" }).click();
    await expect(page.getByText("Review sent.").first()).toBeVisible();
    expect(sent.reviews).toEqual({ event: "APPROVE", body: "Looks good" });

    await panel.getByRole("button", { name: "Merge", exact: true }).click();
    await expect(page.getByText("Pull request merged.").first()).toBeVisible();
    expect(sent.merge).toEqual({ method: "squash" });
    await saveEvidence(page, "4b", "04-approved-and-merged");
  });
});
