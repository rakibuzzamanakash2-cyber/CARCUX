import { Sparkles } from "lucide-react";

import { relationLabel } from "@/lib/events";
import type { EvidenceRelation, StanceSuggestion } from "@/lib/types";

const STRENGTH: Record<StanceSuggestion["strength"], string> = {
  strong: "clear sign",
  medium: "likely",
  weak: "a guess: read it",
};

/** How CARCUX reads an item against an event. A suggestion only; the analyst decides.
 * With `labelled`, shown only when the analyst's label differs (a prompt to look again). */
export function StanceNote({
  stance,
  labelled,
}: {
  stance: StanceSuggestion | null | undefined;
  labelled?: EvidenceRelation;
}) {
  if (!stance) return null;
  if (labelled !== undefined && stance.relation === labelled) return null;
  return (
    <p
      className="flex items-start gap-1.5 text-sm"
      data-testid="stance-note"
      data-relation={stance.relation}
    >
      <Sparkles size={14} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
      <span>
        <span className="text-muted">
          {labelled !== undefined ? "CARCUX reads it differently: " : "CARCUX reads it as: "}
        </span>
        <span className="font-semibold">{relationLabel(stance.relation)}</span>
        <span className="text-muted">
          {" "}
          ({STRENGTH[stance.strength]}) · {stance.reasons.join("; ")}
        </span>
      </span>
    </p>
  );
}
