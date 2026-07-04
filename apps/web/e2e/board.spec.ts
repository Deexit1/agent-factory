import { expect, test, type Page } from "@playwright/test";

import { createTicket, driveToEscalated, transition } from "./api";

const ACTOR_STORAGE_KEY = "agent-factory:actor-context";

async function setActor(page: Page, actor: string, role: "viewer" | "approver" | "admin") {
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    [ACTOR_STORAGE_KEY, JSON.stringify({ actor, role })],
  );
}

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

test("approver sees approval buttons on an escalated ticket; viewer does not", async ({
  page,
}) => {
  const ticket = await createTicket(`Escalation ${Date.now()}`);
  await driveToEscalated(ticket.id);

  await setActor(page, "human:viewer-e2e", "viewer");
  await page.goto("/");
  await page.getByTestId("column-escalated").locator(`[data-ticket-id="${ticket.id}"]`).click();
  await expect(page.getByTestId("ticket-drawer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await page.getByRole("button", { name: "Close ticket details" }).click();

  await setActor(page, "human:approver-e2e", "approver");
  await page.reload();
  await page.getByTestId("column-escalated").locator(`[data-ticket-id="${ticket.id}"]`).click();
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
});
