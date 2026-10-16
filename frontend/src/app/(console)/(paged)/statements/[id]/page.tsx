import { Megaphone } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { BriefView, FindingBadge } from "@/components/statement-bits";
import { api, ApiError } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { formatDhaka, isUuid } from "@/lib/format";
import type { StatementDetail } from "@/lib/types";

export const metadata = { title: "Statement" };

export default async function StatementPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ published?: string }>;
}) {
  await verifySession();
  const [{ id }, { published }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();
  let s: StatementDetail;
  try {
    s = await api<StatementDetail>(`/statements/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  return (
    <>
      <PageBand
        scene="padma"
        icon={Megaphone}
        back={{ href: `/events/${s.event.id}`, label: s.event.title }}
        kicker={s.page.name}
        title={s.title}
      >
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-white">
            <FindingBadge finding={s.finding} />
          </span>
          <span className="text-sm text-night-ink">{formatDhaka(s.published_at)}</span>
        </div>
      </PageBand>
      <PageBody>
        {published && (
          <p role="status" className="rounded-md border border-ok/50 bg-ok/10 px-3 py-2 text-sm">
            Published.
          </p>
        )}
        {s.superseded_by_id && (
          <p className="rounded-md border border-critical/50 bg-critical-soft px-3 py-2 text-sm">
            This statement was corrected.{" "}
            <Link href={`/statements/${s.superseded_by_id}`} className="font-semibold underline">
              Read the correction
            </Link>
          </p>
        )}
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start">
          <Panel title="Statement" id="statement">
            <p className="text-[17px] leading-relaxed whitespace-pre-line">{s.body}</p>
            <p className="mt-4 text-sm text-muted">
              <Link
                href={`/official-pages/${s.page.slug}`}
                className="font-semibold text-ink hover:underline"
              >
                {s.page.name}
              </Link>
              {s.author && ` · written by ${s.author}`}
              {s.supersedes_id && (
                <>
                  {" · corrects "}
                  <Link href={`/statements/${s.supersedes_id}`} className="underline">
                    an earlier statement
                  </Link>
                </>
              )}
            </p>
          </Panel>
          <Panel
            title="Informed by CARCUX"
            id="brief"
            description="The brief the official had in view when publishing. Because of it, this statement is never used as ground truth for testing CARCUX."
          >
            <BriefView brief={s.brief} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
