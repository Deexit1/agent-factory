import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  useAnswerPlanningQuestions,
  useApproveTicket,
  useDescendants,
  useTickets,
  useTransitionTicket,
  useUpdateTask,
} from "../api/queries";
import type { Ticket } from "../api/types";
import { useAuth } from "../auth/AuthContext";

function TaskRow({
  task,
  ideaId,
  editable,
}: {
  task: Ticket;
  ideaId: string;
  editable: boolean;
}): React.JSX.Element {
  const updateTask = useUpdateTask();
  const [title, setTitle] = useState(task.title);
  const [budgetUsd, setBudgetUsd] = useState(task.budget_usd ?? 0);
  const estimateDays =
    typeof task.spec?.estimate_days === "number" ? task.spec.estimate_days : null;
  const dirty = title !== task.title || budgetUsd !== (task.budget_usd ?? 0);

  return (
    <li
      data-testid={`task-${task.id}`}
      className="flex flex-col gap-2 rounded-lg border p-2 text-sm"
    >
      <div className="flex items-center gap-2">
        <Input
          className="flex-1"
          value={title}
          disabled={!editable}
          aria-label={`Title for ${task.id}`}
          onChange={(event) => setTitle(event.target.value)}
        />
        <Input
          type="number"
          className="w-24"
          value={budgetUsd}
          disabled={!editable}
          aria-label={`Budget for ${task.id}`}
          onChange={(event) => setBudgetUsd(Number(event.target.value))}
        />
        {editable && (
          <Button
            size="sm"
            disabled={!dirty || updateTask.isPending}
            onClick={() =>
              updateTask.mutate({ ticketId: task.id, ideaId, title, budget_usd: budgetUsd })
            }
          >
            Save
          </Button>
        )}
      </div>
      {estimateDays !== null && estimateDays > 1 && (
        <Badge variant="outline" className="w-fit border-amber-300 bg-amber-50 text-amber-800">
          ⚠ estimated {estimateDays} days — consider splitting
        </Badge>
      )}
    </li>
  );
}

export function PlanningReviewPage(): React.JSX.Element {
  const { role } = useAuth();
  const canApprove = role === "approver" || role === "owner";

  const { data: ticketsData } = useTickets();
  const [selectedIdeaId, setSelectedIdeaId] = useState<string | null>(null);
  const { data: descendants } = useDescendants(selectedIdeaId);
  const approve = useApproveTicket();
  const transition = useTransitionTicket();
  const answerQuestions = useAnswerPlanningQuestions();
  const [answerText, setAnswerText] = useState("");

  const ideas = (ticketsData?.items ?? []).filter(
    (t) => t.type === "idea" && (t.state === "planning" || t.state === "escalated"),
  );
  const selectedIdea = ideas.find((i) => i.id === selectedIdeaId) ?? null;

  const epics = (descendants?.items ?? []).filter((t) => t.type === "epic");
  const tasksByEpic = new Map<string, Ticket[]>();
  for (const t of descendants?.items ?? []) {
    if (t.type !== "task" || !t.parent_id) continue;
    const list = tasksByEpic.get(t.parent_id) ?? [];
    list.push(t);
    tasksByEpic.set(t.parent_id, list);
  }

  return (
    <div className="flex h-full">
      <aside className="w-64 overflow-y-auto border-r p-3">
        <h2 className="mb-2 text-sm font-semibold text-foreground">Ideas in planning</h2>
        <ul className="flex flex-col gap-1">
          {ideas.map((idea) => (
            <li key={idea.id}>
              <button
                type="button"
                data-testid={`idea-${idea.id}`}
                onClick={() => setSelectedIdeaId(idea.id)}
                className={cn(
                  "w-full rounded-md px-2 py-1 text-left text-sm",
                  selectedIdeaId === idea.id
                    ? "bg-accent font-semibold text-accent-foreground"
                    : "hover:bg-accent/50",
                )}
              >
                {idea.title}
                <span className="ml-1 text-xs text-muted-foreground">({idea.state})</span>
              </button>
            </li>
          ))}
          {ideas.length === 0 && <li className="text-sm text-muted-foreground">None</li>}
        </ul>
      </aside>

      <main className="flex-1 overflow-y-auto p-4">
        {!selectedIdea && <p className="text-muted-foreground">Select an idea to review its plan.</p>}

        {selectedIdea && selectedIdea.state === "escalated" && (
          <div className="max-w-lg rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold text-foreground">
              The Planner needs more information
            </h3>
            <Textarea
              className="mb-2"
              placeholder="Answer the Planner's questions (see event feed)"
              value={answerText}
              onChange={(event) => setAnswerText(event.target.value)}
              aria-label="Answer for the planner"
            />
            <Button
              disabled={!canApprove || !answerText}
              onClick={() =>
                answerQuestions.mutate({ ticketId: selectedIdea.id, answers: answerText })
              }
            >
              Submit answers
            </Button>
          </div>
        )}

        {selectedIdea && selectedIdea.state === "planning" && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">{selectedIdea.title}</h2>
              <p className="text-sm text-muted-foreground">
                Idea budget: ${(selectedIdea.budget_usd ?? 0).toFixed(2)}
              </p>
            </div>

            {epics.map((epic) => (
              <div key={epic.id} className="rounded-lg border p-3">
                <h3 className="mb-2 text-sm font-semibold text-foreground">{epic.title}</h3>
                <ul className="flex flex-col gap-2">
                  {(tasksByEpic.get(epic.id) ?? []).map((task) => (
                    <TaskRow
                      key={task.id}
                      task={task}
                      ideaId={selectedIdea.id}
                      editable={canApprove}
                    />
                  ))}
                </ul>
              </div>
            ))}

            {canApprove && (
              <Button
                className="w-fit"
                onClick={() => {
                  approve.mutate(
                    { ticketId: selectedIdea.id, gate: "budget", decision: "approved" },
                    {
                      onSuccess: () =>
                        transition.mutate({ ticketId: selectedIdea.id, toState: "ready" }),
                    },
                  );
                }}
              >
                Approve & start
              </Button>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
