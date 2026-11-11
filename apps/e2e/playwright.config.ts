/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { defineConfig } from "@playwright/test";

export const AUTH_FILE = ".auth/demo-admin.json";

export default defineConfig({
  testDir: "./tests",
  // The dev server compiles pages on first visit, so allow slow first loads.
  timeout: 360_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    viewport: { width: 1440, height: 900 },
    navigationTimeout: 180_000,
    trace: "retain-on-failure",
  },
  projects: [
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    { name: "chromium", dependencies: ["setup"], use: { storageState: AUTH_FILE } },
  ],
});
