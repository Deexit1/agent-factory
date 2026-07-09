import { useState } from "react";

import { useTos } from "../api/queries";

interface TosAcceptanceStepProps {
  onAccept: (tosVersion: string) => void;
}

export function TosAcceptanceStep({ onAccept }: TosAcceptanceStepProps): React.JSX.Element {
  const { data: tos, isLoading } = useTos();
  const [checked, setChecked] = useState(false);

  if (isLoading || !tos) {
    return <p className="text-sm text-gray-500">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-gray-900">Acceptable use policy</h2>
      <pre className="max-h-64 overflow-y-auto whitespace-pre-wrap rounded border border-gray-200 bg-gray-50 p-3 text-xs text-gray-700">
        {tos.policy_text}
      </pre>
      <label className="flex items-center gap-2 text-sm text-gray-700">
        <input
          type="checkbox"
          checked={checked}
          onChange={(event) => setChecked(event.target.checked)}
        />
        I have read and agree to the acceptable use policy (version {tos.version}).
      </label>
      <button
        type="button"
        onClick={() => onAccept(tos.version)}
        disabled={!checked}
        className="self-start rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
      >
        Continue
      </button>
    </div>
  );
}
