import { useEffect, useState } from "react";

import { ProviderKeysPage } from "../admin/ProviderKeysPage";
import { RepoConnectPage } from "../admin/RepoConnectPage";
import { useOnboardingStatus } from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { ByokSetupGuide } from "../docs/ByokSetupGuide";
import { CreateFirstIdeaStep } from "./CreateFirstIdeaStep";
import { CreateOrgStep } from "./CreateOrgStep";
import { TosAcceptanceStep } from "./TosAcceptanceStep";

type WizardStep = "tos" | "org" | "key" | "repo" | "idea";

const STEPS: { key: WizardStep; label: string }[] = [
  { key: "tos", label: "Acceptable use" },
  { key: "key", label: "LLM key" },
  { key: "repo", label: "Repo" },
  { key: "idea", label: "First idea" },
];

interface OnboardingWizardProps {
  onComplete: () => void;
}

export function OnboardingWizard({ onComplete }: OnboardingWizardProps): React.JSX.Element {
  const { orgId } = useAuth();
  const [step, setStep] = useState<WizardStep>("tos");
  const [stepInitialized, setStepInitialized] = useState(false);
  const [tosVersion, setTosVersion] = useState<string | null>(null);
  const { data: status } = useOnboardingStatus(orgId);

  // Resume mid-flow on refresh/re-login: the first time this org's onboarding status
  // loads, jump straight to whichever step isn't done yet. `orgId` alone can't signal
  // this — every session (including a fresh viewer auto-joined into the shared
  // default org) always has an orgId, so tos_accepted (false for that org, since it
  // predates T-206 and never went through org_service.create_org) is the real signal
  // that a NEW org still needs to be created.
  useEffect(() => {
    if (stepInitialized || !status) return;
    if (!status.tos_accepted) setStep("tos");
    else if (!status.has_provider_key) setStep("key");
    else if (!status.has_repo) setStep("repo");
    else setStep("idea");
    setStepInitialized(true);
  }, [status, stepInitialized]);

  const stepIndex = STEPS.findIndex((s) => s.key === step);

  return (
    <main className="mx-auto flex max-w-2xl flex-col gap-6 p-6">
      <div>
        <h1 className="text-xl font-bold text-gray-900">Get started</h1>
        <p className="mt-1 text-sm text-gray-500">
          A few quick steps and you'll have your first agent-built PR.
        </p>
      </div>

      <ol className="flex gap-4 text-xs text-gray-500">
        {STEPS.map((s, index) => (
          <li
            key={s.key}
            className={index <= stepIndex ? "font-semibold text-gray-900" : ""}
          >
            {index + 1}. {s.label}
          </li>
        ))}
      </ol>

      {step === "tos" && (
        <TosAcceptanceStep
          onAccept={(version) => {
            setTosVersion(version);
            setStep("org");
          }}
        />
      )}

      {step === "org" && tosVersion && (
        <CreateOrgStep tosVersion={tosVersion} onCreated={() => setStep("key")} />
      )}

      {step === "key" && (
        <div className="flex flex-col gap-4">
          <ByokSetupGuide provider="anthropic" />
          <ProviderKeysPage />
          <button
            type="button"
            onClick={() => setStep("repo")}
            disabled={!status?.has_provider_key}
            className="self-start rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Continue
          </button>
        </div>
      )}

      {step === "repo" && (
        <div className="flex flex-col gap-4">
          <RepoConnectPage />
          <button
            type="button"
            onClick={() => setStep("idea")}
            disabled={!status?.has_repo}
            className="self-start rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Continue
          </button>
        </div>
      )}

      {step === "idea" && <CreateFirstIdeaStep onCreated={onComplete} />}
    </main>
  );
}
