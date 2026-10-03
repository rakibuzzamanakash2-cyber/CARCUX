"use client";

import { Ban, CheckCircle2, RotateCcw } from "lucide-react";
import { useState, useTransition } from "react";

import { reviewReport } from "@/app/actions/review";
import { reviewSignal } from "@/app/actions/signals";
import type { ActionState, ReportStatus, SignalStatus } from "@/lib/types";

type Triage = "open" | "reviewed" | "dismissed";

/** Triage buttons for one report or signal: mark reviewed, dismiss with a reason, or reopen. */
export function ReviewControls({
  reportId,
  signalId,
  status,
  compact = false,
}: {
  reportId?: string;
  signalId?: string;
  status: ReportStatus | SignalStatus;
  compact?: boolean;
}) {
  const noun = signalId ? "signal" : "report";
  const id = signalId ?? reportId ?? "";
  const current: Triage = status === "submitted" || status === "new" ? "open" : status;
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState<ActionState>();
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState("");

  function decide(next: Triage, note?: string) {
    startTransition(async () => {
      const result = signalId
        ? await reviewSignal(signalId, next === "open" ? "new" : next, note)
        : await reviewReport(id, next === "open" ? "submitted" : next, note);
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
        {current !== "reviewed" && (
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
        {current !== "dismissed" && !dismissing && (
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
        {current !== "open" && (
          <button
            type="button"
            disabled={pending}
            onClick={() => decide("open")}
            className={`${btn} border border-line bg-panel text-ink hover:border-muted`}
          >
            <RotateCcw size={16} aria-hidden="true" />
            {compact ? "Reopen" : signalId ? "Mark as new" : "Put back in the queue"}
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
          <label htmlFor={`reason-${id}`} className="text-sm font-semibold">
            Why is this {noun} not usable?
          </label>
          <input
            id={`reason-${id}`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            required
            maxLength={1000}
            placeholder={
              signalId
                ? "e.g. Old story; not about Bangladesh; placed in the wrong district"
                : "e.g. Duplicate of an earlier report; photo is from another place"
            }
            className="h-10 rounded-lg border border-line bg-panel px-3 text-ink focus:border-red focus:outline-none"
          />
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={pending || !reason.trim()}
              className={`${btn} bg-red text-white hover:bg-red-strong`}
            >
              Dismiss {noun}
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
