import { expect, test } from "@playwright/test";

import { loginAs } from "./api";

test.beforeEach(async ({ page }) => {
  await loginAs(page, "e2e-default@example.com", "viewer");
});

test("a non-staff user hitting a staff route directly is redirected to the board", async ({
  page,
}) => {
  await page.goto("/admin/impersonate");

  await expect(page).toHaveURL(/\/board$/);
  await expect(page.getByTestId("column-ready")).toBeVisible();
});

test("billing page renders for an onboarded org", async ({ page }) => {
  await page.goto("/billing");

  await expect(page.getByRole("heading", { name: "Billing" })).toBeVisible();
});

test("members page renders for an onboarded org", async ({ page }) => {
  await page.goto("/members");

  await expect(page.getByRole("heading", { name: "Members" })).toBeVisible();
});
