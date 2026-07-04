import { expect, test } from "@playwright/test";

import { createTicket, driveToEscalated, loginAs, transition } from "./api";

test.beforeEach(async ({ page }) => {
  await loginAs(page, "e2e-default@example.com", "viewer");
});

test("board renders tickets grouped by state from the real API", async ({ page }) => {
  const ticket = await createTicket(`Grouped-by-state ${Date.now()}`);

  await page.goto("/");

  const readyCard = page
    .getByTestId("column-ready")
    .locator(`[data-ticket-id="${ticket.id}"]`);
  await expect(readyCard).toBeVisible();
  await expect(readyCard).toContainText(ticket.id);
});

test("dragging a ticket through an illegal transition snaps back and shows the API reason", async ({
  page,
}) => {
  const ticket = await createTicket(`Illegal-drag ${Date.now()}`);
  await page.goto("/");

  const card = page.locator(`[data-ticket-id="${ticket.id}"]`);
  await card.scrollIntoViewIfNeeded();
  const cardBox = await card.boundingBox();
  const targetBox = await page.getByTestId("column-escalated").boundingBox();
  if (!cardBox || !targetBox) throw new Error("missing bounding boxes");

  await page.mouse.move(cardBox.x + cardBox.width / 2, cardBox.y + cardBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(cardBox.x + cardBox.width / 2 + 20, cardBox.y + cardBox.height / 2, {
    steps: 5,
  });
  await page.mouse.move(targetBox.x + targetBox.width / 2, targetBox.y + 50, { steps: 10 });
  await page.mouse.up();

  await expect(page.getByTestId("transition-error")).toContainText(
    "not a whitelisted transition",
  );
  await expect(page.getByTestId("column-ready").locator(`[data-ticket-id="${ticket.id}"]`)).toBeVisible();
});

test("new ticket_events appear in an open drawer within 2s over the websocket", async ({
  page,
}) => {
  const ticket = await createTicket(`Live-feed ${Date.now()}`);
  await page.goto("/");

  await page.locator(`[data-ticket-id="${ticket.id}"]`).click();
  await expect(page.getByTestId("ticket-drawer")).toHaveAttribute("data-ws-connected", "true");

  await transition(ticket.id, "in_progress");

  await expect(page.getByTestId("event-feed")).toContainText("transition", { timeout: 2000 });
});

test("approver sees the escalation inbox on an escalated ticket; viewer does not", async ({
  page,
}) => {
  const ticket = await createTicket(`Escalation ${Date.now()}`);
  await driveToEscalated(ticket.id);

  await loginAs(page, "viewer-e2e@example.com", "viewer");
  await page.goto("/");
  await page.getByTestId("column-escalated").locator(`[data-ticket-id="${ticket.id}"]`).click();
  await expect(page.getByTestId("ticket-drawer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Return to dev" })).toHaveCount(0);
  await page.getByRole("button", { name: "Close ticket details" }).click();

  await loginAs(page, "approver-e2e@example.com", "approver");
  await page.reload();
  await page.getByTestId("column-escalated").locator(`[data-ticket-id="${ticket.id}"]`).click();
  await expect(page.getByRole("button", { name: "Return to dev" })).toBeVisible();
});
