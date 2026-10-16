"use client";

import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";

import { otherEvents } from "@/app/actions/events";
import { LinkButtons } from "@/components/evidence-controls";
import { relationLabel } from "@/lib/events";
import { suggestionUsed, type CandidateEvent, type ReportLink } from "@/lib/types";

const linkBtn =
  "inline-flex items-center gap-1.5 text-sm font-semibold text-brand hover:underline disabled:cursor-wait disabled:opacity-60";

/** On an item labelled "not this event": it may still be true about something else.
 * Find the event it belongs to, link it there, or create one from it. */
export function ElsewhereNote({
  eventId,
  kind,
  itemId,
  canCreate,
}: {
  eventId: string;
  kind: "signal" | "report";
  itemId: string;
  /** The item has a type and a place, so an event can be created from it. */
  canCreate: boolean;
}) {
  const [pending, startTransition] = useTransition();
  const [found, setFound] = useState<{ linked: ReportLink[]; candidates: CandidateEvent[] }>();
  const [error, setError] = useState<string>();

  function look() {
    startTransition(async () => {
      const result = await otherEvents(kind, itemId, eventId);
      if (result && "linked" in result) {
        setFound({ linked: result.linked, candidates: result.candidates });
        setError(undefined);
      } else setError(result?.message ?? "Could not look for other events.");
    });
  }

  const createHref = `/events/new?${kind === "signal" ? "from_signal" : "from_report"}=${itemId}`;
  return (
    <div
      className="mt-2 rounded-md bg-panel-2 px-2.5 py-2 text-sm"
      aria-busy={pending}
      data-testid="elsewhere"
    >
      {!found ? (
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="text-muted">
            Not this event. It may still be true about another one.
          </span>
          <button type="button" className={linkBtn} disabled={pending} onClick={look}>
            <Search size={14} aria-hidden="true" />
            {pending ? "Looking…" : "Find its event"}
          </button>
        </p>
      ) : (
        <div className="flex flex-col gap-2">
          {found.linked.length > 0 && (
            <p>
              <span className="text-muted">Also linked to: </span>
              {found.linked.map((l, i) => (
                <span key={l.evidence_id}>
                  {i > 0 && "; "}
                  <Link
                    href={`/events/${l.event.id}?tab=evidence`}
                    className="font-semibold hover:text-brand hover:underline"
                  >
                    {l.event.title}
                  </Link>
                  <span className="text-muted"> ({relationLabel(l.relation).toLowerCase()})</span>
                </span>
              ))}
            </p>
          )}
          {found.candidates.length === 0 ? (
            <p className="text-muted">No other event matches its place and time.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {found.candidates.slice(0, 3).map((c, i) => (
                <li key={c.event.id} className="rounded-md border border-line bg-panel p-2.5">
                  <Link
                    href={`/events/${c.event.id}`}
                    className="mb-1.5 block font-semibold hover:text-brand hover:underline"
                  >
                    {c.event.title}
                  </Link>
                  <LinkButtons
                    eventId={c.event.id}
                    signalId={kind === "signal" ? itemId : undefined}
                    reportId={kind === "report" ? itemId : undefined}
                    label={`Link to “${c.event.title}” as`}
                    suggestion={suggestionUsed(c, i)}
                    stance={c.stance}
                    onLinked={look}
                  />
                </li>
              ))}
            </ul>
          )}
          {canCreate && (
            <Link href={createHref} className={linkBtn}>
              <Plus size={14} aria-hidden="true" />
              Create an event from it
            </Link>
          )}
        </div>
      )}
      {error && (
        <p role="alert" className="mt-1 text-critical">
          {error}
        </p>
      )}
    </div>
  );
}
