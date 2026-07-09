const CHECKPOINTS: { title: string; description: string }[] = [
  {
    title: "Idea approval",
    description:
      "You set a budget when you create an idea — that's the human-approved go/no-go gate " +
      "before any planning work starts.",
  },
  {
    title: "Plan review",
    description:
      "The Planner breaks your idea into tasks. If anything's under-specified it asks " +
      "questions instead of guessing — you answer, and it re-plans.",
  },
  {
    title: "PR review",
    description:
      "Before a task's code reaches QA, a Review agent (or you) checks the diff for scope " +
      "and quality. A blocked PR bounces back to the dev agent with feedback.",
  },
  {
    title: "Merge queue",
    description:
      "Green CI alone never merges anything — a real rebase-and-retest against your " +
      "target branch has to succeed first.",
  },
  {
    title: "Escalation",
    description:
      "If a task bounces 3 times or runs out of budget, it escalates to you instead of " +
      "looping forever.",
  },
];

export function CheckpointExplainerPage(): React.JSX.Element {
  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">How work moves through the board</h1>
      <p className="mt-1 text-sm text-gray-500">
        Every ticket passes through a handful of human checkpoints on its way to done —
        here's what each one means.
      </p>
      <ol className="mt-4 flex flex-col gap-3">
        {CHECKPOINTS.map((checkpoint, index) => (
          <li key={checkpoint.title} className="rounded border border-gray-200 p-3 text-sm">
            <span className="font-semibold text-gray-900">
              {index + 1}. {checkpoint.title}
            </span>
            <p className="mt-1 text-gray-600">{checkpoint.description}</p>
          </li>
        ))}
      </ol>
    </main>
  );
}
