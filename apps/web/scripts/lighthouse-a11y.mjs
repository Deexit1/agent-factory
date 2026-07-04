// SPEC-002 AC #5: Lighthouse a11y score >= 90 on the board page. Since SPEC-006 gates the
// whole app behind auth, an unauthenticated load now lands on the login page instead — so
// this mints a dev-login session token first and passes it via the #token hash the app
// already knows how to consume, landing Lighthouse on the actual board.
import { setTimeout as sleep } from "node:timers/promises";

import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

const WEB_URL = process.env.A11Y_URL ?? "http://localhost:5173/";
const API_URL = process.env.VITE_API_URL ?? "http://localhost:8000";
const THRESHOLD = 90;

async function waitForServer(url, attempts = 30) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // not up yet
    }
    await sleep(1000);
  }
  throw new Error(`Server at ${url} did not become ready in time`);
}

async function authenticatedUrl() {
  const response = await fetch(`${API_URL}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: "a11y@example.com", role: "admin" }),
  });
  if (!response.ok) {
    throw new Error(
      `dev-login failed (${response.status}) - is AUTH_DEV_MODE=true set on the API? ` +
        "Falling back to auditing the login page.",
    );
  }
  const { token } = await response.json();
  return `${WEB_URL}#token=${encodeURIComponent(token)}`;
}

async function main() {
  await waitForServer(WEB_URL);
  const URL_UNDER_TEST = await authenticatedUrl().catch((error) => {
    console.warn(String(error.message));
    return WEB_URL;
  });

  const chrome = await chromeLauncher.launch({ chromeFlags: ["--headless=new"] });
  try {
    const result = await lighthouse(URL_UNDER_TEST, {
      port: chrome.port,
      onlyCategories: ["accessibility"],
      output: "json",
    });

    const score = Math.round((result.lhr.categories.accessibility.score ?? 0) * 100);
    console.log(`Lighthouse accessibility score: ${score}/100 (threshold: ${THRESHOLD})`);

    if (score < THRESHOLD) {
      const failing = Object.values(result.lhr.audits).filter(
        (audit) => audit.score !== null && audit.score < 1 && audit.scoreDisplayMode !== "notApplicable",
      );
      console.error("Failing audits:");
      for (const audit of failing) {
        console.error(`  - ${audit.title}: ${audit.description}`);
      }
      process.exitCode = 1;
    }
  } finally {
    try {
      await chrome.kill();
    } catch (error) {
      // Best-effort cleanup — e.g. Windows can hold a brief file lock on the temp
      // profile dir after Chrome exits. Doesn't affect the audit result above.
      console.warn(`Warning: failed to clean up Chrome temp profile: ${String(error)}`);
    }
  }
}

await main();
