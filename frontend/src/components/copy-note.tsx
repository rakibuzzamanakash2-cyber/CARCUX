"use client";

import { Copy } from "lucide-react";
import { useId, useState, useTransition } from "react";

import { clearCopy, decideCopy } from "@/app/actions/events";
import type { ActionState, CopyInfo } from "@/lib/types";

const KIND: Record<CopyInfo["kind"], string> = {
  same_media: "uses the same photo as",
  verbatim_copy: "repeats word for word",
  cites: "passes on",
  rewrite: "rewrites",
  repost: "reposts",
};

const linkBtn =
  "text-sm font-semibold text-brand hover:underline disabled:cursor-wait disabled:opacity-60";

/** Whether a linked item repeats another source's, and the analyst's say on it. */
export function CopyNote({
  eventId,
  evidenceId,
  copy,
  others,
}: {
  eventId: string;
  evidenceId: string;
  copy: CopyInfo | null;
  /** The event's other linked items, for naming an origin by hand. */
  others: { id: string; label: string }[];
}) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const [choosing, setChoosing] = useState(false);
  const [origin, setOrigin] = useState(others[0]?.id ?? "");
  const id = useId();
  const run = (action: () => Promise<ActionState>) =>
    startTransition(async () => {
      setResult(await action());
      setChoosing(false);
    });

  const counted = copy && copy.status !== "rejected";
  return (
    <div className="mt-2 text-sm" aria-busy={pending}>
      {copy && (
        <div
          className={`flex flex-wrap items-start gap-x-3 gap-y-1 rounded-md px-2.5 py-1.5 ${
            counted ? "bg-medium-soft" : "bg-panel-2"
          }`}
        >
          <Copy size={15} className="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
          <p className="min-w-0 flex-1">
            {copy.status === "rejected" ? (
              <>
                <span className="font-semibold">Not a copy</span>
                <span className="text-muted">
                  {" "}
                  (looked like it {KIND[copy.kind]} {copy.origin_source}; {copy.decided_by} said
                  no). Counted as its own source.
                </span>
              </>
            ) : (
              <>
                <span className="font-semibold">
                  {copy.status === "confirmed" ? "Copy" : "Looks like a copy"}:
                </span>{" "}
                it {KIND[copy.kind]} <span className="font-semibold">{copy.origin_source}</span>
                <span className="text-muted">
                  {" "}
                  · {copy.reasons.join(", ")}
                  {copy.status === "confirmed" && copy.decided_by
                    ? ` · confirmed by ${copy.decided_by}`
                    : ""}
                  . Counted once, through that source.
                </span>
              </>
            )}
          </p>
          <span className="flex gap-3">
            {copy.status === "detected" ? (
              <>
                <button
                  type="button"
                  className={linkBtn}
                  disabled={pending}
                  onClick={() =>
                    run(() => decideCopy(eventId, evidenceId, copy.origin_evidence_id))
                  }
                >
                  Confirm
                </button>
                <button
                  type="button"
                  className={linkBtn}
                  disabled={pending}
                  onClick={() => run(() => decideCopy(eventId, evidenceId, null))}
                >
                  Not a copy
                </button>
              </>
            ) : (
              <button
                type="button"
                className={linkBtn}
                disabled={pending}
                onClick={() => run(() => clearCopy(eventId, evidenceId))}
              >
                Undo
              </button>
            )}
          </span>
        </div>
      )}

      {!copy && others.length > 0 && !choosing && (
        <button type="button" className={linkBtn} onClick={() => setChoosing(true)}>
          Mark as a copy of another item…
        </button>
      )}
      {choosing && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (origin) run(() => decideCopy(eventId, evidenceId, origin));
          }}
        >
          <label htmlFor={`${id}-origin`} className="flex min-w-0 flex-col gap-1">
            <span className="text-muted">It repeats</span>
            <select
              id={`${id}-origin`}
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              className="h-9 max-w-full rounded-md border border-line bg-panel px-2"
            >
              {others.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="submit"
            disabled={pending || !origin}
            className="h-9 rounded-md bg-brand px-3 font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
          >
            Save
          </button>
          <button
            type="button"
            className="h-9 px-2 text-muted hover:text-ink"
            onClick={() => setChoosing(false)}
          >
            Cancel
          </button>
        </form>
      )}
      {result && !result.ok && (
        <p role="alert" className="mt-1 text-critical">
          {result.message}
        </p>
      )}
    </div>
  );
}
