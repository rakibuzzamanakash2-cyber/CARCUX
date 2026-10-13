"use client";

import { Ban, CheckCircle2, RotateCcw } from "lucide-react";
import { useState, useTransition } from "react";

import { reviewReport } from "@/app/actions/review";
import type { ActionState, ReportStatus } from "@/lib/types";

/** Triage buttons for one report: mark reviewed, dismiss with a reason, or reopen. */
export function ReviewControls({
  reportId,
  status,
  compact = false,
}: {
  reportId: string;
  status: ReportStatus;
  compact?: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");

  function decide(next: ReportStatus, note?: string) {
    startTransition(async () => {
      const result = await reviewReport(reportId, next, note);
      setState(result);
      if (result?.ok) {
        setDismissing(false);
        setReason("");
      }
    });
  }

  const btn =
    "inline-flex h-9 items-center gap-1.5 rounded-lg px-3 text-sm font-semibold shadow-sm transition-colors disabled:cursor-wait disabled:opacity-60";

  return (
    <div className="flex flex-col gap-2" aria-busy={pending}>
      <div className="flex flex-wrap gap-2">
        {status !== "reviewed" && (
          <button
            type="button"
            disabled={pending}
            onClick={() => decide("reviewed")}
            className={`${btn} bg-brand text-white hover:bg-brand-strong`}
          >
            <CheckCircle2 size={16} aria-hidden="true" />
            Mark reviewed
          </button>
        )}
        {status !== "dismissed" && !dismissing && (
          <button
            type="button"
            disabled={pending}
            onClick={() => setDismissing(true)}
            className={`${btn} border border-red bg-panel text-red hover:bg-red-soft`}
          >
            <Ban size={16} aria-hidden="true" />
            Dismiss
          </button>
        )}
        {status !== "submitted" && (
          <button
            type="button"
            disabled={pending}
            onClick={() => decide("submitted")}
            className={`${btn} border border-line bg-panel text-ink hover:border-muted`}
          >
            <RotateCcw size={16} aria-hidden="true" />
            {compact ? "Reopen" : "Put back in the queue"}
          </button>
        )}
      </div>
      {dismissing && (
        <form
          className="flex flex-col gap-2 rounded-lg border border-red/30 bg-red-soft/50 p-3"
          onSubmit={(e) => {
            e.preventDefault();
            decide("dismissed", reason);
          }}
        >
          <label htmlFor={`reason-${reportId}`} className="text-sm font-semibold">
            Why is this report not usable?
          </label>
          <input
            id={`reason-${reportId}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            maxLength={1000}
            placeholder="e.g. Duplicate of an earlier report; photo is from another place"
            className="h-10 rounded-lg border border-line bg-panel px-3 text-ink focus:border-red focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={pending || !reason.trim()}
              className={`${btn} bg-red text-white hover:bg-red-strong`}
            >
              Dismiss report
            </button>
            <button
              type="button"
              onClick={() => setDismissing(false)}
              className={`${btn} border border-line bg-panel text-ink`}
            >
              Cancel
            </button>
          </div>
        </form>
      )}
      {state && (
        <p
          role={state.ok ? "status" : "alert"}
          className={`text-sm ${state.ok ? "text-brand" : "text-critical"}`}
        >
          {state.message}
        </p>
      )}
    </div>
  );
}
