import { Landmark } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { api } from "@/lib/api";
import { verifyStaff } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import { pageKindLabel, type OfficialPage } from "@/lib/types";

import { CreatePageForm } from "./page-forms";
import { PageStatusBadge } from "./status-badge";

export const metadata = { title: "Official pages" };

export default async function OfficialPagesPage() {
  const user = await verifyStaff();
  // An official has one page: theirs.
  if (user.role === "official" && user.official_page) {
    redirect(`/official-pages/${user.official_page.slug}`);
  }
  const admin = user.role === "admin";
  const pages = await api<OfficialPage[]>("/official-pages");
  const verified = pages.filter((p) => p.status === "verified").length;

  return (
    <>
      <PageBand
        scene="hills"
        icon={Landmark}
        title="Official pages"
        description={
          admin
            ? `${pages.length} ${pages.length === 1 ? "page" : "pages"}, ${verified} verified. A page is verified by an admin after the office confirms through its own email address or an official letter. Only verified pages are shown to others or can publish.`
            : "Verified government offices and office holders that publish statements on CARCUX."
        }
      />
      <PageBody>
        <Panel title="Pages" id="pages">
          {pages.length === 0 ? (
            <p className="text-sm text-muted">
              {admin ? "No official pages yet. Create the first one below." : "None yet."}
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {pages.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <Link
                      href={`/official-pages/${p.slug}`}
                      className="font-semibold hover:text-brand hover:underline"
                    >
                      {p.name}
                    </Link>
                    {p.name_bn && <span className="ml-2 text-muted">{p.name_bn}</span>}
                    <p className="text-sm text-muted">
                      {pageKindLabel(p.kind)}
                      {p.verified_at && ` · verified ${formatDhaka(p.verified_at)}`}
                    </p>
                  </div>
                  <PageStatusBadge status={p.status} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {admin && (
          <Panel
            title="New official page"
            id="new-page"
            description="Create it first; verify it once the office has confirmed."
          >
            <CreatePageForm />
          </Panel>
        )}
      </PageBody>
    </>
  );
}
