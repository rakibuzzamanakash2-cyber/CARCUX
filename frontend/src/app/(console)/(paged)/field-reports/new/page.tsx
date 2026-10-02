import { randomUUID } from "node:crypto";

import { PageHeader } from "@/components/page-header";
import { requireRole } from "@/lib/dal";
import { dhakaNowLocalInput } from "@/lib/format";
import { REPORT_SUBMITTERS } from "@/lib/types";

import { ReportForm } from "./report-form";

export const metadata = { title: "New field report" };

export default async function NewReportPage() {
  await requireRole(...REPORT_SUBMITTERS);

  return (
    <div className="max-w-3xl">
      <PageHeader
        back={{ href: "/field-reports", label: "Field reports" }}
        title="New field report"
        description="Say what you see, where, and when. Photos help analysts confirm it. If sending fails, press Send again: a report is never stored twice."
      />
      {/* A fresh id per page load. Retrying with the same id is safe (the backend
          returns the original), which is what makes resending after a dropped
          connection harmless. */}
      <ReportForm clientReportId={randomUUID()} defaultObservedAt={dhakaNowLocalInput()} />
    </div>
  );
}
