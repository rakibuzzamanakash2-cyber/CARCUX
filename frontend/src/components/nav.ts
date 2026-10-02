import type { Role } from "@/lib/types";

export type NavIcon = "map" | "events" | "reports" | "review" | "users" | "audit";

export interface NavItem {
  href: string;
  label: string;
  icon: NavIcon;
  roles?: Role[]; // omitted = everyone
}

export const NAV: NavItem[] = [
  { href: "/", label: "Map", icon: "map" },
  { href: "/events", label: "Events", icon: "events" },
  {
    href: "/field-reports",
    label: "Reports",
    icon: "reports",
    roles: ["admin", "analyst", "field_worker"],
  },
  { href: "/review", label: "Review", icon: "review", roles: ["admin", "analyst"] },
  { href: "/users", label: "Users", icon: "users", roles: ["admin"] },
  { href: "/audit", label: "Audit", icon: "audit", roles: ["admin"] },
];
