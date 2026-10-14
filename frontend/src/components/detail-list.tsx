import type { Detail } from "@/lib/types";

const LABEL: Record<Detail["attribute"], string> = {
  occurrence: "Denies it happened",
  casualty_count: "Deaths",
  affected_count: "Affected",
  magnitude: "How bad",
  cause: "Cause",
  status: "Situation",
};

const STATUS: Record<string, string> = {
  resolved: "over",
  worsening: "getting worse",
  improving: "getting better",
  ongoing: "still going on",
};

/** A detail's value in words: "3", "500 households", "knee-deep", "over". */
export function detailValue(
  attribute: string,
  value: number | string | boolean,
  unit?: string | null,
): string {
  if (attribute === "occurrence") return value === false ? "says it did not happen" : "yes";
  if (attribute === "status") return STATUS[String(value)] ?? String(value);
  if (attribute === "affected_count")
    return `${Number(value).toLocaleString("en-IN")} ${unit === "households" ? "households" : "people"}`;
  if (typeof value === "number") return value.toLocaleString("en-IN");
  return String(value);
}

export const detailLabel = (attribute: string) =>
  LABEL[attribute as Detail["attribute"]] ?? attribute;

/** Details found automatically in a text, each with the words it came from. */
export function DetailList({ details }: { details: Detail[] }) {
  if (details.length === 0) {
    return (
      <p className="text-sm text-muted">
        No deaths, numbers affected, depth, cause or situation stated clearly in the text.
      </p>
    );
  }
  return (
    <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-2.5 text-sm">
      {details.map((d) => (
        <div key={d.attribute} className="contents">
          <dt className="text-muted">{detailLabel(d.attribute)}</dt>
          <dd>
            <span className="font-semibold">{detailValue(d.attribute, d.value, d.unit)}</span>
            <span className="text-muted"> · “{d.surface}”</span>
          </dd>
        </div>
      ))}
    </dl>
  );
}
