import { ClipboardList } from "lucide-react";
import { randomUUID } from "node:crypto";

import { PageBand, PageBody } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { eventTypeLabel } from "@/lib/event-types";
import { dhakaNowLocalInput, isUuid } from "@/lib/format";
import { REPORT_SUBMITTERS, type RequestForWorkers } from "@/lib/types";

import { ReportForm } from "./report-form";

export const metadata = { title: "New field report" };

export default async function NewReportPage({
  searchParams,
}: {
  searchParams: Promise<{ request?: string }>;
}) {
  await requireRole(...REPORT_SUBMITTERS);
  const { request: requestId } = await searchParams;
  // Answering an analyst's request: show what was asked. A closed or unknown request
  // is left out, and the report is sent as an ordinary one.
  let request: RequestForWorkers | null = null;
  let requestGone = false;
  if (requestId && isUuid(requestId)) {
    try {
      request = await api<RequestForWorkers>(`/evidence-requests/${requestId}/brief`);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
      requestGone = true;
    }
  }

  return (
    <>
      <PageBand
        scene="paddy"
        icon={ClipboardList}
        back={{ href: "/field-reports", label: "Field reports" }}
        title="New field report"
        description="Say what you see, where, and when. Photos help analysts confirm it. If sending fails, press Send again: a report is never stored twice."
      />
      <PageBody>
        <div className="flex max-w-3xl flex-col gap-6">
          {request && (
            <div className="rounded-md border border-water/40 bg-water/5 p-4 text-sm">
              <p className="font-semibold">Answering a request to check</p>
              <p className="mt-1 italic">“{request.question}”</p>
              <p className="mt-1 text-muted">
                {eventTypeLabel(request.event_type)}
                {request.place_name ? ` at ${request.place_name}` : ""}. Report what you see
                yourself, including if nothing is happening.
              </p>
            </div>
          )}
          {requestGone && (
            <p className="rounded-md border border-line bg-panel-2 p-3 text-sm">
              That request has been closed. You can still send a report; it will be an ordinary one.
            </p>
          )}
          {/* A fresh id per page load. Retrying with the same id is safe (the backend
          returns the original), which is what makes resending after a dropped
          connection harmless. */}
          <ReportForm
            clientReportId={randomUUID()}
            defaultObservedAt={dhakaNowLocalInput()}
            requestId={request?.id}
          />
        </div>
      </PageBody>
    </>
  );
}
