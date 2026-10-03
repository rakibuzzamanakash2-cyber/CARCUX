import { FileDown, FileUp } from "lucide-react";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { requireRole } from "@/lib/dal";
import { REPORT_REVIEWERS } from "@/lib/types";

import { ImportForm } from "./import-form";

export const metadata = { title: "Import a list" };

const COLUMNS: [string, string][] = [
  ["url", "Link to the article (required)"],
  ["title", "Headline, as published (required)"],
  ["published", "Date, e.g. 2024-08-22, or date and time in Dhaka time (required)"],
  ["publisher", "e.g. The Daily Star, Prothom Alo (required)"],
  ["excerpt", "One or two sentences, at most 300 characters"],
  ["event_type", "e.g. flood, cyclone, rail_accident; found from the headline if empty"],
  ["place", "District, upazila or area; found from the headline if empty"],
  ["language", "en, bn, bn-Latn or mixed; guessed if empty"],
  ["severity", "minor, moderate or severe (optional)"],
];

export default async function ImportPage() {
  await requireRole(...REPORT_REVIEWERS);
  return (
    <>
      <PageBand
        scene="padma"
        icon={FileUp}
        back={{ href: "/signals", label: "All signals" }}
        title="Import a list of past news"
        description="For case studies: collect article links from newspaper archives in a spreadsheet, then import them. CARCUX keeps the headline, a short excerpt and the link, as for live news."
      />
      <PageBody>
        <div className="grid gap-6 lg:grid-cols-[1fr_24rem] lg:items-start">
          <Panel title="File">
            <ImportForm />
          </Panel>
          <Panel
            title="Columns"
            description="Save the spreadsheet as CSV UTF-8, with this header row."
          >
            <dl className="flex flex-col gap-2 text-sm">
              {COLUMNS.map(([name, meaning]) => (
                <div key={name}>
                  <dt className="font-mono font-semibold">{name}</dt>
                  <dd className="text-muted">{meaning}</dd>
                </div>
              ))}
            </dl>
            <a
              href="/templates/signals-import.csv"
              download
              className="mt-4 inline-flex items-center gap-1.5 font-semibold text-brand hover:underline"
            >
              <FileDown size={16} aria-hidden="true" />
              Download a template
            </a>
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
