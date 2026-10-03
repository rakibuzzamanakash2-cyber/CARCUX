import Link from "next/link";

/**
 * The green band that opens every ordinary page: way back, kicker, title, one line
 * of purpose, actions, and optional chips. A red rule closes it, like the header.
 */
export function PageBand({
  title,
  description,
  back,
  actions,
  kicker,
  children,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  kicker?: React.ReactNode;
  children?: React.ReactNode;
}) {
  return (
    <header className="border-b-[3px] border-red bg-gradient-to-r from-forest to-[#11553a] text-white">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6 sm:flex-row sm:items-end sm:justify-between md:px-8 md:py-7">
        <div className="min-w-0">
          {back && (
            <Link
              href={back.href}
              className="mb-3 inline-block text-sm text-forest-ink hover:text-white"
            >
              ← {back.label}
            </Link>
          )}
          {kicker && <div className="mb-1 text-sm text-forest-ink">{kicker}</div>}
          <h1 className="display text-2xl sm:text-[28px]">{title}</h1>
          {description && <p className="mt-1.5 max-w-2xl text-forest-ink">{description}</p>}
          {children && <div className="mt-3">{children}</div>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** The page's working area, under the band. */
export function PageBody({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 md:px-8">{children}</div>
  );
}

/** Kept for pages that do not need a band. */
export function PageHeader(props: Parameters<typeof PageBand>[0]) {
  return <PageBand {...props} />;
}

/** A raised surface grouping one subject; its title carries a short red underline. */
export function Panel({
  title,
  description,
  children,
  id,
  actions,
  tone,
  flush,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
  actions?: React.ReactNode;
  tone?: "critical";
  flush?: boolean;
}) {
  return (
    <section
      aria-labelledby={title && id ? id : undefined}
      className={`overflow-hidden rounded-lg border bg-panel shadow-sm ${
        tone === "critical" ? "border-critical/50" : "border-line"
      }`}
    >
      {title && (
        <div className="flex flex-wrap items-start justify-between gap-2 px-4 pt-4 md:px-5">
          <div>
            <h2 id={id} className="display text-lg">
              {title}
            </h2>
            <span aria-hidden="true" className="mt-1 block h-0.5 w-7 rounded bg-red" />
            {description && <p className="mt-2 text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className={flush ? "mt-3" : "px-4 py-4 md:px-5"}>{children}</div>
    </section>
  );
}

/** One figure that matters, with a coloured top edge. */
export function StatTile({
  value,
  label,
  note,
  tone = "green",
  href,
}: {
  value: React.ReactNode;
  label: string;
  note?: string;
  tone?: "green" | "red" | "amber" | "forest";
  href?: string;
}) {
  const edge = {
    green: "border-t-brand",
    red: "border-t-red",
    amber: "border-t-alert",
    forest: "border-t-forest",
  }[tone];
  const figure = { green: "text-brand", red: "text-red", amber: "text-alert", forest: "text-ink" }[
    tone
  ];
  const body = (
    <>
      <span className={`block text-3xl font-bold ${figure}`}>{value}</span>
      <span className="block font-semibold">{label}</span>
      {note && <span className="block text-sm text-muted">{note}</span>}
    </>
  );
  const cls = `block rounded-lg border border-line border-t-[3px] ${edge} bg-panel px-4 py-3 shadow-sm`;
  return href ? (
    <a href={href} className={`${cls} transition-shadow hover:shadow-md`}>
      {body}
    </a>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function StatTiles({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>;
}

/** Tabs that are links (?tab=…), so every tab has its own address. */
export function Tabs({
  items,
  active,
}: {
  items: { key: string; label: string; href: string; count?: number }[];
  active: string;
}) {
  return (
    <nav aria-label="Sections" className="flex gap-1 overflow-x-auto border-b border-line">
      {items.map((t) => {
        const on = t.key === active;
        return (
          <a
            key={t.key}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 whitespace-nowrap transition-colors ${
              on
                ? "border-red font-semibold text-ink"
                : "border-transparent text-muted hover:text-ink"
            }`}
          >
            {t.label}
            {t.count !== undefined && (
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                  on ? "bg-red-soft text-red" : "bg-panel-2 text-muted"
                }`}
              >
                {t.count}
              </span>
            )}
          </a>
        );
      })}
    </nav>
  );
}

export const buttonPrimary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md bg-brand px-4 font-semibold text-white shadow-sm transition-colors hover:bg-brand-strong disabled:cursor-wait disabled:opacity-60";
/** Secondary action: red outline. */
export const buttonSecondary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-red bg-panel px-4 font-semibold text-red shadow-sm transition-colors hover:bg-red-soft disabled:cursor-wait disabled:opacity-60";
/** Quiet action: grey outline (cancel, less important). */
export const buttonQuiet =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-panel px-4 text-ink shadow-sm transition-colors hover:border-muted disabled:cursor-wait disabled:opacity-60";
/** Main action placed on a green band. */
export const buttonOnBand =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md bg-white px-4 font-semibold text-forest shadow-sm transition-colors hover:bg-brand-soft";
