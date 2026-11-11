/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { createWorkItem, sendPullRequestEvent, sendTrunkPush } from "./github";
import { openWorkItemByKey, saveEvidence, test, testItemName } from "./helpers";

/** GitHub events are applied in the background, so reload until the work item shows the result. */
async function expectAfterReload(page: Page, check: () => Promise<void>) {
  await expect(async () => {
    await page.reload();
    await check();
  }).toPass({ timeout: 90_000, intervals: [2_000, 4_000] });
}

test("work items follow their pull requests and trunk commits", async ({ page, request }) => {
  const runId = Date.now().toString().slice(-6);
  const prNumber = Number(runId);
  const state = page.getByTestId("work-item-state-select");
  const github = page.getByTestId("work-item-github");

  await test.step("opening a pull request moves the item to In Review", async () => {
    const item = await createWorkItem(request, testItemName(`Story ${runId}: pay by link`));
    const branch = `feat/${item.key.toLowerCase()}-pay-by-link`;
    await openWorkItemByKey(page, item.key);
    await expect(state).toHaveText("Backlog");

    await sendPullRequestEvent(request, `[${item.key}] Pay by link`, { number: prNumber, branch, action: "opened" });
    await expectAfterReload(page, async () => {
      await expect(state).toHaveText("In Review", { timeout: 5_000 });
      await expect(github).toContainText(`#${prNumber}`, { timeout: 5_000 });
    });
    await expect(github).toContainText("Open");
    await saveEvidence(page, "3", "01-pr-opened-in-review");

    await test.step("merging it moves the item to Done", async () => {
      await sendPullRequestEvent(request, `[${item.key}] Pay by link`, {
        number: prNumber,
        branch,
        action: "closed",
        merged: true,
      });
      await expectAfterReload(page, async () => {
        await expect(state).toHaveText("Done", { timeout: 5_000 });
        await expect(github).toContainText("Merged", { timeout: 5_000 });
      });
      await saveEvidence(page, "3", "02-pr-merged-done");
    });
  });

  await test.step("closing a pull request without merging keeps the state and adds a comment", async () => {
    const item = await createWorkItem(request, testItemName(`Story ${runId}: split payments`));
    const branch = `feat/${item.key.toLowerCase()}-split`;
    await sendPullRequestEvent(request, `[${item.key}] Split payments`, {
      number: prNumber + 1,
      branch,
      action: "opened",
    });
    await sendPullRequestEvent(request, `[${item.key}] Split payments`, {
      number: prNumber + 1,
      branch,
      action: "closed",
    });
    await openWorkItemByKey(page, item.key);
    await expectAfterReload(page, async () => {
      await expect(page.getByText("was closed without merging").first()).toBeVisible({ timeout: 5_000 });
    });
    await expect(state).toHaveText("In Review");
    await expect(github).toContainText("Closed");
    await saveEvidence(page, "3", "03-pr-closed-comment");
  });

  await test.step("a trunk commit that says fixes completes the item and is listed on it", async () => {
    const item = await createWorkItem(request, testItemName(`Task ${runId}: receipt footer`));
    await sendTrunkPush(request, `Add the receipt footer, fixes ${item.key}`);
    await openWorkItemByKey(page, item.key);
    await expectAfterReload(page, async () => {
      await expect(state).toHaveText("Done", { timeout: 5_000 });
    });
    await expect(github).toContainText(`Add the receipt footer, fixes ${item.key}`);
    await saveEvidence(page, "3", "04-trunk-commit-done");
  });
});
