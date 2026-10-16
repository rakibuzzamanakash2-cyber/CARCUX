import { BadgeCheck, CircleHelp, CircleX, Info, Megaphone } from "lucide-react";
import Link from "next/link";

import { assessmentLabel, claimLabel } from "@/lib/events";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka } from "@/lib/format";
import { findingLabel, type Brief, type Finding, type Statement } from "@/lib/types";

const FINDING_STYLE: Record<Finding, { cls: string; Icon: typeof BadgeCheck }> = {
  confirmed: { cls: "bg-ok/10 text-ok ring-ok/40", Icon: BadgeCheck },
  partly_confirmed: { cls: "bg-alert-soft text-ink ring-alert/40", Icon: Info },
  denied: { cls: "bg-critical-soft text-critical ring-critical/40", Icon: CircleX },
  under_review: { cls: "bg-panel-2 text-muted ring-line", Icon: CircleHelp },
};

export function FindingBadge({ finding }: { finding: Finding }) {
  const { cls, Icon } = FINDING_STYLE[finding];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ${cls}`}
    >
      <Icon size={13} aria-hidden="true" />
      {findingLabel(finding)}
    </span>
  );
}

/** One statement in a list. */
export function StatementCard({ s, showEvent = true }: { s: Statement; showEvent?: boolean }) {
  return (
    <article className="rounded-lg border border-line bg-panel p-4" data-testid="statement">
      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="inline-flex items-center gap-1 font-semibold">
          <Megaphone size={14} className="text-brand" aria-hidden="true" />
          <Link
            href={`/official-pages/${s.page.slug}`}
            className="hover:text-brand hover:underline"
          >
            {s.page.name}
          </Link>
        </span>
        <FindingBadge finding={s.finding} />
        <span className="text-muted">{formatDhaka(s.published_at)}</span>
        {s.superseded_by_id && (
          <Link
            href={`/statements/${s.superseded_by_id}`}
            className="font-semibold text-critical hover:underline"
          >
            Corrected later
          </Link>
        )}
        {s.supersedes_id && <span className="text-muted">Correction</span>}
      </div>
      <h3 className="text-lg leading-snug font-semibold">
        <Link href={`/statements/${s.id}`} className="hover:text-brand hover:underline">
          {s.title}
        </Link>
      </h3>
      <p className="mt-1 line-clamp-3 whitespace-pre-line text-ink/90">{s.body}</p>
      {showEvent && (
        <p className="mt-2 text-sm text-muted">
          On{" "}
          <Link href={`/events/${s.event.id}`} className="font-semibold text-ink hover:underline">
            {s.event.title}
          </Link>{" "}
          · {eventTypeLabel(s.event.event_type)}
          {s.event.place_name && `, ${s.event.place_name}`}
        </p>
      )}
    </article>
  );
}

function pct(p: number | null) {
  if (p === null) return "no estimate yet";
  if (p < 0.01) return "less than 1% likely it happened";
  if (p > 0.99) return "over 99% likely it happened";
  return `${Math.round(p * 100)}% likely it happened`;
}

function value(d: Brief["details"][number]) {
  const v = d.estimate ?? "unknown";
  if (d.attribute === "casualty_count") return `${v} dead`;
  if (d.attribute === "affected_count") return `${v} ${d.unit ?? "people"} affected`;
  return String(v);
}

/** What CARCUX knows about an event, as the official sees it. */
export function BriefView({ brief }: { brief: Brief }) {
  const s = brief.suggestion;
  const c = brief.event.evidence_counts;
  return (
    <div className="flex flex-col gap-4 text-sm" data-testid="brief">
      <div className="rounded-lg bg-panel-2 p-3">
        <p className="text-muted">CARCUX suggests</p>
        <p className="text-lg font-semibold">
          {assessmentLabel(s.label)}
          <span className="ml-2 text-sm font-normal text-muted">{pct(s.probability)}</span>
        </p>
        <p className="mt-1 text-muted">
          Analysts&apos; assessment:{" "}
          <span className="font-semibold text-ink">{assessmentLabel(brief.event.assessment)}</span>
        </p>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5">
        <dt className="text-muted">Say it happened</dt>
        <dd>
          {s.sources_supporting} sources ({s.credible_supporting} credible)
        </dd>
        <dt className="text-muted">Say it did not</dt>
        <dd>
          {s.sources_denying} sources ({s.credible_denying} credible)
        </dd>
        <dt className="text-muted">Evidence</dt>
        <dd>
          {c.supports + c.partially_supports + c.contradicts + c.related + c.unrelated} linked
          items: {c.reporters} field reports, {c.signals} news and posts
        </dd>
        {s.counted_once > 0 && (
          <>
            <dt className="text-muted">Copies</dt>
            <dd>{s.counted_once} repeat another source and are counted once</dd>
          </>
        )}
        {s.disputed.length > 0 && (
          <>
            <dt className="text-muted">Disputed</dt>
            <dd className="font-semibold text-critical">
              {s.disputed.map((a) => claimLabel(a as never)).join(", ")}
            </dd>
          </>
        )}
      </dl>
      {brief.details.length > 0 && (
        <div>
          <p className="mb-1 font-semibold">Details stated by sources</p>
          <ul className="flex flex-col gap-1">
            {brief.details.map((d) => (
              <li key={d.attribute}>
                <span className="text-muted">{claimLabel(d.attribute)}:</span> best estimate{" "}
                <span className="font-semibold">{value(d)}</span>
                <span className="text-muted">
                  {" "}
                  from {d.sources} {d.sources === 1 ? "source" : "sources"}
                  {d.values.length > 1 && ` (values stated: ${d.values.join(", ")})`}
                </span>
                {d.disputed && <span className="ml-1 font-semibold text-critical">disputed</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {brief.sources.length > 0 && (
        <div>
          <p className="mb-1 font-semibold">Sources</p>
          <ul className="flex flex-col gap-1">
            {brief.sources.map((x, i) => (
              <li key={i}>
                {x.source}{" "}
                <span className="text-muted">
                  · says it {x.says === "unclear" ? "is unclear" : x.says} · track record{" "}
                  {Math.round(x.reliability * 100)}%
                  {x.disputes.length > 0 &&
                    ` · disputes ${x.disputes.map((a) => claimLabel(a as never).toLowerCase()).join(", ")}`}
                </span>
              </li>
            ))}
          </ul>
          {brief.field_workers > 0 && (
            <p className="mt-1 text-xs text-muted">
              Field workers are not named outside CARCUX&apos;s staff.
            </p>
          )}
        </div>
      )}
      <p className="text-xs text-muted">
        Brief of {formatDhaka(brief.generated_at)}. A suggestion from the evidence so far, not a
        finding: the statement is yours.
      </p>
    </div>
  );
}
