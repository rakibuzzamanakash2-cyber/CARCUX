/** Labels and colours for public signals and their sources. */
import { Globe2, Newspaper, PenLine, Satellite, type LucideIcon } from "lucide-react";

import type { Severity, SignalStatus, SourceAdapter, SourceType } from "@/lib/types";

export const SIGNAL_STATUSES: { value: SignalStatus; label: string }[] = [
  { value: "new", label: "New" },
  { value: "reviewed", label: "Reviewed" },
  { value: "dismissed", label: "Dismissed" },
];

export const signalStatusLabel = (v: SignalStatus) =>
  SIGNAL_STATUSES.find((s) => s.value === v)?.label ?? v;

export const SEVERITIES: { value: Severity; label: string; meaning: string }[] = [
  {
    value: "severe",
    label: "Severe",
    meaning: "Red alert: lives and property at serious risk.",
  },
  {
    value: "moderate",
    label: "Moderate",
    meaning: "Orange alert: significant impact likely.",
  },
  {
    value: "minor",
    label: "Minor",
    meaning: "Green alert: limited impact expected.",
  },
];

export const severityLabel = (v: Severity) => SEVERITIES.find((s) => s.value === v)?.label ?? v;

/** Pills for light pages. */
export const SEVERITY_STYLE: Record<Severity, string> = {
  severe: "bg-critical-soft text-critical ring-1 ring-critical/30",
  moderate: "bg-alert-soft text-alert ring-1 ring-alert/30",
  minor: "bg-brand-soft text-brand ring-1 ring-brand/25",
};

/** Map colours. Unknown severity (most news) is a calm sky blue. */
export const SEVERITY_COLOR: Record<Severity | "unknown", string> = {
  severe: "#ef3b42",
  moderate: "#f2912c",
  minor: "#3ddc84",
  unknown: "#7cc7f2",
};

export const SOURCE_TYPE_LABEL: Record<SourceType, string> = {
  news: "News",
  public_record: "Official alert",
  other: "Other",
};

export const ADAPTER: Record<SourceAdapter, { label: string; icon: LucideIcon }> = {
  gdacs: { label: "Disaster alerts feed", icon: Satellite },
  rss: { label: "News feed", icon: Newspaper },
  reliefweb: { label: "ReliefWeb reports", icon: Globe2 },
  manual: { label: "Entered or imported by hand", icon: PenLine },
};

export function precisionText(m: number | null): string {
  if (m === null) return "";
  if (m < 1000) return `within ${Math.round(m)} m`;
  return `within about ${Math.round(m / 1000)} km`;
}

export const LANGUAGE_LABEL: Record<string, string> = {
  en: "English",
  bn: "Bangla",
  "bn-Latn": "Banglish",
  mixed: "Mixed",
};
