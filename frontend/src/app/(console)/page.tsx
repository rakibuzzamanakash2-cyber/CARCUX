import Link from "next/link";

import { AssessmentText, EvidenceSummary, PriorityBadge } from "@/components/event-badges";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka } from "@/lib/format";
import type { CarcuxEvent, EventPage, Health, Priority } from "@/lib/types";

export const metadata = { title: "Overview" };

// Where each part of CARCUX stands. Update as PRs land.
const BUILD = [
  {
    name: "Accounts, roles and audit log",
    state: "live",
    note: "Sign-in, four roles, instant revocation, append-only audit trail.",
  },
  {
    name: "Dataset schema and validator",
    state: "live",
    note: "CARCUX-BD v1: events, observations, relations, dependences.",
  },
  {
    name: "Field reports",
    state: "live",
    note: "Phone-friendly submission with GPS and photos; tamper-evident fingerprint; integrity flags for reviewers.",
  },
  {
    name: "Events and evidence",
    state: "live",
    note: "Event records with supporting and contradicting reports, assessment, history, and suggested matches by place and time.",
  },
  { name: "Situation map", state: "next", note: "Events on a map with status and priority." },
  {
    name: "Correlation and fusion engine",
    state: "later",
    note: "The research core: same-event grouping, source independence, calibrated assessment.",
  },
] as const;

const STATE_STYLE = {
  live: { label: "Live", cls: "text-ok" },
  next: { label: "Next", cls: "text-amber" },
  later: { label: "Later", cls: "text-steel" },
} as const;

const PRIORITY_RANK: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3 };

/** Open events, most urgent first: priority, then most recent. */
async function openEvents(): Promise<CarcuxEvent[] | null> {
  try {
    const page = await api<EventPage>("/events?status=active&status=monitoring&limit=200");
    return page.items.sort(
      (a, b) =>
        PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority] ||
        b.started_at.localeCompare(a.started_at),
    );
  } catch {
    return null;
  }
}

async function backendStatus(): Promise<Health | null> {
  try {
    return await api<Health>("/health", { auth: false });
  } catch {
    return null;
  }
}

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ denied?: string }>;
}) {
  const [user, health, events, { denied }] = await Promise.all([
    verifySession(),
    backendStatus(),
    openEvents(),
    searchParams,
  ]);
  const urgent = events?.filter((e) => e.priority === "critical" || e.priority === "high") ?? [];
  const firstName = user.full_name.split(" ")[0];

  return (
    <div className="flex flex-col gap-12">
      {denied && (
        <p role="alert" className="border-l-2 border-signal pl-3 text-sm">
          That page needs a different role. Ask an admin if you need access.
        </p>
      )}

      <section>
        <h1 className="display mb-3 text-5xl">Good to see you, {firstName}.</h1>
        <p className="max-w-2xl text-lg leading-relaxed text-steel">
          {events === null
            ? "Events could not be loaded."
            : events.length === 0
              ? "No open events. When analysts open one from field reports, it appears here, most urgent first."
              : `${events.length} open ${events.length === 1 ? "event" : "events"}${
                  urgent.length ? `, ${urgent.length} high priority or critical` : ""
                }.`}
        </p>
      </section>

      {events && events.length > 0 && (
        <section aria-labelledby="attention" className="border-t border-line pt-6">
          <div className="mb-4 flex items-baseline justify-between gap-4">
            <h2 id="attention" className="display text-2xl">
              Needs attention
            </h2>
            <Link href="/events" className="text-sm text-steel hover:text-bone">
              All events →
            </Link>
          </div>
          <ul className="flex max-w-4xl flex-col divide-y divide-line border-y border-line">
            {events.slice(0, 5).map((e) => (
              <li key={e.id}>
                <Link
                  href={`/events/${e.id}`}
                  className="grid gap-2 py-3 transition-colors hover:bg-panel sm:grid-cols-[6rem_1fr_auto] sm:items-center sm:gap-4 sm:px-2"
                >
                  <span>
                    <PriorityBadge priority={e.priority} />
                  </span>
                  <span className="min-w-0">
                    <span className="block">{e.title}</span>
                    <span className="block text-sm text-steel">
                      {eventTypeLabel(e.event_type)} · since {formatDhaka(e.started_at)} ·{" "}
                      <EvidenceSummary counts={e.evidence_counts} />
                    </span>
                  </span>
                  <span className="text-sm">
                    <AssessmentText assessment={e.assessment} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="system" className="border-t border-line pt-6">
        <h2 id="system" className="display mb-4 text-2xl">
          System
        </h2>
        <dl className="grid max-w-2xl grid-cols-[10rem_1fr] gap-y-2 text-sm">
          <dt className="text-steel">Backend</dt>
          <dd className={health ? "text-ok" : "text-signal"}>
            {health ? "Running" : "Not reachable"}
          </dd>
          <dt className="text-steel">Version</dt>
          <dd>{health?.version ?? "Unknown"}</dd>
          <dt className="text-steel">Environment</dt>
          <dd>{health?.environment ?? "Unknown"}</dd>
          <dt className="text-steel">Signed in as</dt>
          <dd>{user.email}</dd>
        </dl>
      </section>

      <section aria-labelledby="build" className="border-t border-line pt-6">
        <h2 id="build" className="display mb-4 text-2xl">
          What is built
        </h2>
        <ul className="flex max-w-3xl flex-col divide-y divide-line">
          {BUILD.map((b) => (
            <li key={b.name} className="grid gap-1 py-3 sm:grid-cols-[4rem_1fr]">
              <span className={`text-sm font-semibold ${STATE_STYLE[b.state].cls}`}>
                {STATE_STYLE[b.state].label}
              </span>
              <div>
                <p>{b.name}</p>
                <p className="text-sm text-steel">{b.note}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
