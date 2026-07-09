import { useState } from "react";

import { useApproveIntakeReview, useIntakeReviews, useRejectIntakeReview } from "../api/queries";
import type { IntakeReview } from "../api/types";

function ReviewRow({ review }: { review: IntakeReview }): React.JSX.Element {
  const [note, setNote] = useState("");
  const approve = useApproveIntakeReview();
  const reject = useRejectIntakeReview();

  return (
    <li
      data-testid={`intake-review-${review.id}`}
      className="flex flex-col gap-2 rounded border border-gray-200 p-3 text-sm"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-900">{review.title}</span>
        <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
          {review.ticket_type}
        </span>
      </div>
      <p className="text-xs text-gray-500">org {review.org_id} · submitted by {review.submitted_by}</p>
      {review.screening_reason && (
        <p className="text-xs text-amber-700">{review.screening_reason}</p>
      )}
      <input
        type="text"
        placeholder="Decision note (optional)"
        value={note}
        onChange={(event) => setNote(event.target.value)}
        aria-label={`Decision note for review ${review.id}`}
        className="rounded border border-gray-300 px-2 py-1 text-xs"
      />
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => void approve.mutateAsync({ reviewId: review.id, note })}
          disabled={approve.isPending || reject.isPending}
          className="rounded bg-green-700 px-3 py-1 text-xs font-medium text-white hover:bg-green-800 disabled:opacity-50"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={() => void reject.mutateAsync({ reviewId: review.id, note })}
          disabled={approve.isPending || reject.isPending}
          className="rounded bg-red-700 px-3 py-1 text-xs font-medium text-white hover:bg-red-800 disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </li>
  );
}

export function IntakeReviewPage(): React.JSX.Element {
  const { data } = useIntakeReviews("pending");
  const reviews = data?.items ?? [];

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">Intake review queue</h1>
      <p className="mt-1 text-sm text-gray-500">
        Borderline idea/task submissions that didn't clear automated screening —
        approve to create the ticket, or reject with a note.
      </p>
      <ul className="mt-4 flex flex-col gap-2">
        {reviews.map((review) => (
          <ReviewRow key={review.id} review={review} />
        ))}
        {reviews.length === 0 && <li className="text-sm text-gray-400">Nothing pending</li>}
      </ul>
    </main>
  );
}
