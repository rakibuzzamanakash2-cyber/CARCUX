import type { Role } from "@/lib/types";

export interface NavItem {
  href: string;
  label: string;
  roles?: Role[]; // omitted = everyone
}

export const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Operate",
    items: [
      { href: "/", label: "Overview" },
      { href: "/map", label: "Situation map" },
      { href: "/events", label: "Events" },
      { href: "/field-reports", label: "Field reports" },
      { href: "/review", label: "Review queue", roles: ["admin", "analyst"] },
    ],
  },
  {
    group: "Administer",
    items: [
      { href: "/users", label: "Users", roles: ["admin"] },
      { href: "/audit", label: "Audit log", roles: ["admin"] },
    ],
  },
];
