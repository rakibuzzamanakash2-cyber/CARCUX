"use client";

import {
  ChevronRight,
  Clock,
  Droplets,
  Layers,
  MapPin,
  MapPinned,
  Plus,
  Siren,
  Triangle,
  Diamond,
} from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AssessmentText } from "@/components/event-badges";
import { eventTypeIcon } from "@/lib/event-icons";
import { eventTypeLabel } from "@/lib/event-types";
import { FAMILIES, FAMILY_SHAPE, PRIORITY_COLOR, priorityLabel } from "@/lib/events";
import type { CarcuxEvent, FieldReport, Priority } from "@/lib/types";

const MapView = dynamic(() => import("./map-view"), {
  ssr: false,
  loading: () => <div className="h-full w-full bg-sea" aria-busy="true" />,
});

const RANK: Record<Priority, number> = { critical: 0, high: 1, medium: 2, low: 3 };
const FAMILY_ICON = {
  natural_calamity: Droplets,
  road_infrastructure: Diamond,
  urban_emergency: Triangle,
};
const PILL: Record<Priority, string> = {
  critical: "bg-critical/20 text-[#ff8b8f] ring-1 ring-critical/50",
  high: "bg-alert-bright/15 text-alert-bright ring-1 ring-alert-bright/40",
  medium: "bg-medium/20 text-[#8cbcff] ring-1 ring-medium/40",
  low: "bg-white/10 text-night-muted ring-1 ring-white/15",
};

