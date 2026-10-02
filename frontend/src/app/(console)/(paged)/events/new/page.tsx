import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { dhakaNowLocalInput, isUuid } from "@/lib/format";
import { REPORT_REVIEWERS, type FieldReport } from "@/lib/types";

import { EventForm, type EventDraft } from "./event-form";

export const metadata = { title: "New event" };

export default async function NewEventPage({
  searchParams,
}: {
  searchParams: Promise<{ from_report?: string }>;
}) {
  await requireRole(...REPORT_REVIEWERS);
  const { from_report } = await searchParams;

  let source: FieldReport | null = null;
  if (from_report && isUuid(from_report)) {
    try {
      source = await api<FieldReport>(`/field-reports/${from_report}`);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }

  // Starting from a report: its type, place, location and time are the best first guess.
  const draft: EventDraft = source
    ? {
        title: source.event_type
          ? `${eventTypeLabel(source.event_type)}${source.place_name ? ` at ${source.place_name}` : ""}`
          : (source.place_name ?? ""),
        event_type: source.event_type ?? "",
        place_name: source.place_name ?? "",
        latitude: String(source.latitude),
        longitude: String(source.longitude),
        started_at: dhakaNowLocalInput(new Date(source.observed_at)),
        report: { id: source.id, text: source.text, reporter: source.reporter.full_name },
      }
    : {
        title: "",
        event_type: "",
        place_name: "",
        latitude: "",
        longitude: "",
        started_at: dhakaNowLocalInput(),
        report: null,
      };

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h1 className="display mb-3 text-4xl">New event</h1>
        <p className="max-w-2xl text-steel">
          One record per real situation. Reports are attached to it as evidence, so before creating
          one, check Events for an open event at the same place.
        </p>
      </section>
      <EventForm draft={draft} />
    </div>
  );
}
