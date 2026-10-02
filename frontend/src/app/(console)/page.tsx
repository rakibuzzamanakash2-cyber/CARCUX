import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import type { Health } from "@/lib/types";

export const metadata = { title: "Overview" };

// Where each part of CARCUX stands. Update as PRs land.
const BUILD = [
  { name: "Accounts, roles and audit log", state: "live", note: "Sign-in, four roles, instant revocation, append-only audit trail." },
  { name: "Dataset schema and validator", state: "live", note: "CARCUX-BD v1: events, observations, relations, dependences." },
  { name: "Field reports", state: "next", note: "Submission with location, time, photos and integrity checks." },
  { name: "Events and evidence", state: "next", note: "Event records linked to their supporting and conflicting evidence." },
  { name: "Situation map", state: "later", note: "Events on a map with status and priority." },
  { name: "Correlation and fusion engine", state: "later", note: "The research core: same-event grouping, source independence, calibrated assessment." },
] as const;

const STATE_STYLE = {
  live: { label: "Live", cls: "text-ok" },
  next: { label: "Next", cls: "text-amber" },
  later: { label: "Later", cls: "text-steel" },
} as const;

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
  const [user, health, { denied }] = await Promise.all([verifySession(), backendStatus(), searchParams]);
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
          No events are being tracked yet. Once field reports and the evidence engine are live,
          this page will open on the situations that need attention first.
        </p>
      </section>

      <section aria-labelledby="system" className="border-t border-line pt-6">
        <h2 id="system" className="display mb-4 text-2xl">System</h2>
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
        <h2 id="build" className="display mb-4 text-2xl">What is built</h2>
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
