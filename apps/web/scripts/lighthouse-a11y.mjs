// SPEC-002 AC #5: Lighthouse a11y score >= 90 on the board page.
import { setTimeout as sleep } from "node:timers/promises";

import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

const URL_UNDER_TEST = process.env.A11Y_URL ?? "http://localhost:5173/";
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

async function main() {
  await waitForServer(URL_UNDER_TEST);

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
