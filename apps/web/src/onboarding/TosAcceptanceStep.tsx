import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useTos } from "../api/queries";

interface TosAcceptanceStepProps {
  onAccept: (tosVersion: string) => void;
}

export function TosAcceptanceStep({ onAccept }: TosAcceptanceStepProps): React.JSX.Element {
  const { data: tos, isLoading } = useTos();
  const [checked, setChecked] = useState(false);

  if (isLoading || !tos) {
    return <Skeleton className="h-40 w-full" />;
  }

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-foreground">Acceptable use policy</h2>
      <pre className="max-h-64 overflow-y-auto rounded-md border bg-muted/50 p-3 text-xs whitespace-pre-wrap text-muted-foreground">
        {tos.policy_text}
      </pre>
      <Label className="items-start gap-2 font-normal">
        <Checkbox
          checked={checked}
          onCheckedChange={(value) => setChecked(value === true)}
          className="mt-0.5"
        />
        <span>I have read and agree to the acceptable use policy (version {tos.version}).</span>
      </Label>
      <Button onClick={() => onAccept(tos.version)} disabled={!checked} className="self-start">
        Continue
      </Button>
    </div>
  );
}
