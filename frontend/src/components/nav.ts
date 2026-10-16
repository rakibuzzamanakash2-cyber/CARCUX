import type { Role } from "@/lib/types";

export type NavIcon =
  | "map"
  | "events"
  | "reports"
  | "signals"
  | "review"
  | "sources"
  | "dataset"
  | "annotation"
  | "users"
  | "official"
  | "statements"
  | "audit";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIcon;
  roles?: Role[]; // omitted = everyone
  desktopOnly?: boolean; // left out of the phone tab bar, which has room for six
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Operate",
    items: [
      { href: "/", label: "Situation map", icon: "map" },
      { href: "/events", label: "Events", icon: "events" },
      {
        href: "/field-reports",
        label: "Field reports",
        icon: "reports",
        roles: ["admin", "analyst", "field_worker"],
      },
      { href: "/signals", label: "Public signals", icon: "signals" },
      { href: "/statements", label: "Statements", icon: "statements", desktopOnly: true },
      {
        href: "/review",
        label: "Review queue",
        icon: "review",
        roles: ["admin", "analyst"],
      },
      {
        href: "/annotation",
        label: "Second opinions",
        icon: "annotation",
        roles: ["admin", "analyst"],
        desktopOnly: true,
      },
    ],
  },
  {
    group: "Administer",
    items: [
      {
        href: "/sources",
        label: "Sources",
        icon: "sources",
        roles: ["admin", "analyst"],
        desktopOnly: true,
      },
      {
        href: "/dataset",
        label: "Dataset",
        icon: "dataset",
        roles: ["admin", "analyst"],
        desktopOnly: true,
      },
      { href: "/users", label: "Users", icon: "users", roles: ["admin"] },
      {
        href: "/official-pages",
        label: "Official pages",
        icon: "official",
        roles: ["admin", "official"],
      },
      {
        href: "/audit",
        label: "Audit log",
        icon: "audit",
        roles: ["admin"],
        desktopOnly: true,
      },
    ],
  },
];

/** Short labels for the phone tab bar. */
export const SHORT_LABEL: Record<string, string> = {
  "/": "Map",
  "/events": "Events",
  "/field-reports": "Reports",
  "/signals": "Signals",
  "/review": "Review",
  "/sources": "Sources",
  "/dataset": "Dataset",
  "/annotation": "Opinions",
  "/users": "Users",
  "/official-pages": "Official",
  "/statements": "Statements",
  "/audit": "Audit",
};
