import { Radar } from "lucide-react";
import { PageBand, PageBody, Panel } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { dhakaNowLocalInput, isUuid } from "@/lib/format";
import { REPORT_REVIEWERS, type FieldReport, type Signal } from "@/lib/types";

import { EventForm, type EventDraft } from "./event-form";

export const metadata = { title: "New event" };

export default async function NewEventPage({
  searchParams,
}: {
  searchParams: Promise<{ from_report?: string; from_signal?: string }>;
}) {
  await requireRole(...REPORT_REVIEWERS);
  const { from_report, from_signal } = await searchParams;

  let source: FieldReport | null = null;
  if (from_report && isUuid(from_report)) {
    try {
      source = await api<FieldReport>(`/field-reports/${from_report}`);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }

  let signal: Signal | null = null;
  if (!source && from_signal && isUuid(from_signal)) {
    try {
      signal = await api<Signal>(`/signals/${from_signal}`);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }

  // Starting from a report or a signal: its type, place, location and time are the best
  // first guess.
  const draft: EventDraft = signal
    ? {
        title: signal.event_type
          ? `${eventTypeLabel(signal.event_type)}${signal.place_name ? ` in ${signal.place_name}` : ""}`
          : signal.title.slice(0, 160),
        event_type: signal.event_type ?? "",
        place_name: signal.place_name ?? "",
        latitude: signal.latitude !== null ? String(signal.latitude) : "",
        longitude: signal.longitude !== null ? String(signal.longitude) : "",
        started_at: dhakaNowLocalInput(new Date(signal.valid_from ?? signal.published_at)),
        report: null,
        signal: {
          id: signal.id,
          title: signal.title,
          source: signal.source.name,
        },
      }
    : source
      ? {
          title: source.event_type
            ? `${eventTypeLabel(source.event_type)}${source.place_name ? ` at ${source.place_name}` : ""}`
            : (source.place_name ?? ""),
          event_type: source.event_type ?? "",
          place_name: source.place_name ?? "",
          latitude: String(source.latitude),
          longitude: String(source.longitude),
          started_at: dhakaNowLocalInput(new Date(source.observed_at)),
          report: {
            id: source.id,
            text: source.text,
            reporter: source.reporter.full_name,
          },
          signal: null,
        }
      : {
          title: "",
          event_type: "",
          place_name: "",
          latitude: "",
          longitude: "",
          started_at: dhakaNowLocalInput(),
          report: null,
          signal: null,
        };

  return (
    <>
      <PageBand
        scene="sundarbans"
        icon={Radar}
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
