"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV } from "@/components/nav";
import type { Role } from "@/lib/types";

export function Sidebar({ role }: { role: Role }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  return (
    <nav
      aria-label="Main"
      className="flex flex-wrap items-center gap-x-6 gap-y-3 px-5 py-4 md:h-full md:flex-col md:flex-nowrap md:items-stretch md:gap-8 md:py-6"
    >
      <Link href="/" className="block w-24 md:w-36" aria-label="CARCUX overview">
        <Image src="/carcux-logo-light.png" alt="CARCUX" width={900} height={474} priority />
      </Link>

      {NAV.map(({ group, items }) => {
        const visible = items.filter((i) => !i.roles || i.roles.includes(role));
        if (visible.length === 0) return null;
        return (
          <div key={group}>
            <p className="mb-2 hidden text-xs text-steel md:block">{group}</p>
            <ul className="flex flex-wrap gap-x-4 md:flex-col md:gap-x-0">
              {visible.map((item) => {
                const active = isActive(item.href);
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={`relative flex items-center py-1.5 pl-4 text-[15px] transition-colors ${
                        active ? "text-bone" : "text-steel hover:text-bone"
                      }`}
                    >
                      {active && (
                        <span aria-hidden="true" className="absolute left-0 top-1/2 h-2 w-2 -translate-y-1/2 rotate-45 bg-signal" />
                      )}
                      {item.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
