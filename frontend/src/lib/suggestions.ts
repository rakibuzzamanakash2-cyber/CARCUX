import { isUuid } from "@/lib/format";
import type { CandidateEvent, SuggestionUsed } from "@/lib/types";

/** Keep a suggestion reference only if it is well formed (it goes to the audit log). */
export function cleanSuggestion(s?: SuggestionUsed): { suggestion?: SuggestionUsed } {
  if (!s) return {};
  const rankOk = Number.isInteger(s.rank) && s.rank >= 1 && s.rank <= 50;
  const methodOk = s.method === "rule" || s.method === "model";
  const scoreOk = s.score === null || (typeof s.score === "number" && s.score >= 0 && s.score <= 1);
  const modelOk = s.model_id === null || isUuid(s.model_id);
  return rankOk && methodOk && scoreOk && modelOk
    ? { suggestion: { rank: s.rank, method: s.method, score: s.score, model_id: s.model_id } }
    : {};
}

function span(hours: number): string {
  const h = Math.abs(hours);
  if (h < 1) return "under an hour";
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} days`;
}

export function distanceText(km: number | null): string {
  if (km === null) return "place unknown";
  return km < 1 ? `${Math.round(km * 1000)} m away` : `${km.toFixed(1)} km away`;
}

/** Why an event is suggested, as short phrases (the model's reasons, or the rule's). */
export function suggestionReasons(c: CandidateEvent): string[] {
  const out: string[] = [];
  if (c.method === "model") {
    const sim = c.text_similarity ?? 0;
    out.push(
      sim >= 0.5 ? "very similar wording" : sim >= 0.25 ? "similar wording" : "different wording",
    );
    const h = c.hours_from_latest;
    if (h !== null) {
      out.push(
        Math.abs(h) < 1
          ? "same hour as its latest evidence"
          : `${span(h)} ${h > 0 ? "after" : "before"} its latest evidence`,
      );
    }
  } else {
    out.push(c.hours_apart === 0 ? "during the event" : `${c.hours_apart} h outside it`);
  }
  out.push(distanceText(c.distance_km));
  if (c.same_type) out.push("same type");
  return out;
}

/** One line under the "possibly the same situation" heading. */
export function suggestionIntro(method: "rule" | "model", what: "report" | "signal"): string {
  return method === "model"
    ? `Ranked by the suggestion model, trained on your team's links: wording, timing, place and type together. It can be wrong; read the event before linking.`
    : what === "report"
      ? "Open events within 5 km and 48 hours of this report, same type first. Read the event before linking."
      : "Open events whose area and time overlap this signal's, same type first.";
}
