import Link from "next/link";
import { notFound } from "next/navigation";

import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { FLAG_INFO, flagLabel, formatBytes, formatCoords, formatDhaka, isUuid } from "@/lib/format";
import { REPORT_READERS, REPORT_REVIEWERS, REPORT_SUBMITTERS, type FieldReport } from "@/lib/types";

import { VerifyPanel } from "./verify-panel";

export const metadata = { title: "Field report" };

const UUID_IN_TEXT = /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/gi;

/** Turn report ids inside a flag's detail into links to those reports. */
function linkReports(text: string) {
  return text.split(UUID_IN_TEXT).map((part, i) =>
    isUuid(part) ? (
      <Link
        key={i}
        href={`/field-reports/${part}`}
        className="underline underline-offset-2 hover:text-white"
      >
        report {part.slice(0, 8)}
      </Link>
    ) : (
      part
    ),
  );
}

export default async function FieldReportPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ submitted?: string }>;
}) {
  const user = await requireRole(...REPORT_READERS);
  const [{ id }, { submitted }] = await Promise.all([params, searchParams]);
  if (!isUuid(id)) notFound();

  let report: FieldReport;
  try {
    report = await api<FieldReport>(`/field-reports/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  const reviewer = REPORT_REVIEWERS.includes(user.role);
  const canSubmit = REPORT_SUBMITTERS.includes(user.role);
  const mapUrl = `https://www.openstreetmap.org/?mlat=${report.latitude}&mlon=${report.longitude}#map=17/${report.latitude}/${report.longitude}`;

  return (
    <div className="flex flex-col gap-10">
      <Link href="/field-reports" className="w-fit text-sm text-steel hover:text-bone">
        ← All field reports
      </Link>

      {submitted && (
        <div
          role="status"
          className="flex flex-col gap-3 border-l-2 border-ok pl-3 sm:flex-row sm:items-center sm:justify-between"
        >
          <p>
            {submitted === "new"
              ? "Report sent. Analysts can see it now."
              : "This report had already arrived, so nothing was sent twice."}
          </p>
          {canSubmit && (
            <Link
              href="/field-reports/new"
              className="text-sm text-steel underline underline-offset-2 hover:text-bone"
            >
              Send another report
            </Link>
          )}
        </div>
      )}

      <section>
        <p className="mb-2 text-sm text-steel">
          {eventTypeLabel(report.event_type)}
          {report.place_name && <span> · {report.place_name}</span>}
        </p>
        <h1 className="display mb-4 text-3xl sm:text-4xl">Field report</h1>
        <p className="max-w-3xl whitespace-pre-wrap text-lg leading-relaxed">{report.text}</p>
      </section>

      {/* Field workers do not see integrity flags: they are prompts for reviewers,
          and showing them to submitters teaches how to avoid them. */}
      {reviewer && report.integrity_flags.length > 0 && (
        <section aria-labelledby="flags" className="border-t border-line pt-6">
          <h2 id="flags" className="display mb-4 text-2xl">
            Look closer
          </h2>
          <ul className="flex max-w-3xl flex-col gap-4">
            {report.integrity_flags.map((f, i) => (
              <li key={`${f.code}-${i}`} className="border-l-2 border-signal pl-3">
                <p className="font-semibold">{flagLabel(f.code)}</p>
                <p className="text-sm">{linkReports(f.detail)}</p>
                {FLAG_INFO[f.code] && (
                  <p className="mt-1 text-sm text-steel">{FLAG_INFO[f.code].meaning}</p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section aria-labelledby="details" className="border-t border-line pt-6">
        <h2 id="details" className="display mb-4 text-2xl">
          Details
        </h2>
        <dl className="grid max-w-3xl grid-cols-[9rem_1fr] gap-x-4 gap-y-2 text-sm sm:grid-cols-[11rem_1fr]">
          <dt className="text-steel">Seen at</dt>
          <dd>{formatDhaka(report.observed_at)}</dd>
          <dt className="text-steel">Received</dt>
          <dd>{formatDhaka(report.received_at)}</dd>
          <dt className="text-steel">Reported by</dt>
          <dd>{report.reporter.full_name}</dd>
          <dt className="text-steel">Location</dt>
          <dd>
            {formatCoords(report.latitude, report.longitude)}
            {report.location_accuracy_m !== null && (
              <span className="text-steel"> (±{Math.round(report.location_accuracy_m)} m)</span>
            )}
            <a
              href={mapUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="ml-3 text-steel underline underline-offset-2 hover:text-bone"
            >
              Open map
            </a>
          </dd>
          <dt className="text-steel">Status</dt>
          <dd className="capitalize">{report.status}</dd>
        </dl>
      </section>

      <section aria-labelledby="photos" className="border-t border-line pt-6">
        <h2 id="photos" className="display mb-4 text-2xl">
          Photos
        </h2>
        {report.media.length === 0 ? (
          <p className="text-sm text-steel">No photos with this report.</p>
        ) : (
          <ul className="grid gap-4 sm:grid-cols-2">
            {report.media.map((m) => {
              const src = `/field-reports/${report.id}/photos/${m.id}`;
              return (
                <li key={m.id} className="flex flex-col gap-2">
                  <a href={src} target="_blank" rel="noopener" title="Open full size">
                    {/* Authenticated, uncached photo: next/image would cache it. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={`Photo ${m.position + 1} from this report`}
                      width={m.width}
                      height={m.height}
                      loading="lazy"
                      className="h-auto w-full rounded-sm border border-line bg-panel"
                    />
                  </a>
                  <p className="text-xs text-steel">
                    {m.width} × {m.height} · {formatBytes(m.size_bytes)}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      <section aria-labelledby="integrity" className="border-t border-line pt-6">
        <h2 id="integrity" className="display mb-2 text-2xl">
          Fingerprint
        </h2>
        <p className="mb-4 max-w-3xl text-sm text-steel">
          Taken when the report arrived, over its text, location, time and every photo. If anything
          is edited later, it no longer matches.
        </p>
        <p className="mb-5 font-mono text-xs break-all text-steel">{report.content_hash}</p>
        {reviewer && <VerifyPanel reportId={report.id} />}
      </section>
    </div>
  );
}
