"use client";

import { Layers, MapPinned, Plus } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AssessmentText, EvidenceSummary, PriorityBadge } from "@/components/event-badges";
import { eventTypeLabel } from "@/lib/event-types";
import { FAMILIES, FAMILY_SHAPE, PRIORITY_COLOR } from "@/lib/events";
import { formatDhaka } from "@/lib/format";
import type { CarcuxEvent, FieldReport, Priority } from "@/lib/types";

const MapView = dynamic(() => import("./map-view"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-ground" aria-busy="true" />,
});

const RANK: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3 };

function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} days`;
}

function ShapeKey({ shape, color }: { shape: string; color: string }) {
  const d =
    shape === "diamond"
      ? "M7 1 L13 7 L7 13 L1 7 Z"
      : shape === "triangle"
        ? "M7 1.5 L13 12 L1 12 Z"
        : "M1 7 a6 6 0 1 0 12 0 a6 6 0 1 0 -12 0";
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <path d={d} fill={color} />
    </svg>
  );
}

export function Situation({
  events,
  reports,
  canSubmit,
  canSeeReports,
}: {
  events: CarcuxEvent[];
  reports: FieldReport[];
  canSubmit: boolean;
  canSeeReports: boolean;
}) {
  const [family, setFamily] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showReports, setShowReports] = useState(true);
  const [streetDetail, setStreetDetail] = useState(false);
  const [legend, setLegend] = useState(false);

  const visible = useMemo(
    () =>
      events
        .filter((e) => !family || e.family === family)
        .sort(
          (a, b) => RANK[a.priority] - RANK[b.priority] || b.started_at.localeCompare(a.started_at),
        ),
    [events, family],
  );

  return (
    <div className="grid grid-rows-[60vh_auto] md:h-full md:grid-cols-[1fr_24rem] md:grid-rows-1">
      <div className="relative min-h-0">
        <MapView
          events={visible}
          reports={canSeeReports && showReports ? reports : []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          showReports={canSeeReports && showReports}
          streetDetail={streetDetail}
        />

        <div className="pointer-events-none absolute inset-x-3 bottom-3 z-[500] flex items-end justify-between gap-3">
          <button
            type="button"
            onClick={() => setLegend((v) => !v)}
            aria-expanded={legend}
            className="pointer-events-auto rounded-md border border-line bg-panel px-3 py-1.5 text-sm text-muted md:hidden"
          >
            Key
          </button>
          <div
            className={`pointer-events-auto absolute bottom-12 left-0 rounded-md border border-line bg-panel/95 px-3 py-2 text-xs text-muted md:static md:block ${
              legend ? "block" : "hidden"
            }`}
          >
            <p className="mb-1.5 flex flex-wrap gap-x-3 gap-y-1">
              {(["critical", "high", "medium", "low"] as Priority[]).map((p) => (
                <span key={p} className="flex items-center gap-1.5 capitalize">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ background: PRIORITY_COLOR[p] }}
                  />
                  {p}
                </span>
              ))}
            </p>
            <p className="flex flex-wrap gap-x-3 gap-y-1">
              {FAMILIES.map((f) => (
                <span key={f.value} className="flex items-center gap-1.5">
                  <ShapeKey shape={FAMILY_SHAPE[f.value]} color="#8da2ad" />
                  {f.label}
                </span>
              ))}
              {canSeeReports && showReports && (
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-water" />
                  Report, 48 h
                </span>
              )}
            </p>
          </div>
          {canSubmit && (
            <Link
              href="/field-reports/new"
              className="pointer-events-auto inline-flex h-12 items-center gap-2 rounded-full whitespace-nowrap bg-water px-5 font-semibold text-ground shadow-lg shadow-black/30 transition-colors hover:bg-[#4dbac8]"
            >
              <Plus size={18} strokeWidth={2.25} aria-hidden="true" />
              New report
            </Link>
          )}
        </div>

        <div className="absolute top-3 right-3 z-[500] flex flex-col gap-2">
          {canSeeReports && (
            <button
              type="button"
              aria-pressed={showReports}
              onClick={() => setShowReports((v) => !v)}
              className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors ${
                showReports
                  ? "border-water bg-water-soft text-ink"
                  : "border-line bg-panel text-muted hover:text-ink"
              }`}
            >
              <MapPinned size={15} strokeWidth={1.75} aria-hidden="true" />
              Field reports
            </button>
          )}
          <button
            type="button"
            aria-pressed={streetDetail}
            onClick={() => setStreetDetail((v) => !v)}
            title="Street-level map tiles from OpenStreetMap (needs internet)"
            className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors ${
              streetDetail
                ? "border-water bg-water-soft text-ink"
                : "border-line bg-panel text-muted hover:text-ink"
            }`}
          >
            <Layers size={15} strokeWidth={1.75} aria-hidden="true" />
            Street detail
          </button>
        </div>
      </div>

      <aside
        aria-label="Open events"
        className="flex min-h-0 flex-col border-t border-line bg-panel md:border-t-0 md:border-l"
      >
        <div className="border-b border-line px-4 pt-4 pb-3">
          <div className="mb-3 flex items-baseline justify-between">
            <h1 className="display text-2xl">Open events</h1>
            <span className="display text-2xl text-muted">{visible.length}</span>
          </div>
          <div role="group" aria-label="Kind of event" className="flex flex-wrap gap-1.5">
            {[{ value: "", label: "All" }, ...FAMILIES].map((f) => (
              <button
                key={f.value}
                type="button"
                aria-pressed={family === f.value}
                onClick={() => setFamily(f.value)}
                className={`rounded-full border px-3 py-1 text-[13px] transition-colors ${
                  family === f.value
                    ? "border-water bg-water-soft text-ink"
                    : "border-line text-muted hover:text-ink"
                }`}
              >
                {f.value ? f.label.split(" ")[0] : f.label}
              </button>
            ))}
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="p-4 text-sm text-muted">
            <p className="mb-3">No open events{family ? " of this kind" : ""}.</p>
            <Link href="/events" className="text-water hover:underline">
              See resolved and dismissed events
            </Link>
          </div>
        ) : (
          <ul className="min-h-0 flex-1 overflow-y-auto">
            {visible.map((e) => {
              const active = e.id === selectedId;
              return (
                <li key={e.id} className="border-b border-line">
                  <button
                    type="button"
                    onClick={() => setSelectedId(e.id)}
                    aria-expanded={active}
                    className={`relative block w-full py-3 pr-4 pl-5 text-left transition-colors ${
                      active ? "bg-panel-2" : "hover:bg-panel-2/60"
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className="absolute top-3 bottom-3 left-0 w-1 rounded-r"
                      style={{ background: PRIORITY_COLOR[e.priority] }}
                    />
                    <span className="mb-0.5 flex items-center justify-between gap-2 text-xs text-muted">
                      <span>{eventTypeLabel(e.event_type)}</span>
                      <span>{ago(e.started_at)}</span>
                    </span>
                    <span className="display block text-lg leading-tight">{e.title}</span>
                    {e.place_name && (
                      <span className="block text-sm text-muted">{e.place_name}</span>
                    )}
                  </button>
                  {active && (
                    <div className="flex flex-col gap-3 bg-panel-2 px-5 pb-4 text-sm">
                      <div className="flex flex-wrap items-center gap-3">
                        <PriorityBadge priority={e.priority} />
                        <AssessmentText assessment={e.assessment} />
                      </div>
                      <p>
                        <EvidenceSummary counts={e.evidence_counts} />
                      </p>
                      <p className="text-muted">Since {formatDhaka(e.started_at)}</p>
                      <Link
                        href={`/events/${e.id}`}
                        className="inline-flex h-9 w-fit items-center rounded-md bg-water px-3 font-semibold text-ground hover:bg-[#4dbac8]"
                      >
                        Open event
                      </Link>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}
