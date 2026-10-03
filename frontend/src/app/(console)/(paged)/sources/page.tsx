import { AlertTriangle, CheckCircle2, PauseCircle, RadioTower, Rss } from "lucide-react";
import Link from "next/link";

import { DataTable, rowCls, td, th, wide } from "@/components/data-table";
import { PageBand, PageBody, Panel, StatTile, StatTiles } from "@/components/page-header";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import { ADAPTER, LANGUAGE_LABEL, SOURCE_TYPE_LABEL } from "@/lib/signals";
import { REPORT_REVIEWERS, type Source } from "@/lib/types";

import { BackfillForm } from "./backfill-form";
import { AddFeedForm, SourceActions } from "./source-controls";

export const metadata = { title: "Sources" };

function every(minutes: number): string {
  if (minutes % 60 === 0) return minutes === 60 ? "Every hour" : `Every ${minutes / 60} hours`;
  return `Every ${minutes} minutes`;
}

function Health({ source }: { source: Source }) {
  if (source.adapter === "manual") return <span className="text-muted">Entered by analysts</span>;
  if (!source.enabled)
    return (
      <span className="inline-flex items-center gap-1.5 text-muted">
        <PauseCircle size={15} aria-hidden="true" />
        Switched off
      </span>
    );
  if (!source.last_run_at) return <span className="text-muted">Not read yet</span>;
  if (source.last_error)
    return (
      <span className="flex flex-col gap-0.5">
        <span className="inline-flex items-center gap-1.5 font-semibold text-critical">
          <AlertTriangle size={15} aria-hidden="true" />
          Failed {formatDhaka(source.last_run_at)}
        </span>
        <span className="text-sm text-critical">{source.last_error}</span>
        {source.last_success_at && (
          <span className="text-xs text-muted">
            Last worked {formatDhaka(source.last_success_at)}
          </span>
        )}
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1.5 text-brand">
      <CheckCircle2 size={15} aria-hidden="true" />
      Read {formatDhaka(source.last_run_at)}
    </span>
  );
}

export default async function SourcesPage() {
  const user = await requireRole(...REPORT_REVIEWERS);
  const admin = user.role === "admin";
  const sources = await api<Source[]>("/sources");
  const automatic = sources.filter((s) => s.adapter !== "manual");
  const on = automatic.filter((s) => s.enabled);
  const failing = on.filter((s) => s.last_error);

  return (
    <>
      <PageBand
        scene="hills"
        icon={Rss}
        title="Sources"
        description="Where public signals come from. Feeds are read on a schedule by the ingest worker; bulletins without a feed are entered by analysts."
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={Rss}
            value={on.length}
            label="Feeds switched on"
            note={`${automatic.length - on.length} switched off`}
            tone="green"
          />
          <StatTile
            icon={AlertTriangle}
            value={failing.length}
            label="Failed last time"
            note={failing.length ? "See the reason below" : "All read normally"}
            tone={failing.length ? "red" : "forest"}
          />
          <StatTile
            icon={RadioTower}
            value={sources.reduce((n, s) => n + s.signals_24h, 0)}
            label="Signals, 24 hours"
            note="Across all sources"
            tone="blue"
            href="/signals"
          />
          <StatTile
            icon={RadioTower}
            value={sources.reduce((n, s) => n + s.signal_count, 0)}
            label="Signals in all"
            note="Since collection began"
            tone="amber"
          />
        </StatTiles>

        <DataTable
          head={
            <tr>
              <th scope="col" className={th}>
                Source
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                How
              </th>
              <th scope="col" className={th}>
                Last read
              </th>
              <th scope="col" className={`${th} ${wide}`}>
                Signals
              </th>
              {admin && (
                <th scope="col" className={th}>
                  <span className="sr-only">Actions</span>
                </th>
              )}
            </tr>
          }
        >
          {sources.map((s) => {
            const { label, icon: Icon } = ADAPTER[s.adapter];
            return (
              <tr key={s.id} className={rowCls}>
                <td className={td}>
                  <span className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-soft text-brand">
                      <Icon size={17} aria-hidden="true" />
                    </span>
                    <span>
                      <span className="block font-semibold text-ink">{s.name}</span>
                      <span className="text-sm text-muted">
                        {SOURCE_TYPE_LABEL[s.source_type]}
                        {s.domain && ` · ${s.domain}`}
                        {` · ${LANGUAGE_LABEL[s.language] ?? s.language}`}
                      </span>
                    </span>
                  </span>
                </td>
                <td className={`${td} ${wide} text-muted`}>
                  {label}
                  {s.adapter !== "manual" && (
                    <span className="block text-sm">{every(s.interval_minutes)}</span>
                  )}
                </td>
                <td className={td}>
                  <Health source={s} />
                </td>
                <td className={`${td} ${wide}`}>
                  <Link
                    href={`/signals?source=${s.id}`}
                    className="font-semibold text-brand hover:underline"
                  >
                    {s.signal_count}
                  </Link>
                  <span className="block text-sm text-muted">{s.signals_24h} in 24 h</span>
                </td>
                {admin && (
                  <td className={td}>
                    <SourceActions
                      sourceId={s.id}
                      name={s.name}
                      enabled={s.enabled}
                      readable={s.adapter !== "manual"}
                    />
                  </td>
                )}
              </tr>
            );
          })}
        </DataTable>

        {admin && (
          <Panel
            id="backfill"
            title="Fill in a past period"
            description="Read a source's archive for a case study. GDACS covers floods, cyclones and earthquakes; ReliefWeb (once switched on) adds BMD and FFWC bulletins. For newspaper articles, import a list under Public signals."
          >
            <BackfillForm
              sources={sources
                .filter((s) => s.adapter === "gdacs" || s.adapter === "reliefweb")
                .map((s) => ({ id: s.id, name: s.name }))}
            />
          </Panel>
        )}

        {admin && (
          <Panel
            id="add-feed"
            title="Add a news feed"
            description="Any RSS or Atom feed. Only items about a disaster or disruption that name a place in Bangladesh are kept, as headline, short excerpt and link."
          >
            <AddFeedForm />
          </Panel>
        )}
      </PageBody>
    </>
  );
}
