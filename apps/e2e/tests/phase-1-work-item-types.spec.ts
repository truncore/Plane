/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { openProjectPage, openWorkItemPage, saveEvidence, test, testItemName, workItemRow } from "./helpers";

async function createWorkItem(page: Page, name: string, type?: "User Story" | "Task") {
  await page.getByRole("button", { name: "Add work item" }).click();
  const dialog = page.getByRole("dialog", { name: "Create new work item" });
  await dialog.getByRole("textbox", { name: "Title" }).fill(name);
  if (type) {
    await page.getByTestId("create-work-item-type-select").click();
    await page.getByRole("option", { name: type }).click();
  }
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
}

test("work items can be User Stories or Tasks", async ({ page }) => {
  const runId = Date.now().toString().slice(-6);
  const storyName = testItemName(`Story ${runId}: checkout shows a total`);
  const taskName = testItemName(`Task ${runId}: add the total component`);

  await openProjectPage(page, "Work items");
  await page.getByRole("button", { name: "List Layout" }).click();

  await test.step("create form offers both types, Task by default", async () => {
    await page.getByRole("button", { name: "Add work item" }).click();
    await expect(page.getByTestId("create-work-item-type-select")).toHaveText("Task");
    await page.getByTestId("create-work-item-type-select").click();
    await expect(page.getByRole("option", { name: "User Story" })).toBeVisible();
    await expect(page.getByRole("option", { name: "Task" })).toBeVisible();
    await saveEvidence(page, "1", "01-create-form-type-picker");
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Discard" }).click();
  });

  await test.step("create a User Story and a Task", async () => {
    await createWorkItem(page, storyName, "User Story");
    await createWorkItem(page, taskName);
    await expect(workItemRow(page, storyName).getByTestId("work-item-type-badge")).toHaveText("User Story");
    await expect(workItemRow(page, taskName)).toBeVisible();
    await expect(workItemRow(page, taskName).getByTestId("work-item-type-badge")).toHaveCount(0);
    await saveEvidence(page, "1", "02-list-badge");
  });

  await test.step("the badge shows on the board layout", async () => {
    await page.getByRole("button", { name: "Board Layout" }).click();
    await expect(workItemRow(page, storyName).getByTestId("work-item-type-badge")).toBeVisible();
    await saveEvidence(page, "1", "03-board-badge");
    await page.getByRole("button", { name: "List Layout" }).click();
  });

  await test.step("switch the type later and see it in the activity", async () => {
    await workItemRow(page, taskName).getByText(taskName).click();
    const typeSelect = page.getByTestId("work-item-type-select");
    await expect(typeSelect).toHaveText("Task");
    await typeSelect.click();
    await page.getByRole("option", { name: "User Story" }).click();
    await expect(typeSelect).toHaveText("User Story");
    await expect(page.getByText("changed the work item type to User Story").first()).toBeVisible();
    await saveEvidence(page, "1", "04-peek-type-change-activity");

    await typeSelect.click();
    await page.getByRole("option", { name: "Task" }).click();
    await expect(page.getByText("changed the work item type to Task").first()).toBeVisible();
    await page.keyboard.press("Escape");
  });

  await test.step("the badge shows on the work item's own page", async () => {
    await openWorkItemPage(page, storyName);
    await expect(page.getByTestId("work-item-type-badge").first()).toHaveText("User Story");
    await expect(page.getByTestId("work-item-type-select")).toHaveText("User Story");
    await saveEvidence(page, "1", "05-detail-badge");
  });

  await test.step("filter the list by type", async () => {
    await openProjectPage(page, "Work items");
    await page.getByRole("combobox", { name: "Filters" }).click();
    await page.getByRole("option", { name: "Work item type" }).click();
    await page.getByRole("option", { name: "User Story" }).click();
    await page.keyboard.press("Escape");
    await expect(workItemRow(page, storyName)).toBeVisible();
    await expect(workItemRow(page, taskName)).toBeHidden();
    await saveEvidence(page, "1", "06-filter-by-type");
  });
});
