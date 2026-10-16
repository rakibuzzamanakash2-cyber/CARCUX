import { Megaphone } from "lucide-react";

import { PageBand, PageBody } from "@/components/page-header";
import { StatementCard } from "@/components/statement-bits";
import { api } from "@/lib/api";
import { verifyStaff } from "@/lib/dal";
import type { Statement } from "@/lib/types";

export const metadata = { title: "Statements" };

export default async function StatementsPage() {
  await verifyStaff();
  const statements = await api<Statement[]>("/statements?limit=100");
  return (
    <>
      <PageBand
        scene="padma"
        icon={Megaphone}
        title="Official statements"
        description="What verified official pages have said about events, newest first. Each was written with CARCUX's brief in view and is marked as such."
      />
      <PageBody>
        {statements.length === 0 ? (
          <p className="text-muted">No statements yet.</p>
        ) : (
          <div className="flex max-w-3xl flex-col gap-4">
            {statements.map((s) => (
              <StatementCard key={s.id} s={s} />
            ))}
          </div>
        )}
      </PageBody>
    </>
  );
}
