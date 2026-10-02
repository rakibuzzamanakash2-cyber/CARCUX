import { randomUUID } from "node:crypto";

import { requireRole } from "@/lib/dal";
import { dhakaNowLocalInput } from "@/lib/format";
import { REPORT_SUBMITTERS } from "@/lib/types";

import { ReportForm } from "./report-form";

export const metadata = { title: "New field report" };

export default async function NewReportPage() {
  await requireRole(...REPORT_SUBMITTERS);

  return (
    <div className="flex flex-col gap-8">
      <section>
        <h1 className="display mb-3 text-4xl">New field report</h1>
        <p className="max-w-2xl text-steel">
          Say what you see, where, and when. Photos help analysts confirm it. If the send fails,
          press Send again: the report is never stored twice.
        </p>
      </section>
      {/* A fresh id per page load. Retrying with the same id is safe (the backend
          returns the original), which is what makes resending after a dropped
          connection harmless. */}
      <ReportForm clientReportId={randomUUID()} defaultObservedAt={dhakaNowLocalInput()} />
    </div>
  );
}
