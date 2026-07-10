import { expect, test } from "@playwright/test";

import { loginAs } from "./api";

// T-210: a brand-new real login with no org membership anywhere used to be
// silently auto-joined into the shared "default" org — since that org is already
// onboarded by global-setup.ts, this test would previously have landed straight on
// the real board with no wizard at all, which was the actual bug. `orgId: null`
// simulates that exact "never-seen-before Google account" scenario via dev-login.
test("a brand-new signup with no org lands in the onboarding wizard, not a shared board", async ({
  page,
}) => {
  await loginAs(page, `pending-signup-${Date.now()}@example.com`, "viewer", null);

  await page.goto("/");

  await expect(page.getByText("Get started")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Acceptable use policy" })).toBeVisible();
  // No sidebar/nav chrome — the wizard is a full-screen takeover.
  await expect(page.getByRole("link", { name: "Board", exact: true })).toHaveCount(0);
});

test("two different brand-new signups do not see each other's org", async ({ browser }) => {
  const ctxA = await browser.newContext();
  const pageA = await ctxA.newPage();
  await loginAs(pageA, `pending-a-${Date.now()}@example.com`, "viewer", null);
  await pageA.goto("/");

  const ctxB = await browser.newContext();
  const pageB = await ctxB.newPage();
  await loginAs(pageB, `pending-b-${Date.now()}@example.com`, "viewer", null);
  await pageB.goto("/");

  // Both independently land on the wizard's first step — neither has a real org
  // yet, so there's no shared board (or shared anything) for them to collide on.
  await expect(pageA.getByRole("heading", { name: "Acceptable use policy" })).toBeVisible();
  await expect(pageB.getByRole("heading", { name: "Acceptable use policy" })).toBeVisible();

  await ctxA.close();
  await ctxB.close();
});
