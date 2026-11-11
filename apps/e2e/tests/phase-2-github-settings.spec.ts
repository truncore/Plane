/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { expect } from "@playwright/test";
import { DEMO, getDemoProjectId, saveEvidence, test } from "./helpers";

const FAKE_TOKEN = "github_pat_e2e_not_a_real_token";

test("a project admin connects GitHub, tests it and changes the settings", async ({ page, request }) => {
  const projectId = await getDemoProjectId(request);
  const settingsUrl = `/${DEMO.workspaceSlug}/settings/projects/${projectId}/github`;
  const repository = page.getByRole("textbox", { name: "Repository" });

  await test.step("start from a disconnected project", async () => {
    await page.goto(settingsUrl);
    await page.getByRole("button", { name: "Disconnect" }).click();
    await expect(page.getByRole("button", { name: "Connect repository" })).toBeVisible();
    await expect(page.getByText("/api/github/webhook/")).toBeVisible();
    await saveEvidence(page, "2", "01-not-connected");
  });

  await test.step("the form explains what is missing", async () => {
    await repository.fill("not a repository");
    await page.getByRole("button", { name: "Connect repository" }).click();
    await expect(page.getByText("Use the form owner/name, for example truncore/plane.")).toBeVisible();
    await expect(page.getByText("Enter an access token.")).toBeVisible();
    await saveEvidence(page, "2", "02-validation");
  });

  await test.step("connect with trunk-based defaults", async () => {
    await repository.fill(`${DEMO.github.repository_owner}/${DEMO.github.repository_name}`);
    await page.getByLabel("Access token").fill(FAKE_TOKEN);
    await page.getByRole("button", { name: "Generate" }).click();
    await expect(page.getByLabel("Webhook secret")).toHaveValue(/^[0-9a-f]{48}$/);
    await expect(page.getByRole("radio", { name: /Trunk-based/ })).toBeChecked();
    await expect(page.getByRole("textbox", { name: "Trunk branch" })).toHaveValue("main");
    await page.getByRole("button", { name: "Connect repository" }).click();

    await expect(page.getByText("Connected to truncore/plane-demo")).toBeVisible();
    await expect(page.getByTestId("github-review_state_id")).toHaveText("In Review");
    await expect(page.getByTestId("github-merged_state_id")).toHaveText("Done");
    await expect(page.getByLabel("Access token")).toHaveValue("");
    expect(await page.content()).not.toContain(FAKE_TOKEN);
    await saveEvidence(page, "2", "03-connected");
  });

  await test.step("test the connection: a fake token gets a clear message", async () => {
    await page.getByRole("button", { name: "Test connection" }).click();
    // GitHub rejects the fake token; without internet the message says GitHub can't be reached instead
    await expect(page.getByTestId("github-test-result")).toContainText(
      /GitHub rejected the token|Plane couldn't reach GitHub/
    );
    await saveEvidence(page, "2", "04-test-connection");
  });

  await test.step("change the base branch and the mode, and they stay saved", async () => {
    await page.getByRole("radio", { name: /Feature branches/ }).click();
    await expect(page.getByRole("textbox", { name: "Default base branch" })).toBeVisible();
    await expect(page.getByLabel("Warn when a branch is older than (days)")).toHaveCount(0);
    await page.getByRole("textbox", { name: "Default base branch" }).fill("develop");
    await page.getByRole("button", { name: "Save changes" }).click();
    await expect(page.getByText("GitHub settings saved.").first()).toBeVisible();

    await page.reload();
    await expect(page.getByRole("radio", { name: /Feature branches/ })).toBeChecked();
    await expect(page.getByRole("textbox", { name: "Default base branch" })).toHaveValue("develop");
    await saveEvidence(page, "2", "05-feature-branches-saved");
  });
});
