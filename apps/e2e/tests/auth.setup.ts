/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { test as setup } from "@playwright/test";
import { AUTH_FILE } from "../playwright.config";
import { DEMO } from "./helpers";

setup("sign in as the demo admin", async ({ page }) => {
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await page.locator("#email").fill(DEMO.email);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.locator("#password").fill(DEMO.password);
  await page.getByRole("button", { name: "Go to workspace" }).click();
  await page.waitForURL(new RegExp(`/${DEMO.workspaceSlug}/`));
  await page.context().storageState({ path: AUTH_FILE });
});
