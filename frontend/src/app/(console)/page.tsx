import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import {
  REPORT_REVIEWERS,
  REPORT_SUBMITTERS,
  type EventPage,
  type FieldReportPage,
} from "@/lib/types";

import { Situation } from "./situation";

export const metadata = { title: "Situation map" };

/** Field reports on the map: the last two days. */
function reportWindowStart(): string {
  return new Date(Date.now() - 48 * 3600 * 1000).toISOString();
}

export default async function SituationPage({
  searchParams,
}: {
  searchParams: Promise<{ denied?: string }>;
}) {
  const [user, { denied }] = await Promise.all([verifySession(), searchParams]);
  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const since = reportWindowStart();

  const [events, reports] = await Promise.all([
    api<EventPage>("/events?status=active&status=monitoring&limit=200"),
    reviewer
      ? api<FieldReportPage>(`/field-reports?limit=200&since=${encodeURIComponent(since)}`)
      : Promise.resolve(null),
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
        canSubmit={REPORT_SUBMITTERS.includes(user.role)}
        canSeeReports={reviewer}
      />
    </main>
  );
}
