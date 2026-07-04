import { expect, test } from "@playwright/test";

test("board shell loads @smoke", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Agent Factory" })).toBeVisible();
});
