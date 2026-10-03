import { ArrowRight, type LucideIcon } from "lucide-react";
import Link from "next/link";

/** Banner scenes drawn from Bangladesh (public/art, built by scripts/build-art.py). */
export type Scene = "sundarbans" | "paddy" | "hills" | "padma";

/**
 * The banner that opens every ordinary page: a Bangladeshi scene behind, darkened on
 * the left where the icon, title, purpose and main action sit.
 */
export function PageBand({
  title,
  description,
  back,
  actions,
  kicker,
  children,
  scene = "hills",
  icon: Icon,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  back?: { href: string; label: string };
  actions?: React.ReactNode;
  kicker?: React.ReactNode;
  children?: React.ReactNode;
  scene?: Scene;
  icon?: LucideIcon;
}) {
  return (
    <header className="relative isolate overflow-hidden bg-night text-white">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={`/art/${scene}.svg`}
        alt=""
        aria-hidden="true"
        className="absolute inset-0 -z-10 h-full w-full object-cover object-[70%_60%]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-gradient-to-r from-night/95 via-night/70 to-night/10"
      />
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-5 px-4 py-7 sm:flex-row sm:items-center sm:justify-between md:px-8 md:py-9">
        <div className="flex min-w-0 items-start gap-5">
          {Icon && (
            <span className="hidden h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-forest-2 shadow-lg shadow-black/30 sm:flex">
              <Icon size={30} strokeWidth={1.7} aria-hidden="true" />
            </span>
          )}
          <div className="min-w-0">
            {back && (
              <Link
                href={back.href}
                className="mb-2 inline-block text-sm text-forest-ink hover:text-white"
              >
                ← {back.label}
              </Link>
            )}
            {kicker && <div className="mb-1 text-sm text-forest-ink">{kicker}</div>}
            <h1 className="display text-2xl drop-shadow sm:text-[32px]">{title}</h1>
            {description && (
              <p className="mt-1.5 max-w-xl text-[15px] text-night-ink/90 drop-shadow">
                {description}
              </p>
            )}
            {children && <div className="mt-3">{children}</div>}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
    </header>
  );
}

/** The page's working area, under the banner. */
export function PageBody({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-6 md:px-8">{children}</div>
  );
}

/** Kept for pages that do not pass a scene. */
export function PageHeader(props: Parameters<typeof PageBand>[0]) {
  return <PageBand {...props} />;
}

