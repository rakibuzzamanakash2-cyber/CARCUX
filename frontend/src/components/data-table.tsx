/** Table chrome shared by list pages. Columns are the page's own <th>/<td>. */
export function DataTable({
  head,
  children,
  empty,
}: {
  head: React.ReactNode;
  children: React.ReactNode;
  empty?: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-panel shadow-sm">
      {empty ?? (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-line bg-panel-2 text-xs font-semibold text-muted">
              {head}
            </thead>
            <tbody className="divide-y divide-line">{children}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export const th = "px-4 py-2.5 font-semibold";
export const td = "px-4 py-3 align-top";
/** Columns that only fit from tablet width up. */
export const wide = "hidden md:table-cell";

/** A whole-row link: the first cell holds the real <a>; this makes the row look clickable. */
export const rowCls = "transition-colors hover:bg-brand-soft/40";

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-10 text-center text-muted">{children}</p>;
}
