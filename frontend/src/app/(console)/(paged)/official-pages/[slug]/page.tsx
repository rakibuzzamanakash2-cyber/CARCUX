import { ExternalLink, FileText, Landmark } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { StatementCard } from "@/components/statement-bits";
import { api, ApiError } from "@/lib/api";
import { verifyStaff } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import {
  pageKindLabel,
  VERIFICATION_LABEL,
  type OfficialPage,
  type OfficialPageDetail,
  type Statement,
} from "@/lib/types";

import {
  AddOfficialForm,
  EditPageForm,
  LetterForm,
  ReinstateButton,
  SuspendForm,
  VerifyForm,
} from "../page-forms";
import { PageStatusBadge } from "../status-badge";

export const metadata = { title: "Official page" };

function isDetail(p: OfficialPage | OfficialPageDetail): p is OfficialPageDetail {
  return "members" in p;
}

export default async function OfficialPageView({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ created?: string }>;
}) {
  const [{ slug }, { created }] = await Promise.all([params, searchParams]);
  const user = await verifyStaff();
  let page: OfficialPage | OfficialPageDetail;
  try {
    page = await api<OfficialPage | OfficialPageDetail>(
      `/official-pages/by-slug/${encodeURIComponent(slug)}`,
    );
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const admin = user.role === "admin";
  const detail = isDetail(page) ? page : null;
  const statements = await api<Statement[]>(`/statements?page_id=${page.id}`);

  return (
    <>
      <PageBand
        scene="hills"
        icon={Landmark}
        back={admin ? { href: "/official-pages", label: "All official pages" } : undefined}
        kicker={pageKindLabel(page.kind)}
        title={page.name}
        description={page.name_bn ?? undefined}
      >
        <div className="mt-3">
          <PageStatusBadge status={page.status} onBand />
        </div>
      </PageBand>
      <PageBody>
        {created && (
          <p role="status" className="rounded-md border border-ok/50 bg-ok/10 px-3 py-2 text-sm">
            Page created. It stays hidden until you verify it.
          </p>
        )}
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <div className="flex flex-col gap-6">
            <Panel title="About" id="about">
              {page.description ? (
                <p className="whitespace-pre-line">{page.description}</p>
              ) : (
                <p className="text-muted">No description yet.</p>
              )}
              {page.website && (
                <a
                  href={page.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-3 inline-flex items-center gap-1 font-semibold text-brand hover:underline"
                >
                  {page.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                  <ExternalLink size={14} aria-hidden="true" />
                </a>
              )}
            </Panel>

            <Panel title="Statements" id="page-statements">
              {statements.length === 0 ? (
                <p className="text-sm text-muted">
                  No statements yet.
                  {user.official_page?.id === page.id &&
                    page.status === "verified" &&
                    " Open an event and choose Write a statement."}
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  {statements.map((x) => (
                    <StatementCard key={x.id} s={x} />
                  ))}
                </div>
              )}
            </Panel>

            {detail && (
              <Panel
                title="Officials"
                id="officials"
                description="People who speak for this page. Each signs in with their own account."
              >
                {detail.members.length === 0 ? (
                  <p className="text-sm text-muted">No official accounts yet.</p>
                ) : (
                  <ul className="mb-4 divide-y divide-line text-sm">
                    {detail.members.map((m) => (
                      <li key={m.id} className="flex flex-wrap justify-between gap-2 py-2">
                        <span>
                          <span className="font-semibold">{m.full_name}</span>
                          <span className="text-muted"> · {m.email}</span>
                          {!m.is_active && <span className="text-critical"> · deactivated</span>}
                        </span>
                        <span className="text-muted">
                          {m.last_login_at
                            ? `last signed in ${formatDhaka(m.last_login_at)}`
                            : "never signed in"}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {admin && <AddOfficialForm page={detail} />}
              </Panel>
            )}

            {admin && detail && (
              <Panel title="Details" id="details">
                <EditPageForm page={detail} />
              </Panel>
            )}
          </div>

          <div className="flex flex-col gap-6">
            <Panel title="Verification" id="verification">
              {page.status === "verified" && page.verification_method ? (
                <p className="text-sm">
                  <span className="font-semibold">Verified</span>
                  {page.verified_at && ` on ${formatDhaka(page.verified_at)}`}:{" "}
                  {VERIFICATION_LABEL[page.verification_method]}.
                </p>
              ) : page.status === "suspended" ? (
                <p className="text-sm text-critical">
                  Suspended{detail?.suspended_reason ? `: ${detail.suspended_reason}` : "."}
                </p>
              ) : (
                <p className="text-sm text-muted">
                  Not verified yet. It is hidden from others and cannot publish.
                </p>
              )}
              {detail && (
                <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
                  <dt className="text-muted">Office email</dt>
                  <dd>{detail.contact_email ?? "not given"}</dd>
                  {detail.verified_by && (
                    <>
                      <dt className="text-muted">Verified by</dt>
                      <dd>{detail.verified_by.full_name}</dd>
                    </>
                  )}
                  {detail.verification_note && (
                    <>
                      <dt className="text-muted">What was checked</dt>
                      <dd className="whitespace-pre-line">{detail.verification_note}</dd>
                    </>
                  )}
                  <dt className="text-muted">Letter</dt>
                  <dd>
                    {detail.has_document ? (
                      admin ? (
                        <Link
                          href={`/official-pages/${page.slug}/letter`}
                          className="inline-flex items-center gap-1 font-semibold text-brand hover:underline"
                          prefetch={false}
                          target="_blank"
                        >
                          <FileText size={14} aria-hidden="true" />
                          Open the letter
                        </Link>
                      ) : (
                        "on file"
                      )
                    ) : (
                      "none"
                    )}
                    {detail.document_sha256 && (
                      <span className="block font-mono text-xs break-all text-muted">
                        SHA-256 {detail.document_sha256.slice(0, 16)}…
                      </span>
                    )}
                  </dd>
                </dl>
              )}
            </Panel>

            {admin && detail && page.status !== "suspended" && (
              <Panel title={page.status === "verified" ? "Verify again" : "Verify"} id="verify">
                <div className="flex flex-col gap-6">
                  <LetterForm page={detail} />
                  <VerifyForm page={detail} />
                </div>
              </Panel>
            )}
            {admin && detail && (
              <Panel
                title={page.status === "suspended" ? "Reinstate" : "Suspend"}
                id="suspend"
                tone={page.status === "suspended" ? undefined : "critical"}
              >
                {page.status === "suspended" ? (
                  <ReinstateButton page={detail} />
                ) : (
                  <SuspendForm page={detail} />
                )}
              </Panel>
            )}
          </div>
        </div>
      </PageBody>
    </>
  );
}
