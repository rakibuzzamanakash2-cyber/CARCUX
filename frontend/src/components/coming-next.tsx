import { Construction } from "lucide-react";

import { PageHeader, Panel } from "@/components/page-header";

/** Honest placeholder for sections whose backend does not exist yet. */
export function ComingNext({
  title,
  purpose,
  shows,
  needs,
}: {
  title: string;
  purpose: string;
  shows: string[];
  needs: string;
}) {
  return (
    <div className="max-w-3xl">
      <PageHeader title={title} description={purpose} />
      <Panel>
        <div className="mb-4 flex items-center gap-2 text-alert">
          <Construction size={18} strokeWidth={1.75} aria-hidden="true" />
          <span className="font-semibold">Not built yet</span>
        </div>
        <ul className="mb-4 flex list-disc flex-col gap-2 pl-5">
          {shows.map((s) => (
            <li key={s} className="leading-relaxed">
              {s}
            </li>
          ))}
        </ul>
        <p className="text-sm text-muted">{needs}</p>
      </Panel>
    </div>
  );
}
