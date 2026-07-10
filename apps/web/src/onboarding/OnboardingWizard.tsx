import { useEffect, useState } from "react";

import { CheckIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { ProviderKeysPage } from "../admin/ProviderKeysPage";
import { RepoConnectPage } from "../admin/RepoConnectPage";
import { useOnboardingStatus } from "../api/queries";
import { useAuth } from "../auth/AuthContext";
import { ByokSetupGuide } from "../docs/ByokSetupGuide";
import { CreateOrgStep } from "./CreateOrgStep";
import { TosAcceptanceStep } from "./TosAcceptanceStep";

type WizardStep = "tos" | "org" | "key" | "repo";

const STEPS: { key: WizardStep; label: string }[] = [
  { key: "tos", label: "Acceptable use" },
  { key: "key", label: "LLM key" },
  { key: "repo", label: "Repo" },
];

// "org" isn't in the visible stepper (it's a sub-step of "Acceptable use" — collecting
// the org name right after ToS accept) but should still visually count step 1 as
// active/complete rather than showing no step highlighted while it's active.
function stepperIndex(step: WizardStep): number {
  return step === "org" ? 0 : STEPS.findIndex((s) => s.key === step);
}

// Board access is gated on exactly these three (OnboardingGate) — once `has_repo` flips
// true, the gate swaps this wizard out for the real app on the next render, so there is
// deliberately no step after "repo" to get cut off mid-flow.
export function OnboardingWizard(): React.JSX.Element {
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
    else setStep("repo");
    setStepInitialized(true);
  }, [status, stepInitialized]);

  const stepIndex = stepperIndex(step);

  return (
    <main className="flex min-h-screen items-start justify-center bg-muted/30 p-6">
      <div className="mt-12 flex w-full max-w-2xl flex-col gap-6">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Get started</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            A few quick steps and you'll have access to the board.
          </p>
        </div>

        <ol className="flex items-center gap-2">
          {STEPS.map((s, index) => {
            const complete = index < stepIndex;
            const active = index === stepIndex;
            return (
              <li key={s.key} className="flex flex-1 items-center gap-2 last:flex-none">
                <div className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold",
                      complete && "bg-primary text-primary-foreground",
                      active && !complete && "bg-primary text-primary-foreground",
                      !complete && !active && "bg-muted text-muted-foreground",
                    )}
                  >
                    {complete ? <CheckIcon className="size-3.5" /> : index + 1}
                  </span>
                  <span
                    className={cn(
                      "text-xs whitespace-nowrap",
                      active || complete ? "font-semibold text-foreground" : "text-muted-foreground",
                    )}
                  >
                    {s.label}
                  </span>
                </div>
                {index < STEPS.length - 1 && (
                  <div className={cn("h-px flex-1", complete ? "bg-primary" : "bg-border")} />
                )}
              </li>
            );
          })}
        </ol>

        <Card>
          <CardHeader className="sr-only">
            <span>{STEPS[stepIndex >= 0 ? stepIndex : 0]?.label}</span>
          </CardHeader>
          <CardContent className="pt-4">
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
                <Button onClick={() => setStep("repo")} disabled={!status?.has_provider_key} className="self-start">
                  Continue
                </Button>
              </div>
            )}

            {step === "repo" && (
              <div className="flex flex-col gap-4">
                <RepoConnectPage />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
