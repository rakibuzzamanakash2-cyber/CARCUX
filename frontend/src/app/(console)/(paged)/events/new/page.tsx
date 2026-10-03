import { PageBand, PageBody, Panel } from "@/components/page-header";
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
    <>
      <PageBand
        back={{ href: "/events", label: "All events" }}
        title="New event"
        description="One record per real situation. Before creating one, check the map for an open event at the same place."
      />
      <PageBody>
        <div className="flex max-w-3xl flex-col gap-6">
          <Panel>
            <EventForm draft={draft} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
