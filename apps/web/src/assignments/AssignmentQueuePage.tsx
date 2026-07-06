import { useTickets, useUtilisation } from "../api/queries";
import type { Ticket } from "../api/types";

function ReadyTaskRow({ task }: { task: Ticket }): React.JSX.Element {
  const dependsOn = Array.isArray(task.spec?.depends_on) ? (task.spec?.depends_on as string[]) : [];

  return (
    <li
      data-testid={`ready-task-${task.id}`}
      className="flex items-center justify-between rounded border border-gray-200 p-2 text-sm"
    >
      <div>
        <p className="font-medium text-gray-900">{task.title}</p>
        <p className="text-xs text-gray-400">
          budget ${(task.budget_usd ?? 0).toFixed(2)}
          {dependsOn.length > 0 && ` · depends on ${dependsOn.join(", ")}`}
        </p>
      </div>
      {task.assignee_agent && (
        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
          last tried: {task.assignee_agent}
        </span>
      )}
    </li>
  );
}

export function AssignmentQueuePage(): React.JSX.Element {
  const { data: ticketsData } = useTickets();
  const { data: utilisation } = useUtilisation();

  const readyTasks = (ticketsData?.items ?? []).filter(
    (t) => t.type === "task" && t.state === "ready",
  );

  return (
    <div className="flex h-full">
      <main className="flex-1 overflow-y-auto p-4">
        <h2 className="mb-2 text-sm font-semibold text-gray-700">
          Ready tasks awaiting assignment
        </h2>
        <ul className="flex flex-col gap-2">
          {readyTasks.map((task) => (
            <ReadyTaskRow key={task.id} task={task} />
          ))}
          {readyTasks.length === 0 && <li className="text-sm text-gray-400">None</li>}
        </ul>
      </main>

      <aside className="w-72 overflow-y-auto border-l border-gray-200 p-3">
        <h2 className="mb-2 text-sm font-semibold text-gray-700">Profile utilisation</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-gray-400">
              <th className="pb-1">Profile</th>
              <th className="pb-1">In progress</th>
              <th className="pb-1">Capacity</th>
            </tr>
          </thead>
          <tbody>
            {(utilisation?.items ?? []).map((row) => (
              <tr key={row.profile} data-testid={`utilisation-${row.profile}`}>
                <td className="py-1">{row.profile}</td>
                <td className="py-1">{row.in_progress_count}</td>
                <td className="py-1">{row.max_parallel}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {(utilisation?.items?.length ?? 0) === 0 && (
          <p className="text-sm text-gray-400">No profiles configured</p>
        )}
      </aside>
    </div>
  );
}
