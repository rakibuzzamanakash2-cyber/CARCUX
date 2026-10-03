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

/** Night-green sidebar on desktop, with counts that need attention; a tab bar on phones. */
export function Sidebar({ role, badges }: { role: Role; badges: Record<string, number> }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));
  const groups = NAV.map((g) => ({
    ...g,
    items: g.items.filter((i) => !i.roles || i.roles.includes(role)),
  })).filter((g) => g.items.length > 0);
  const badgeTone: Record<string, string> = {
    "/events": "bg-critical text-white",
    "/review": "bg-alert-bright text-night",
  };

  return (
    <>
      <nav
        aria-label="Main"
        className="relative hidden h-full flex-col overflow-hidden border-r border-white/5 bg-gradient-to-b from-forest to-night px-3 pt-5 md:flex"
      >
        {groups.map((g, gi) => (
          <div key={g.group} className={gi > 0 ? "mt-2 border-t border-white/10 pt-5" : ""}>
            <p className="mb-2 px-3 text-sm font-semibold text-night-muted">{g.group}</p>
            <ul className="mb-4 flex flex-col gap-1">
              {g.items.map((item) => {
                const Icon = ICONS[item.icon];
                const active = isActive(item.href);
                const count = badges[item.href] ?? 0;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] transition-colors ${
                        active
                          ? "bg-forest-2 font-semibold text-white shadow-lg shadow-black/20"
                          : "text-forest-ink hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      <Icon size={19} strokeWidth={1.8} aria-hidden="true" />
                      <span className="flex-1">{item.label}</span>
                      {count > 0 && (
                        <span
                          className={`min-w-6 rounded-full px-1.5 text-center text-xs leading-6 font-bold ${badgeTone[item.href]}`}
                        >
                          {count}
                          <span className="sr-only"> need attention</span>
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}

        {/* Sundarbans mangroves and a tiger, fading up into the navigation. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/art/sidebar.svg"
          alt=""
          aria-hidden="true"
          className="pointer-events-none mt-auto -mx-3 w-[calc(100%+1.5rem)] max-w-none select-none"
        />
        <p className="absolute bottom-4 left-5 border-l-2 border-red pl-3 text-xs leading-snug text-forest-ink/80">
          Disasters and disruptions
          <br />
          in Bangladesh
        </p>
      </nav>

      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-[1000] border-t border-white/10 bg-night md:hidden"
      >
        <ul className="flex justify-around">
          {groups
            .flatMap((g) => g.items)
            .map((item) => {
              const Icon = ICONS[item.icon];
              const active = isActive(item.href);
              const count = badges[item.href] ?? 0;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`relative flex flex-col items-center gap-0.5 px-2 py-2 text-[11px] font-semibold ${
                      active ? "text-[#5fd38a]" : "text-night-muted"
                    }`}
                  >
                    {active && (
                      <span
                        aria-hidden="true"
                        className="absolute top-0 h-0.5 w-8 rounded-full bg-[#5fd38a]"
                      />
                    )}
                    <Icon size={20} strokeWidth={1.8} aria-hidden="true" />
                    {SHORT_LABEL[item.href] ?? item.label}
                    {count > 0 && (
                      <span
                        className={`absolute top-1 right-1 min-w-4 rounded-full px-1 text-center text-[10px] leading-4 font-bold ${badgeTone[item.href]}`}
                      >
                        {count}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
        </ul>
      </nav>
    </>
  );
}
