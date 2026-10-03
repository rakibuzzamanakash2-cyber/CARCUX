import type { Role } from "@/lib/types";

export type NavIcon = "map" | "events" | "reports" | "review" | "users" | "audit";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIcon;
  roles?: Role[]; // omitted = everyone
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
      { href: "/review", label: "Review queue", icon: "review", roles: ["admin", "analyst"] },
    ],
  },
  {
    group: "Administer",
    items: [
      { href: "/users", label: "Users", icon: "users", roles: ["admin"] },
      { href: "/audit", label: "Audit log", icon: "audit", roles: ["admin"] },
    ],
  },
];

/** Short labels for the phone tab bar. */
export const SHORT_LABEL: Record<string, string> = {
  "/": "Map",
  "/events": "Events",
  "/field-reports": "Reports",
  "/review": "Review",
  "/users": "Users",
  "/audit": "Audit",
};
