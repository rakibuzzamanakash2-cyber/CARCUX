"use client";

import Link from "next/link";
import { useRef, useState, useTransition } from "react";

import { importList } from "@/app/actions/signals";
import { Pill } from "@/components/data-table";
import { eventTypeLabel } from "@/lib/event-types";
import type { ImportResult } from "@/lib/types";

const btn =
  "inline-flex h-10 items-center justify-center rounded-lg px-4 font-semibold shadow-sm transition-colors disabled:cursor-wait disabled:opacity-60";

const STATUS = {
  add: { label: "Will add", tone: "green" },
  duplicate: { label: "Already in", tone: "grey" },
  error: { label: "Needs fixing", tone: "red" },
} as const;

/** Check the file first (nothing saved), then import what is ready. */
export function ImportForm() {
  const form = useRef<HTMLFormElement>(null);
  const [pending, startTransition] = useTransition();
  const [checked, setChecked] = useState<ImportResult | null>(null);
  const [saved, setSaved] = useState<ImportResult | null>(null);
  const [error, setError] = useState("");

  function run(save: boolean) {
    if (!form.current) return;
    const data = new FormData(form.current);
    setError("");
    startTransition(async () => {
      const outcome = await importList(data, save);
      if (!outcome.ok) {
        setError(outcome.message);
        return;
      }
      if (save) {
        setSaved(outcome.result);
        setChecked(null);
      } else {
        setChecked(outcome.result);
        setSaved(null);
      }
    });
  }

  const result = saved ?? checked;
  return (
    <div className="flex flex-col gap-5" aria-busy={pending}>
      <form
        ref={form}
        onSubmit={(e) => {
          e.preventDefault();
          run(false);
        }}
        className="flex flex-col gap-3"
      >
        <label htmlFor="import-file" className="text-sm font-semibold">
          CSV file
        </label>
        <input
          id="import-file"
          name="file"
          type="file"
          accept=".csv,text/csv"
          required
          onChange={() => {
            setChecked(null);
            setSaved(null);
          }}
          className="rounded-md border border-line bg-panel p-2 text-sm file:mr-3 file:rounded-md file:border-0 file:bg-brand-soft file:px-3 file:py-1.5 file:font-semibold file:text-brand"
        />
        <div className="flex flex-wrap gap-2">
          <button
            type="submit"
            disabled={pending}
            className={`${btn} border border-brand bg-panel text-brand hover:bg-brand-soft`}
          >
            {pending && !checked ? "Checking…" : "Check the file"}
          </button>
          {checked && checked.added > 0 && (
            <button
              type="button"
              disabled={pending}
              onClick={() => run(true)}
              className={`${btn} bg-brand text-white hover:bg-brand-strong`}
            >
              {pending
                ? "Importing…"
                : `Import ${checked.added} ${checked.added === 1 ? "item" : "items"}`}
            </button>
          )}
        </div>
      </form>

      {error && (
        <p
          role="alert"
          className="rounded-md border border-critical/60 bg-critical-soft px-3 py-2 text-sm"
        >
          {error}
        </p>
      )}

      {result && (
        <div className="flex flex-col gap-3">
          <p role="status" className="rounded-md bg-panel-2 px-3 py-2 text-sm">
            {saved ? (
              <>
                Imported {saved.added} {saved.added === 1 ? "item" : "items"}.{" "}
                <Link
                  href="/signals?status=new"
                  className="font-semibold text-brand hover:underline"
                >
                  See them under Public signals
                </Link>
              </>
            ) : (
              <>
                Checked: {result.added} ready, {result.duplicates} already in CARCUX,{" "}
                {result.errors} to fix. Nothing has been saved yet.
              </>
            )}
            {result.new_publishers.length > 0 && (
              <span className="block text-muted">
                New publishers {saved ? "added" : "to be added"}: {result.new_publishers.join(", ")}
              </span>
            )}
          </p>
          <div className="overflow-x-auto rounded-lg border border-line">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Rows in the file</caption>
              <thead className="bg-panel-2 text-muted">
                <tr>
                  <th scope="col" className="px-3 py-2">
                    Line
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Status
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Headline
                  </th>
                  <th scope="col" className="px-3 py-2">
                    Type and place
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {result.rows.map((r) => (
                  <tr key={r.line} className="align-top">
                    <td className="px-3 py-2 text-muted">{r.line}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      <Pill tone={STATUS[r.status].tone}>{STATUS[r.status].label}</Pill>
                    </td>
                    <td className="px-3 py-2">
                      {r.title || <span className="text-muted">No headline</span>}
                      {r.message && r.status !== "add" && (
                        <span
                          className={`block ${r.status === "error" ? "text-critical" : "text-muted"}`}
                        >
                          {r.message}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-muted">
                      {r.event_type ? eventTypeLabel(r.event_type) : ""}
                      {r.place ? `, ${r.place}` : r.event_type ? ", not placed" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