/** A raised surface grouping one subject. */
export function Panel({
  title,
  description,
  children,
  id,
  actions,
  tone,
  flush,
  icon: Icon,
}: {
  title?: React.ReactNode;
  description?: React.ReactNode;
  children: React.ReactNode;
  id?: string;
  actions?: React.ReactNode;
  tone?: "critical";
  flush?: boolean;
  icon?: LucideIcon;
}) {
  return (
    <section
      aria-labelledby={title && id ? id : undefined}
      className={`overflow-hidden rounded-xl border bg-panel shadow-sm ${
        tone === "critical" ? "border-critical/40" : "border-line"
      }`}
    >
      {title && (
        <div className="flex flex-wrap items-start justify-between gap-2 border-b border-line px-4 py-3.5 md:px-5">
          <div className="flex items-start gap-3">
            {Icon && (
              <span
                className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                  tone === "critical"
                    ? "bg-critical-soft text-critical"
                    : "bg-brand-soft text-brand"
                }`}
              >
                <Icon size={17} strokeWidth={1.9} aria-hidden="true" />
              </span>
            )}
            <div>
              <h2 id={id} className="display text-lg">
                {title}
              </h2>
              {description && <p className="mt-0.5 text-sm text-muted">{description}</p>}
            </div>
          </div>
          {actions}
        </div>
      )}
      <div className={flush ? "" : "px-4 py-4 md:px-5"}>{children}</div>
    </section>
  );
}

const TONES = {
  green: {
    icon: "bg-brand-soft text-brand",
    tint: "from-brand-soft/60",
    label: "text-ink",
    arrow: "bg-brand-soft text-brand",
  },
  red: {
    icon: "bg-critical-soft text-critical",
    tint: "from-critical-soft/80",
    label: "text-critical",
    arrow: "bg-critical-soft text-critical",
  },
  amber: {
    icon: "bg-alert-soft text-alert",
    tint: "from-alert-soft/80",
    label: "text-ink",
    arrow: "bg-alert-soft text-alert",
  },
  blue: {
    icon: "bg-medium-soft text-medium",
    tint: "from-medium-soft/70",
    label: "text-ink",
    arrow: "bg-medium-soft text-medium",
  },
  forest: {
    icon: "bg-brand-soft text-brand",
    tint: "from-brand-soft/60",
    label: "text-ink",
    arrow: "bg-brand-soft text-brand",
  },
} as const;

/** One figure that matters: icon, number, label, a line of context, and where it leads. */
export function StatTile({
  value,
  label,
  note,
  tone = "green",
  href,
  icon: Icon,
}: {
  value: React.ReactNode;
  label: string;
  note?: string;
  tone?: keyof typeof TONES;
  href?: string;
  icon?: LucideIcon;
}) {
  const t = TONES[tone];
  const body = (
    <>
      {Icon && (
        <span
          className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full ${t.icon}`}
        >
          <Icon size={23} strokeWidth={1.9} aria-hidden="true" />
        </span>
      )}
      <span className="min-w-0 flex-1">
        <span
          className={`block text-[28px] leading-none font-bold ${tone === "red" ? "text-critical" : "text-ink"}`}
        >
          {value}
        </span>
        <span className={`mt-1 block font-semibold ${t.label}`}>{label}</span>
        {note && <span className="block text-sm text-muted">{note}</span>}
      </span>
      {href && (
        <span
          aria-hidden="true"
          className={`flex h-8 w-8 shrink-0 items-center justify-center self-center rounded-full ${t.arrow}`}
        >
          <ArrowRight size={16} strokeWidth={2.2} />
        </span>
      )}
    </>
  );
  const cls = `flex items-start gap-4 rounded-xl border border-line bg-gradient-to-br ${t.tint} to-panel to-60% px-4 py-4 shadow-sm`;
  return href ? (
    <Link href={href} className={`${cls} transition-shadow hover:shadow-md`}>
      {body}
    </Link>
  ) : (
    <div className={cls}>{body}</div>
  );
}

export function StatTiles({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">{children}</div>;
}

/** Tabs that are links (?tab=…), so every tab has its own address. */
export function Tabs({
  items,
  active,
}: {
  items: { key: string; label: string; href: string; count?: number; icon?: LucideIcon }[];
  active: string;
}) {
  return (
    <nav
      aria-label="Sections"
      className="flex gap-1 overflow-x-auto rounded-xl border border-line bg-panel p-1 shadow-sm"
    >
      {items.map((t) => {
        const on = t.key === active;
        const Icon = t.icon;
        return (
          <Link
            key={t.key}
            href={t.href}
            aria-current={on ? "page" : undefined}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 whitespace-nowrap transition-colors ${
              on
                ? "bg-forest-2 font-semibold text-white"
                : "text-muted hover:bg-panel-2 hover:text-ink"
            }`}
          >
            {Icon && <Icon size={16} strokeWidth={1.9} aria-hidden="true" />}
            {t.label}
            {t.count !== undefined && (
              <span
                className={`rounded-full px-2 py-0.5 text-xs font-bold ${
                  on ? "bg-white/20 text-white" : "bg-panel-2 text-muted"
                }`}
              >
                {t.count}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export const buttonPrimary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 font-semibold text-white shadow-sm transition-colors hover:bg-brand-strong disabled:cursor-wait disabled:opacity-60";
/** Secondary action: red outline. */
export const buttonSecondary =
  "inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-red bg-panel px-4 font-semibold text-red shadow-sm transition-colors hover:bg-red-soft disabled:cursor-wait disabled:opacity-60";
/** Quiet action: grey outline (cancel, less important). */
export const buttonQuiet =
  "inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line bg-panel px-4 text-ink shadow-sm transition-colors hover:border-muted disabled:cursor-wait disabled:opacity-60";
/** Main action on a banner. */
export const buttonOnBand =
  "inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-forest-2 px-5 font-semibold text-white shadow-lg shadow-black/30 ring-1 ring-white/15 transition-colors hover:bg-[#1f9a50]";
