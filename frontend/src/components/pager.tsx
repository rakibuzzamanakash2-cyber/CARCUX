import Link from "next/link";

export function Pager({
  page,
  lastPage,
  total,
  noun,
  newer,
  older,
}: {
  page: number;
  lastPage: number;
  total: number;
  noun: string;
  newer: string | null;
  older: string | null;
}) {
  const cls = "rounded-md border border-line px-3 py-1.5 transition-colors hover:border-muted";
  return (
    <nav aria-label="Pages" className="mt-4 flex items-center gap-3 text-sm">
      {newer ? (
        <Link href={newer} className={cls}>
          Newer
        </Link>
      ) : (
        <span className={`${cls} text-muted/40`}>Newer</span>
      )}
      <span className="text-muted">
        Page {page} of {lastPage}, {total} {noun}
      </span>
      {older ? (
        <Link href={older} className={cls}>
          Older
        </Link>
      ) : (
        <span className={`${cls} text-muted/40`}>Older</span>
      )}
    </nav>
  );
}
