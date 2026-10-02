import Link from "next/link";

/** Title row for every ordinary page: optional way back, title, one line of purpose, actions. */
export function PageHeader({
  title,
  description,
  back,
  actions,
  kicker,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  kicker?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {back && (
          <Link href={back.href} className="mb-3 inline-block text-sm text-muted hover:text-ink">
            ← {back.label}
          </Link>
        )}
        {kicker && <div className="mb-1.5 text-sm text-muted">{kicker}</div>}
        <h1 className="display text-3xl sm:text-4xl">{title}</h1>
        {description && <p className="mt-2 max-w-2xl text-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

/** A raised surface grouping one subject. */
export function Panel({
  title,
  description,
  children,
  id,
  actions,
  tone,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
  actions?: React.ReactNode;
  tone?: "critical";
}) {
  return (
    <section
      aria-labelledby={title && id ? id : undefined}
      className={`rounded-lg border bg-panel ${tone === "critical" ? "border-critical/50" : "border-line"}`}
    >
      {title && (
        <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line px-4 py-3 md:px-5">
          <div>
            <h2 id={id} className="display text-xl">
              {title}
            </h2>
            {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="px-4 py-4 md:px-5">{children}</div>
    </section>
  );
}

export const buttonPrimary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md bg-water px-4 font-semibold text-ground transition-colors hover:bg-[#4dbac8] disabled:cursor-wait disabled:opacity-60";
export const buttonSecondary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-md border border-line bg-panel-2 px-4 text-ink transition-colors hover:border-muted disabled:cursor-wait disabled:opacity-60";
