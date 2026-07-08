import type { Page } from "@playwright/test";

const API_URL = "http://localhost:8000";

// Must match apps/api/scripts/e2e-server.sh's AGENT_FACTORY_SERVICE_TOKEN default —
// this file seeds fixtures the same way the orchestrator/sandbox call the API (SPEC-006).
const SERVICE_TOKEN = "e2e-service-token-at-least-32-bytes";
const SERVICE_HEADERS = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${SERVICE_TOKEN}`,
};

interface CreatedTicket {
  id: string;
  state: string;
}

export async function createTicket(title: string, budgetUsd = 50): Promise<CreatedTicket> {
  const response = await fetch(`${API_URL}/tickets`, {
    method: "POST",
    headers: SERVICE_HEADERS,
    body: JSON.stringify({
      type: "task",
      title,
      created_by: "human:e2e",
      budget_usd: budgetUsd,
      acceptance_criteria: [{ id: "AC-1", description: "works", verification: "manual" }],
    }),
  });
  if (!response.ok) {
    throw new Error(`createTicket failed: ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as CreatedTicket;
}

export async function transition(
  ticketId: string,
  toState: string,
  actor = "human:e2e",
): Promise<Response> {
  return fetch(`${API_URL}/tickets/${ticketId}/transition`, {
    method: "POST",
    headers: SERVICE_HEADERS,
    body: JSON.stringify({ to_state: toState, actor }),
  });
}

export async function loginAs(
  page: Page,
  email: string,
  role: "viewer" | "approver" | "member" | "owner",
): Promise<void> {
  const response = await fetch(`${API_URL}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, role }),
  });
  if (!response.ok) {
    throw new Error(`dev-login failed: ${response.status} ${await response.text()}`);
  }
  const { token } = (await response.json()) as { token: string };
  await page.addInitScript(
    ([key, value]) => window.localStorage.setItem(key, value),
    ["agent-factory:session-token", token],
  );
}

export async function driveToEscalated(ticketId: string): Promise<void> {
  await transition(ticketId, "in_progress");
  for (let i = 0; i < 3; i += 1) {
    await transition(ticketId, "in_review");
    await transition(ticketId, "in_qa");
    await transition(ticketId, "bounced");
    await transition(ticketId, "in_progress");
  }
  await transition(ticketId, "in_review");
  await transition(ticketId, "in_qa");
  await transition(ticketId, "bounced"); // 4th bounce attempt -> auto-escalates
}
