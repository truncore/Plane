/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import { openProjectPage, saveEvidence, test } from "./helpers";

test("the demo workspace has a project with work items and a cycle", async ({ page }) => {
  await openProjectPage(page, "Work items");
  await expect(page.getByText("As a customer I can pay with a saved card")).toBeVisible();
  await expect(page.getByText("Store card tokens securely")).toBeVisible();
  await saveEvidence(page, "0", "01-work-items");

  await openProjectPage(page, "Cycles");
  await expect(page.getByText("Sprint 1").first()).toBeVisible();
  await saveEvidence(page, "0", "02-cycles");
});
