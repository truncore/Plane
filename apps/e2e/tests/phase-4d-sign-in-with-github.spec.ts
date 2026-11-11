/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import { API_URL, saveEvidence, test } from "./helpers";

test("connect a personal GitHub account with the GitHub App", async ({ page, request }) => {
  const account = (await (await request.get(`${API_URL}/api/users/me/github/`)).json()) as { oauth_available: boolean };

  await test.step("a callback that Plane didn't start is refused", async () => {
    await page.goto(`${API_URL}/api/github/oauth/callback/?code=stolen-code&state=forged`);
    await page.waitForURL(/\/settings\/profile\/github\?github=error/);
    await expect(page.getByText("Connecting to GitHub didn't work.")).toBeVisible();
    await saveEvidence(page, "4d", "01-forged-callback-refused");
  });

  await test.step("cancelling on GitHub is explained", async () => {
    await page.goto("/settings/profile/github?github=denied");
    await expect(page.getByText("You cancelled on GitHub, so nothing was connected.")).toBeVisible();
  });

  await test.step("the profile page offers the right way to connect", async () => {
    await page.goto("/settings/profile/github");
    if (account.oauth_available) {
      await page.getByRole("link", { name: "Connect with GitHub" }).click();
      await page.waitForURL(/github\.com\/login/);
      expect(page.url()).toContain("client_id");
      await saveEvidence(page, "4d", "02-github-consent");
    } else {
      // Without the GitHub App's keys, pasting a personal token is the fallback
      await expect(page.getByLabel("Personal access token")).toBeVisible();
      await expect(page.getByRole("link", { name: "Connect with GitHub" })).toHaveCount(0);
      await saveEvidence(page, "4d", "02-fallback-without-github-app");
    }
  });
});
