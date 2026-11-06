import { api } from "@/lib/api";
import { verifyStaff } from "@/lib/dal";
import { mapWindowStart, parseMapWindow } from "@/lib/map-window";
import {
  REPORT_REVIEWERS,
  REPORT_SUBMITTERS,
  type EventPage,
  type FieldReportPage,
  type SignalPage,
} from "@/lib/types";

import { Situation } from "./situation";

export const metadata = { title: "Situation map" };

export default async function SituationPage({
  searchParams,
}: {
  searchParams: Promise<{ denied?: string; window?: string }>;
}) {
  const [user, params] = await Promise.all([verifyStaff(), searchParams]);
  const { denied } = params;
  const timeWindow = parseMapWindow(params.window);
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const since = mapWindowStart(timeWindow);

  const [events, reports, signals] = await Promise.all([
    api<EventPage>("/events?status=active&status=monitoring&limit=200"),
    reviewer
      ? api<FieldReportPage>(`/field-reports?limit=200&since=${encodeURIComponent(since)}`)
      : Promise.resolve(null),
    api<SignalPage>(
      `/signals?located=true&status=new&status=reviewed&limit=500&since=${encodeURIComponent(since)}`,
    ),
  ]);

  return (
    <main className="relative h-full">
      {denied && (
        <p
          role="alert"
          className="absolute top-3 left-1/2 z-[600] -translate-x-1/2 rounded-md border border-critical bg-critical-soft px-4 py-2 text-sm"
        >
          That page needs a different role. Ask an admin if you need access.
        </p>
      )}
      <Situation
        events={events.items}
        reports={reports?.items ?? []}
        signals={signals.items}
        canSubmit={REPORT_SUBMITTERS.includes(user.role)}
        canSeeReports={reviewer}
        timeWindow={timeWindow}
        loadedAt={new Date().toISOString()}
      />
    </main>
  );
}
