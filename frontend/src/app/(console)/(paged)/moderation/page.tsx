import { ShieldAlert } from "lucide-react";
import Link from "next/link";

import { PageBand, PageBody } from "@/components/page-header";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import type { ModerationComment } from "@/lib/types";

import { ModerationItem } from "./moderation-item";

export const metadata = { title: "Moderation" };

const TABS = [
  { value: "reported", label: "Reported" },
  { value: "hidden", label: "Hidden" },
  { value: "all", label: "All comments" },
] as const;

export default async function ModerationPage({
  searchParams,
}: {
  searchParams: Promise<{ state?: string }>;
}) {
  const user = await requireRole("admin", "official");
  const { state: raw } = await searchParams;
  const state = TABS.some((t) => t.value === raw) ? (raw as string) : "reported";
  const items = await api<ModerationComment[]>(`/moderation/comments?state=${state}`);
  return (
    <>
      <PageBand
        scene="hills"
        icon={ShieldAlert}
        title="Moderation"
        description={
          user.role === "admin"
            ? "Comments on official posts that people reported, and those hidden. Three reports hide a comment until you decide; keeping it stops further reports from hiding it."
            : "Comments on your page's posts that people reported, and those hidden."
        }
      />
      <PageBody>
        <nav aria-label="Which comments" className="flex flex-wrap gap-2">
          {TABS.map((t) => (
            <Link
              key={t.value}
              href={`/moderation?state=${t.value}`}
              aria-current={t.value === state ? "page" : undefined}
              className={`rounded-full px-3 py-1.5 text-sm font-semibold ${
                t.value === state ? "bg-brand text-white" : "bg-panel text-ink ring-1 ring-line"
              }`}
            >
              {t.label}
            </Link>
          ))}
        </nav>
        {items.length === 0 ? (
          <p className="text-muted">Nothing here.</p>
        ) : (
          <ul className="flex max-w-3xl flex-col gap-3">
            {items.map((c) => (
              <ModerationItem key={c.id} c={c} admin={user.role === "admin"} />
            ))}
          </ul>
        )}
      </PageBody>
    </>
  );
}
