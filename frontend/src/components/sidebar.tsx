"use client";

import { ClipboardList, Inbox, Map, Radar, ScrollText, Users } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV, SHORT_LABEL, type NavIcon } from "@/components/nav";
import type { Role } from "@/lib/types";

const ICONS: Record<NavIcon, typeof Map> = {
  map: Map,
  events: Radar,
  reports: ClipboardList,
  review: Inbox,
  users: Users,
  audit: ScrollText,
};

/** Forest-green sidebar on desktop; a white tab bar at the bottom on phones. */
export function Sidebar({ role }: { role: Role }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const groups = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.roles || i.roles.includes(role)),
  })).filter((g) => g.items.length > 0);

  return (
    <>
      <nav aria-label="Main" className="hidden h-full flex-col bg-forest px-3 py-5 md:flex">
        {groups.map((g) => (
          <div key={g.group} className="mb-6">
            <p className="mb-2 px-3 text-xs font-semibold tracking-wide text-forest-ink/60">
              {g.group}
            </p>
            <ul className="flex flex-col gap-0.5">
              {g.items.map((item) => {
                const Icon = ICONS[item.icon];
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`relative flex items-center gap-3 rounded-md px-3 py-2 text-[15px] transition-colors ${
                        active
                          ? "bg-forest-2 font-semibold text-white"
                          : "text-forest-ink hover:bg-forest-2/60 hover:text-white"
                      }`}
                    >
                      {active && (
                        <span
                          aria-hidden="true"
                          className="absolute top-2 bottom-2 -left-3 w-1 rounded-r bg-[#3fbf6a]"
                        />
                      )}
                      <Icon size={18} strokeWidth={1.75} aria-hidden="true" />
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
        <p className="mt-auto px-3 text-xs text-forest-ink/50">
          Disasters and disruptions in Bangladesh
        </p>
      </nav>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-[1000] border-t border-line bg-panel md:hidden"
      >
        <ul className="flex justify-around">
          {groups
            .flatMap((g) => g.items)
            .map((item) => {
              const Icon = ICONS[item.icon];
              const active = isActive(item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`relative flex flex-col items-center gap-0.5 px-2 py-2 text-[11px] font-semibold ${
                      active ? "text-brand" : "text-muted"
                    }`}
                  >
                    {active && (
                      <span
                        aria-hidden="true"
                        className="absolute top-0 h-0.5 w-8 rounded-full bg-brand"
                      />
                    )}
                    <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
                    {SHORT_LABEL[item.href] ?? item.label}
                  </Link>
                </li>
              );
            })}
        </ul>
      </nav>
    </>
  );
}
