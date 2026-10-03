"use client";

import { useState, useTransition } from "react";

import { verifyReport } from "@/app/actions/field-reports";
import type { VerifyResult } from "@/lib/types";

export function VerifyPanel({ reportId }: { reportId: string }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  function run() {
    startTransition(async () => {
      const outcome = await verifyReport(reportId);
      if (outcome.ok) {
        setResult(outcome.result);
        setError(null);
      } else {
        setResult(null);
        setError(outcome.message);
      }
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-2">
        <button
          type="button"
          onClick={run}
          disabled={pending}
          className="h-11 w-fit rounded-md border border-line bg-panel-2 px-4 text-ink transition-colors hover:bg-panel-2 disabled:cursor-wait disabled:opacity-60"
        >
          {pending ? "Checking…" : result ? "Check again" : "Check it is unchanged"}
        </button>
        <p className="text-sm text-muted">
          Recomputes the fingerprint from the stored text, location and photos. Each check is
          logged.
        </p>
      </div>
      <div role="status" aria-live="polite">
        {result?.intact && (
          <p className="border-l-2 border-ok pl-3 text-sm">
            Unchanged since it was submitted. Text, location, time and every photo match the
            fingerprint.
          </p>
        )}
        {result && !result.intact && (
          <div className="border-l-2 border-critical pl-3 text-sm">
            <p className="mb-1 font-semibold">This report was changed after submission.</p>
            <ul className="list-disc pl-5">
              {result.problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        )}
        {error && <p className="border-l-2 border-critical pl-3 text-sm">{error}</p>}
      </div>
    </div>
  );
}
