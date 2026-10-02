"use client";

import { ClipboardList, Inbox, Map, Radar, ScrollText, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV, type NavIcon } from "@/components/nav";
import type { Role } from "@/lib/types";

const ICONS: Record<NavIcon, typeof Map> = {
  map: Map,
  events: Radar,
  reports: ClipboardList,
  review: Inbox,
  users: Users,
  audit: ScrollText,
};

/** Icon rail on desktop; a bottom tab bar on phones. */
export function Sidebar({ role }: { role: Role }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const items = NAV.filter((i) => !i.roles || i.roles.includes(role));

  return (
    <nav
      aria-label="Main"
      className="fixed inset-x-0 bottom-0 z-[1000] border-t border-line bg-panel md:static md:h-full md:border-t-0 md:border-r"
    >
      <ul className="flex justify-around md:flex-col md:justify-start md:gap-1 md:py-3">
        {items.map((item) => {
          const Icon = ICONS[item.icon];
          const active = isActive(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`relative flex flex-col items-center gap-1 px-2 py-2 text-[11px] font-medium transition-colors md:mx-2 md:rounded-md md:py-2.5 ${
                  active ? "text-ink md:bg-panel-2" : "text-muted hover:text-ink"
                }`}
              >
                {active && (
                  <span
                    aria-hidden="true"
                    className="absolute top-0 h-0.5 w-8 rounded-full bg-water md:top-1/2 md:-left-2 md:h-6 md:w-0.5 md:-translate-y-1/2"
                  />
                )}
                <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
