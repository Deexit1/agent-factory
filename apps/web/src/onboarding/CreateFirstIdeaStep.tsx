import { useState } from "react";

import { useCreateTicket } from "../api/queries";
import { isIntakeQueuedResult } from "../api/types";
import { useAuth } from "../auth/AuthContext";

interface CreateFirstIdeaStepProps {
  onCreated: () => void;
}

export function CreateFirstIdeaStep({ onCreated }: CreateFirstIdeaStepProps): React.JSX.Element {
  const { actor } = useAuth();
  const createTicket = useCreateTicket();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("100");
  const [error, setError] = useState<string | null>(null);
  const [queuedMessage, setQueuedMessage] = useState<string | null>(null);

  const handleCreate = async (): Promise<void> => {
    setError(null);
    setQueuedMessage(null);
    try {
      const result = await createTicket.mutateAsync({
        type: "idea",
        title,
        spec: description ? { description } : null,
        acceptance_criteria: [],
        budget_usd: Number(budget),
        created_by: actor ?? "human:unknown",
      });
      if (isIntakeQueuedResult(result)) {
        setQueuedMessage(
          "Thanks — this idea needs a quick platform-staff review before it starts. " +
            "You'll see it on your board once approved.",
        );
        return;
      }
      onCreated();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Could not create this idea.";
      setError(message);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-gray-900">Create your first idea</h2>
      <p className="text-sm text-gray-500">
        Describe what you want built. A budget cap keeps spend bounded — agents stop and
        escalate if they'd exceed it.
      </p>
      <input
        type="text"
        placeholder="Title"
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        aria-label="Idea title"
        className="rounded border border-gray-300 px-3 py-2 text-sm"
      />
      <textarea
        placeholder="What should this idea accomplish?"
        value={description}
        onChange={(event) => setDescription(event.target.value)}
        aria-label="Idea description"
        rows={4}
        className="rounded border border-gray-300 px-3 py-2 text-sm"
      />
      <label className="flex items-center gap-2 text-sm text-gray-700">
        Budget (USD)
        <input
          type="number"
          min={1}
          value={budget}
          onChange={(event) => setBudget(event.target.value)}
          aria-label="Budget in USD"
          className="w-28 rounded border border-gray-300 px-2 py-1 text-sm"
        />
      </label>
      <button
        type="button"
        onClick={() => void handleCreate()}
        disabled={!title || !budget || createTicket.isPending}
        className="self-start rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
      >
        Create idea
      </button>
      {queuedMessage && <p className="text-xs text-amber-700">{queuedMessage}</p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
