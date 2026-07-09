import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  // Onboarding-gate enforcement (apps/web/src/App.tsx): completes real onboarding for
  // the pre-existing "default" org once, before any test, so every test's dev-login
  // (e2e/api.ts's loginAs) lands in an already-onboarded org — no per-test changes.
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  // Mock-free per SPEC-002 AC #1: both the web dev server and a real, migrated API
  // (backed by a real Postgres) are started for the suite — no mocked fetch/WS.
  webServer: [
    {
      command: "npm run dev",
      url: "http://localhost:5173",
      reuseExistingServer: !process.env.CI,
    },
    {
      command: "bash ../api/scripts/e2e-server.sh",
      url: "http://localhost:8000/health",
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
});
