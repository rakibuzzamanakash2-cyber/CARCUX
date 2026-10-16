import { Megaphone } from "lucide-react";
import { notFound, redirect } from "next/navigation";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { BriefView } from "@/components/statement-bits";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { isUuid } from "@/lib/format";
import type { Brief, Statement } from "@/lib/types";

import { StatementForm } from "./statement-form";

export const metadata = { title: "Write a statement" };

export default async function WriteStatementPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole("official");
  const { id } = await params;
  if (!isUuid(id)) notFound();
  if (user.official_page?.status !== "verified") redirect(`/events/${id}?denied=1`);
  let brief: Brief;
  let mine: Statement[];
  try {
    [brief, mine] = await Promise.all([
      api<Brief>(`/events/${id}/brief`),
      api<Statement[]>(`/statements?event_id=${id}&page_id=${user.official_page.id}`),
    ]);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  // A new statement on an event your page already spoke about corrects the latest one.
  const latest = mine.find((s) => !s.superseded_by_id) ?? null;

  return (
    <>
      <PageBand
        scene="padma"
        icon={Megaphone}
        back={{ href: `/events/${id}`, label: brief.event.title }}
        kicker={user.official_page.name}
        title={latest ? "Correct your statement" : "Write a statement"}
        description="CARCUX's brief is on the right: what the evidence says so far. The statement is yours, in your own words."
      />
      <PageBody>
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_24rem] lg:items-start">
          <Panel title="Statement" id="statement">
            <StatementForm eventId={id} correcting={latest} />
          </Panel>
          <Panel title="CARCUX's brief" id="brief" description={brief.event.title}>
            <BriefView brief={brief} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
