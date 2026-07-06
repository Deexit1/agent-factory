# SPEC-203 — GitHub Connect & Provisioned Repos

## Goal
Agents deliver code to the CUSTOMER's repos (GitHub App install) or to a provisioned
repo we hand over.

## In scope
- GitHub App: contents + pull-requests permissions on selected repos only; install/
  uninstall flow in org settings; installation tokens minted per ticket, scoped to
  `agent/*` branches (replaces the single-app assumption in SPEC-003).
- Provisioned mode: create repo under the platform org from a template; export =
  ownership transfer or bundle download.
- Repo registry per org: default branch, CI mode (our runners vs their existing CI),
  protected-branch rules verified at connect time.
- Webhooks: PR/CI events from customer repos drive ticket transitions exactly like
  internal repos (signature-verified).
- Uninstall/disconnect handling: in-flight tickets → `blocked` with a clear event.

## Acceptance criteria
1. Connect flow on a test org results in an agent PR on the customer repo from a
   `agent/T-xxx` branch; push to their default branch is impossible (rejected test).
2. Tokens expire ≤ 1h and are minted per ticket (token introspection test).
3. Forged webhook signature is rejected and logged.
4. Disconnecting the App blocks in-flight tickets within 60s with events explaining why.
5. Provisioned repo export transfers ownership and revokes platform access.
