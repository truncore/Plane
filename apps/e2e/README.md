# e2e

Playwright browser tests that click through the running app.

## Run

1. Start the backend and web apps (see the root README), then create the demo data:
   `docker compose -f docker-compose-local.yml exec api python manage.py seed_engineering_demo`
2. Install the browser once: `pnpm --filter e2e exec playwright install chromium`
3. Run: `pnpm --filter e2e test:e2e` (or one file: `pnpm --filter e2e test:e2e phase-1`)

Tests sign in as the demo admin from the seed. Screenshots go to `docs/phase-evidence/phase-<N>/`.
Set `E2E_BASE_URL` and `E2E_API_URL` to test another instance.

Work items a test creates are named with `testItemName()` (prefix `[e2e]`); they are deleted before and
after every test, so the demo project stays as the seed left it.
