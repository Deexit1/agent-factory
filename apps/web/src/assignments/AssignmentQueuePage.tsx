import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTickets, useUtilisation } from "../api/queries";
import type { Ticket } from "../api/types";

function ReadyTaskRow({ task }: { task: Ticket }): React.JSX.Element {
  const dependsOn = Array.isArray(task.spec?.depends_on) ? (task.spec?.depends_on as string[]) : [];

  return (
    <li
      data-testid={`ready-task-${task.id}`}
      className="flex items-center justify-between rounded-lg border p-2 text-sm"
    >
      <div>
        <p className="font-medium text-foreground">{task.title}</p>
        <p className="text-xs text-muted-foreground">
          budget ${(task.budget_usd ?? 0).toFixed(2)}
          {dependsOn.length > 0 && ` · depends on ${dependsOn.join(", ")}`}
        </p>
      </div>
      {task.assignee_agent && (
        <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800">
          last tried: {task.assignee_agent}
        </Badge>
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
        <h2 className="mb-2 text-sm font-semibold text-foreground">
          Ready tasks awaiting assignment
        </h2>
        <ul className="flex flex-col gap-2">
          {readyTasks.map((task) => (
            <ReadyTaskRow key={task.id} task={task} />
          ))}
          {readyTasks.length === 0 && <li className="text-sm text-muted-foreground">None</li>}
        </ul>
      </main>

      <aside className="w-72 overflow-y-auto border-l p-3">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Profile utilisation</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Profile</TableHead>
              <TableHead>In progress</TableHead>
              <TableHead>Capacity</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(utilisation?.items ?? []).map((row) => (
              <TableRow key={row.profile} data-testid={`utilisation-${row.profile}`}>
                <TableCell>{row.profile}</TableCell>
                <TableCell>{row.in_progress_count}</TableCell>
                <TableCell>{row.max_parallel}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {(utilisation?.items?.length ?? 0) === 0 && (
          <p className="mt-2 text-sm text-muted-foreground">No profiles configured</p>
        )}
      </aside>
    </div>
  );
}