function ago(iso: string): string {
  const minutes = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
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

/** A north arrow, for people reading the map as a map. */
function NorthArrow() {
  return (
    <div
      aria-hidden="true"
      className="flex h-14 w-14 flex-col items-center justify-center rounded-full border border-white/25 bg-night/80 text-white"
    >
      <span className="text-[10px] leading-none font-bold">N</span>
      <svg width="18" height="24" viewBox="0 0 18 24">
        <path d="M9 0 L17 22 L9 17 L1 22 Z" fill="#fff" />
        <path d="M9 0 L9 17 L1 22 Z" fill="#9db8a8" />
      </svg>
    </div>
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

  const toggle = (on: boolean) =>
    `flex items-center gap-2 rounded-lg border px-3.5 py-2 text-sm font-semibold shadow-lg shadow-black/30 transition-colors ${
      on
        ? "border-[#2fbf68]/60 bg-forest-2 text-white"
        : "border-white/20 bg-night/90 text-night-ink hover:bg-night-3"
    }`;

  return (
    <div className="grid grid-rows-[62vh_auto] gap-4 bg-night p-3 md:h-full md:grid-cols-[1fr_24rem] md:grid-rows-1 md:p-4">
      <div className="relative min-h-0 overflow-hidden rounded-xl border border-night-line shadow-2xl shadow-black/40">
        <MapView
          events={visible}
          reports={canSeeReports && showReports ? reports : []}
          selectedId={selectedId}
          onSelect={setSelectedId}
          showReports={canSeeReports && showReports}
          streetDetail={streetDetail}
        />

        <div className="absolute top-3 right-3 z-[500] flex flex-col items-end gap-2">
          {canSeeReports && (
            <button
              type="button"
              aria-pressed={showReports}
              onClick={() => setShowReports((v) => !v)}
              className={toggle(showReports)}
            >
              <MapPinned size={16} strokeWidth={1.9} aria-hidden="true" />
              Field reports
            </button>
          )}
          <button
            type="button"
            aria-pressed={streetDetail}
            onClick={() => setStreetDetail((v) => !v)}
            title="Street-level map tiles from OpenStreetMap (needs internet)"
            className={toggle(streetDetail)}
          >
            <Layers size={16} strokeWidth={1.9} aria-hidden="true" />
            Street detail
          </button>
        </div>

        <div className="pointer-events-none absolute inset-x-3 bottom-3 z-[500] flex items-end justify-between gap-3">
          <div className="relative">
            <button
              type="button"
              onClick={() => setLegend((v) => !v)}
              aria-expanded={legend}
              className="pointer-events-auto rounded-lg border border-white/20 bg-night/90 px-3 py-2 text-sm font-semibold text-night-ink md:hidden"
            >
              Key
            </button>
            <div
              className={`pointer-events-auto absolute bottom-12 left-0 rounded-lg border border-white/15 bg-night/90 px-4 py-3 text-[13px] text-night-ink shadow-xl backdrop-blur md:static md:block ${
                legend ? "block" : "hidden"
              }`}
            >
              <p className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
                {(["critical", "high", "medium", "low"] as Priority[]).map((p) => (
                  <span key={p} className="flex items-center gap-1.5">
                    <span
                      className="h-3 w-3 rounded-full ring-2 ring-white/70"
                      style={{ background: PRIORITY_COLOR[p] }}
                    />
                    {priorityLabel(p)}
                  </span>
                ))}
              </p>
              <p className="flex flex-wrap gap-x-4 gap-y-1">
                {FAMILIES.map((f) => (
                  <span key={f.value} className="flex items-center gap-1.5">
                    <ShapeKey shape={FAMILY_SHAPE[f.value]} color="#e6f1ea" />
                    {f.label}
                  </span>
                ))}
                {canSeeReports && showReports && (
                  <span className="flex items-center gap-1.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#3ddc84]" />
                    Report, 48 h
                  </span>
                )}
              </p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-3">
            <NorthArrow />
            {canSubmit && (
              <Link
                href="/field-reports/new"
                className="pointer-events-auto inline-flex h-12 items-center gap-2 rounded-full bg-forest-2 px-6 font-semibold whitespace-nowrap text-white shadow-xl shadow-black/40 ring-1 ring-white/20 transition-colors hover:bg-[#1f9a50]"
              >
                <Plus size={19} strokeWidth={2.4} aria-hidden="true" />
                New report
              </Link>
            )}
          </div>
        </div>
      </div>

      <aside
        aria-label="Open events"
        className="flex min-h-0 flex-col overflow-hidden rounded-xl border border-night-line bg-night-2 text-night-ink shadow-2xl shadow-black/40"
      >
        <div className="border-b border-night-line px-4 pt-4 pb-3">
          <div className="mb-3 flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-critical/20 text-[#ff8b8f]">
              <Siren size={19} strokeWidth={1.9} aria-hidden="true" />
            </span>
            <h1 className="display flex-1 text-xl text-white">Open events</h1>
            <span className="flex h-8 min-w-8 items-center justify-center rounded-full bg-white/10 px-2 text-sm font-bold text-white">
              {visible.length}
            </span>
          </div>
          <div role="group" aria-label="Kind of event" className="flex flex-wrap gap-2">
            {[{ value: "", label: "All" }, ...FAMILIES].map((f) => {
              const Icon = f.value ? FAMILY_ICON[f.value as keyof typeof FAMILY_ICON] : null;
              const on = family === f.value;
              return (
                <button
                  key={f.value}
                  type="button"
                  aria-pressed={on}
                  onClick={() => setFamily(f.value)}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[13px] font-semibold transition-colors ${
                    on
                      ? "border-[#2fbf68] bg-forest-2 text-white"
                      : "border-white/15 text-night-ink hover:bg-white/5"
                  }`}
                >
                  {Icon && <Icon size={13} strokeWidth={2} aria-hidden="true" />}
                  {f.value ? f.label.split(" ")[0] : f.label}
                </button>
              );
            })}
          </div>
        </div>

        {visible.length === 0 ? (
          <div className="p-4 text-sm text-night-muted">
            <p className="mb-3">No open events{family ? " of this kind" : ""}.</p>
            <Link href="/events" className="font-semibold text-[#5fd38a] hover:underline">
              See resolved and dismissed events
            </Link>
          </div>
        ) : (
          <ul className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto p-3">
            {visible.map((e) => {
              const active = e.id === selectedId;
              const TypeIcon = eventTypeIcon(e.event_type);
              const color = PRIORITY_COLOR[e.priority];
              const critical = e.priority === "critical";
              return (
                <li
                  key={e.id}
                  className={`relative shrink-0 overflow-hidden rounded-xl border transition-colors ${
                    critical
                      ? "border-critical/70 bg-gradient-to-r from-critical/15 to-night-2"
                      : active
                        ? "border-[#2fbf68]/60 bg-night-3"
                        : "border-night-line bg-night-3/40 hover:bg-night-3"
                  }`}
                >
                  {critical && (
                    <span
                      aria-hidden="true"
                      className="absolute inset-y-0 left-0 w-1 bg-critical"
                    />
                  )}
                  <button
                    type="button"
                    onClick={() => setSelectedId(e.id)}
                    aria-expanded={active}
                    className="flex w-full items-start gap-3 py-3 pr-12 pl-4 text-left"
                  >
                    <span
                      className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white ring-2 ring-white/20"
                      style={{ background: color }}
                    >
                      <TypeIcon size={17} strokeWidth={2} aria-hidden="true" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-[13px] font-semibold" style={{ color }}>
                          {eventTypeLabel(e.event_type)}
                        </span>
                        <span className="inline-flex items-center gap-1 text-xs text-night-muted">
                          <Clock size={12} aria-hidden="true" />
                          {ago(e.started_at)}
                        </span>
                      </span>
                      <span className="block leading-snug font-semibold text-white">{e.title}</span>
                      {e.place_name && (
                        <span className="mt-0.5 flex items-center gap-1 text-[13px] text-night-muted">
                          <MapPin size={13} aria-hidden="true" />
                          {e.place_name}
                        </span>
                      )}
                      <span className="mt-2 flex flex-wrap items-center gap-2">
                        <span
                          className={`rounded-md px-2 py-0.5 text-xs font-bold ${PILL[e.priority]}`}
                        >
                          {priorityLabel(e.priority)}
                        </span>
                        {active && (
                          <span className="rounded-md bg-white px-2 py-0.5 text-xs">
                            <AssessmentText assessment={e.assessment} />
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                  <Link
                    href={`/events/${e.id}`}
                    className="absolute top-1/2 right-2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-night-muted transition-colors hover:bg-white/10 hover:text-white"
                  >
                    <ChevronRight size={20} aria-hidden="true" />
                    <span className="sr-only">Open event: {e.title}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </aside>
    </div>
  );
}
