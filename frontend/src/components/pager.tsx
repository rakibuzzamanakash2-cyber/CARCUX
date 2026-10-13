import Link from "next/link";

export function Pager({
  page,
  lastPage,
  total,
  noun,
  newer,
  older,
  labels = ["Newer", "Older"],
}: {
  labels?: [string, string];
  page: number;
  lastPage: number;
  total: number;
  noun: string;
  newer: string | null;
  older: string | null;
}) {
  const cls = "rounded-md border border-line px-3 py-1.5 transition-colors hover:border-muted";
  return (
    <nav aria-label="Pages" className="flex items-center gap-3 text-sm">
      {newer ? (
        <Link href={newer} className={cls}>
          {labels[0]}
        </Link>
      ) : (
        <span className={`${cls} text-muted/40`}>{labels[0]}</span>
      )}
      <span className="text-muted">
        Page {page} of {lastPage}, {total} {noun}
      </span>
      {older ? (
        <Link href={older} className={cls}>
          {labels[1]}
        </Link>
      ) : (
        <span className={`${cls} text-muted/40`}>{labels[1]}</span>
      )}
    </nav>
  );
}
