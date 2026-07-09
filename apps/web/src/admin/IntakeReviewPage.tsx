import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useApproveIntakeReview, useIntakeReviews, useRejectIntakeReview } from "../api/queries";
import type { IntakeReview } from "../api/types";

function ReviewRow({ review }: { review: IntakeReview }): React.JSX.Element {
  const [note, setNote] = useState("");
  const approve = useApproveIntakeReview();
  const reject = useRejectIntakeReview();

  return (
    <li
      data-testid={`intake-review-${review.id}`}
      className="flex flex-col gap-2 rounded-lg border p-3 text-sm"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-foreground">{review.title}</span>
        <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-800">
          {review.ticket_type}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">
        org {review.org_id} · submitted by {review.submitted_by}
      </p>
      {review.screening_reason && (
        <p className="text-xs text-amber-700">{review.screening_reason}</p>
      )}
      <Input
        type="text"
        placeholder="Decision note (optional)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        aria-label={`Decision note for review ${review.id}`}
      />
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={() => void approve.mutateAsync({ reviewId: review.id, note })}
          disabled={approve.isPending || reject.isPending}
        >
          Approve
        </Button>
        <Button
          size="sm"
          variant="destructive"
          onClick={() => void reject.mutateAsync({ reviewId: review.id, note })}
          disabled={approve.isPending || reject.isPending}
        >
          Reject
        </Button>
      </div>
    </li>
  );
}

export function IntakeReviewPage(): React.JSX.Element {
  const { data } = useIntakeReviews("pending");
  const reviews = data?.items ?? [];

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-foreground">Intake review queue</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Borderline idea/task submissions that didn't clear automated screening —
        approve to create the ticket, or reject with a note.
      </p>
      <ul className="mt-4 flex flex-col gap-2">
        {reviews.map((review) => (
          <ReviewRow key={review.id} review={review} />
        ))}
        {reviews.length === 0 && <li className="text-sm text-muted-foreground">Nothing pending</li>}
      </ul>
    </main>
  );
}
