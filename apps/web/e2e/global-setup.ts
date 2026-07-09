// Onboarding-gate enforcement (apps/web/src/App.tsx) means the board is unreachable
// for any org that hasn't accepted the ToS, added a BYOK key, and connected a repo.
// Every existing test in this suite logs into the pre-existing "default" org (via
// e2e/api.ts's loginAs), which predates onboarding entirely — so this runs ONCE,
// before any test, and completes real onboarding for that org via the same live API
// calls a real user's browser would make. Nothing in board.spec.ts/smoke.spec.ts needs
// to change: by the time they run, "default" is already a fully-onboarded org, exactly
// like any other operating org.
//
// Uses PROVIDER_KEY_VALIDATION_SKIP / FIXTURE_REPO_PROVISIONING (both set by
// apps/api/scripts/e2e-server.sh) so the key/repo steps succeed without a live
// Anthropic account or a registered GitHub App — neither exists in this environment.

const API_URL = "http://localhost:8000";

async function ok(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new Error(`${response.url} -> ${response.status}: ${await response.text()}`);
  }
  return response;
}

async function json<T>(response: Response): Promise<T> {
  return (await ok(response)).json() as Promise<T>;
}

export default async function globalSetup(): Promise<void> {
  const login = await fetch(`${API_URL}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email: "e2e-onboarding-bootstrap@example.com",
      role: "owner",
      org_id: "default",
    }),
  });
  const { token } = await json<{ token: string }>(login);
  const headers = { "Content-Type": "application/json", Authorization: `Bearer ${token}` };

  const status = await json<{
    tos_accepted: boolean;
    has_provider_key: boolean;
    has_repo: boolean;
  }>(await fetch(`${API_URL}/orgs/default/onboarding-status`, { headers }));

  if (!status.tos_accepted) {
    const tos = await json<{ version: string }>(await fetch(`${API_URL}/tos`, { headers }));
    await ok(
      await fetch(`${API_URL}/orgs/default/tos/accept`, {
        method: "POST",
        headers,
        body: JSON.stringify({ tos_version: tos.version }),
      }),
    );
  }

  if (!status.has_provider_key) {
    await json(
      await fetch(`${API_URL}/orgs/default/provider-keys`, {
        method: "POST",
        headers,
        body: JSON.stringify({ provider: "anthropic", api_key: "e2e-fixture-key-not-real" }),
      }),
    );
  }

  if (!status.has_repo) {
    await json(
      await fetch(`${API_URL}/orgs/default/repos/provisioned`, {
        method: "POST",
        headers,
        body: JSON.stringify({ name: "e2e-default-repo" }),
      }),
    );
  }
}
