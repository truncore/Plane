/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import { openProjectPage, openWorkItemPage, saveEvidence, test, testItemName, workItemRow } from "./helpers";

// From the demo seed: a story with 3 tasks (1 done) and one of its tasks.
const SEEDED_STORY = "As a customer I can pay with a saved card";
const SEEDED_TASK = "Store card tokens securely";

test("User Stories and Tasks follow their own rules", async ({ page }) => {
  const runId = Date.now().toString().slice(-6);
  const storyName = testItemName(`Story ${runId}: pay by bank transfer`);
  const taskName = testItemName(`Task ${runId}: show bank details`);

  await openProjectPage(page, "Work items");
  await page.getByRole("button", { name: "List Layout" }).click();

  await test.step("stories show points and task progress; tasks show no points", async () => {
    const storyRow = workItemRow(page, SEEDED_STORY);
    await expect(storyRow.getByTestId("story-progress")).toContainText("1 of 3 tasks done");
    await expect(storyRow.getByRole("button", { name: /^Estimates/ })).toBeVisible();
    await expect(workItemRow(page, SEEDED_TASK).getByRole("button", { name: /^Estimates/ })).toHaveCount(0);
    await saveEvidence(page, "1b", "01-list-progress-and-points");

    await page.getByRole("button", { name: "Board Layout" }).click();
    await expect(workItemRow(page, SEEDED_STORY).getByTestId("story-progress")).toContainText("1 of 3 tasks done");
    await saveEvidence(page, "1b", "02-board-progress");
    await page.getByRole("button", { name: "List Layout" }).click();
  });

  await test.step("a new User Story gets the template and can have points; a Task cannot", async () => {
    await page.getByRole("button", { name: "Add work item" }).click();
    const dialog = page.getByRole("dialog", { name: "Create new work item" });
    await expect(dialog.getByRole("button", { name: "Estimate" })).toHaveCount(0);

    await page.getByTestId("create-work-item-type-select").click();
    await page.getByRole("option", { name: "User Story" }).click();
    await expect(dialog.getByText("As a [type of user], I want [goal] so that [reason].")).toBeVisible();
    await expect(dialog.getByText("Acceptance criteria")).toBeVisible();
    await expect(dialog.getByRole("button", { name: "Add parent" })).toHaveCount(0);
    await dialog.getByRole("button", { name: "Estimate" }).click();
    await page.getByRole("option", { name: "3", exact: true }).click();
    await dialog.getByRole("textbox", { name: "Title" }).fill(storyName);
    await saveEvidence(page, "1b", "03-create-story-template");
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();
    await expect(workItemRow(page, storyName).getByRole("button", { name: /^Estimates/ })).toBeVisible();
  });

  await test.step("a story becomes a task: its points are removed", async () => {
    await workItemRow(page, storyName).getByText(storyName).click();
    const typeSelect = page.getByTestId("work-item-type-select");
    await typeSelect.click();
    await page.getByRole("option", { name: "Task" }).click();
    await expect(typeSelect).toHaveText("Task");
    await expect(page.getByText("Estimate", { exact: true })).toHaveCount(0);
    await expect(workItemRow(page, storyName).getByRole("button", { name: /^Estimates/ })).toHaveCount(0);
    await saveEvidence(page, "1b", "04-story-to-task-clears-points");
    await page.keyboard.press("Escape");
  });

  await test.step("a task with no description becomes a story and gets the template", async () => {
    await page.getByRole("button", { name: "Add work item" }).click();
    const dialog = page.getByRole("dialog", { name: "Create new work item" });
    await dialog.getByRole("textbox", { name: "Title" }).fill(taskName);
    await dialog.getByRole("button", { name: "Save" }).click();
    await expect(dialog).toBeHidden();

    await workItemRow(page, taskName).getByText(taskName).click();
    await page.getByTestId("work-item-type-select").click();
    await page.getByRole("option", { name: "User Story" }).click();
    await expect(page.getByText("As a [type of user], I want [goal] so that [reason].")).toBeVisible();
    await saveEvidence(page, "1b", "05-task-to-story-template");
    await page.keyboard.press("Escape");
  });

  await test.step("a task under a story cannot become a story", async () => {
    await workItemRow(page, SEEDED_TASK).getByText(SEEDED_TASK).click();
    const typeSelect = page.getByTestId("work-item-type-select");
    await typeSelect.click();
    await page.getByRole("option", { name: "User Story" }).click();
    await expect(
      page.getByText("A User Story can't be a sub-work item. Remove its parent first.").first()
    ).toBeVisible();
    await expect(typeSelect).toHaveText("Task");
    await saveEvidence(page, "1b", "06-story-under-story-message");
    await page.keyboard.press("Escape");
  });

  await test.step("only a story offers sub-work items, with its progress", async () => {
    await openWorkItemPage(page, SEEDED_TASK);
    await expect(page.getByRole("button", { name: "Add sub-work item" })).toHaveCount(0);
    await expect(page.getByText("Estimate", { exact: true })).toHaveCount(0);

    await openProjectPage(page, "Work items");
    await openWorkItemPage(page, SEEDED_STORY);
    await expect(page.getByRole("button", { name: "Add sub-work item" }).first()).toBeVisible();
    await expect(page.getByText("1/3 Done")).toBeVisible();
    await saveEvidence(page, "1b", "07-story-detail-progress");
  });
});
