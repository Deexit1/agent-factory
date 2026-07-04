import { expect, test } from "@playwright/test";

test("app shell loads (login gate, unauthenticated) @smoke", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Agent Factory/ })).toBeVisible();
});
