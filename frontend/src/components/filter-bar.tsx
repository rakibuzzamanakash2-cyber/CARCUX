"use client";

import { Search, X } from "lucide-react";
import { useRef } from "react";

export interface FilterSelect {
  name: string;
  label: string;
  value: string;
  options: { value: string; label: string }[];
}

/**
 * A GET form: search box plus dropdowns. Dropdowns apply as soon as they change;
 * the search applies on Enter. Works without JavaScript too (Apply button).
 */
export function FilterBar({
  action,
  search,
  selects,
  hidden = {},
}: {
  action: string;
  search?: { name: string; value: string; placeholder: string };
  selects: FilterSelect[];
  hidden?: Record<string, string>;
}) {
  const form = useRef<HTMLFormElement>(null);
  const active = Boolean(search?.value) || selects.some((s) => s.value);

  return (
    <form
      ref={form}
      action={action}
      method="get"
      role="search"
      className="flex flex-col gap-2 rounded-lg border border-line bg-panel p-2 shadow-sm md:flex-row md:items-center"
    >
      {Object.entries(hidden).map(([k, v]) => (
        <input key={k} type="hidden" name={k} value={v} />
      ))}
      {search && (
        <label className="relative flex-1">
          <span className="sr-only">Search</span>
          <Search
            size={16}
            strokeWidth={2}
            aria-hidden="true"
            className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted"
          />
          <input
            type="search"
            name={search.name}
            defaultValue={search.value}
            placeholder={search.placeholder}
            maxLength={100}
            className="h-10 w-full rounded-md border border-line bg-panel pr-3 pl-9 text-ink placeholder:text-muted/70 focus:border-brand focus:ring-2 focus:ring-brand/15 focus:outline-none"
          />
        </label>
      )}
      {selects.map((s) => (
        <label key={s.name} className="flex items-center gap-2 text-sm">
          <span className="sr-only md:not-sr-only md:text-muted">{s.label}</span>
          <select
            name={s.name}
            defaultValue={s.value}
            onChange={() => form.current?.requestSubmit()}
            className="h-10 w-full rounded-md border border-line bg-panel px-2 text-ink focus:border-brand focus:outline-none md:w-auto"
          >
            {s.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      ))}
      <noscript>
        <button type="submit" className="h-10 rounded-md bg-brand px-4 font-semibold text-white">
          Apply
        </button>
      </noscript>
      {active && (
        <a
          href={action}
          className="inline-flex h-10 items-center gap-1 rounded-md px-3 text-sm text-muted hover:text-red"
        >
          <X size={15} aria-hidden="true" />
          Clear
        </a>
      )}
    </form>
  );
}
