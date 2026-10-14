import { AlertTriangle, Database, Download, FileCheck2, Link2, ListChecks } from "lucide-react";
import Link from "next/link";

import { PageBand, PageBody, Panel, StatTile, StatTiles } from "@/components/page-header";
import { AssessmentModelControls } from "@/components/assessment-model-controls";
import { SuggestionModelControls } from "@/components/suggestion-model-controls";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import {
  REPORT_REVIEWERS,
  type DatasetProblem,
  type DatasetSummary,
  type AssessmentStatus,
  type SuggestionStatus,
} from "@/lib/types";

function pct(x?: number): string {
  return x === undefined ? "–" : `${Math.round(x * 100)}%`;
}

export const metadata = { title: "Dataset" };

const FILES: { name: string; label: string }[] = [
  { name: "events.jsonl", label: "Events" },
  { name: "observations.jsonl", label: "Observations (reports and signals)" },
  { name: "relations.jsonl", label: "Relations (links with labels)" },
  { name: "dependences.jsonl", label: "Dependences (copies)" },
  { name: "sources.jsonl", label: "Sources" },
];

const FIX: Record<DatasetProblem["kind"], { title: string; how: string }> = {
  needs_ground_truth: {
    title: "Events without ground truth",
    how: "Open the event, and under Ground truth say whether it happened and add a source published afterwards.",
  },
  needs_conflicts: {
    title: "Partly supporting links that do not say what is wrong",
    how: "Open the event's Evidence tab and choose what the item gets wrong.",
  },
  contradiction: {
    title: "Verified, but did not happen",
    how: "The assessment and the ground truth disagree: change one of them.",
  },
  outside_bangladesh: {
    title: "Events placed outside Bangladesh",
    how: "Correct the event's location.",
  },
};

export default async function DatasetPage() {
  const user = await requireRole(...REPORT_REVIEWERS);
  const admin = user.role === "admin";
  const [data, suggestions, assessing] = await Promise.all([
    api<DatasetSummary>("/dataset/summary"),
    api<SuggestionStatus>("/suggestions/model"),
    api<AssessmentStatus>("/assessment/model"),
  ]);
  const assessModel = assessing.active;
  const canTrainAssessment =
    assessing.resolved_events >= assessing.min_events &&
    assessing.resolved_happened >= assessing.min_each &&
    assessing.resolved_events - assessing.resolved_happened >= assessing.min_each;
  const model = suggestions.active;
  const canTrain =
    suggestions.labelled_items >= suggestions.min_items &&
    suggestions.labelled_events >= suggestions.min_events;
  const c = data.counts;
  const byKind = new Map<string, DatasetProblem[]>();
  for (const p of data.problems) byKind.set(p.kind, [...(byKind.get(p.kind) ?? []), p]);

  return (
    <>
      <PageBand
        scene="hills"
        icon={Database}
        title="Dataset"
        description="What CARCUX's records add to the CARCUX-BD research dataset, and what still needs an analyst before it can go in."
      />
      <PageBody>
        <StatTiles>
          <StatTile
            icon={FileCheck2}
            value={`${c["events.jsonl"] ?? 0} of ${data.events_total}`}
            label="Events ready"
            note="With ground truth recorded"
            tone="green"
          />
          <StatTile
            icon={ListChecks}
            value={c["observations.jsonl"] ?? 0}
            label="Observations"
            note="Reports and signals linked to them"
            tone="blue"
          />
          <StatTile
            icon={Link2}
            value={c["relations.jsonl"] ?? 0}
            label="Labelled links"
            note="Stance, conflicts, confidence"
            tone="forest"
          />
          <StatTile
            icon={AlertTriangle}
            value={data.problems.length}
            label="Need work"
            note="Left out until fixed"
            tone={data.problems.length ? "amber" : "green"}
          />
        </StatTiles>

        <div className="grid gap-6 lg:grid-cols-[1fr_24rem] lg:items-start">
          <div className="flex min-w-0 flex-col gap-6">
            {data.problems.length === 0 ? (
              <Panel title="Nothing to fix">
                <p className="text-muted">Every event and link can go into the dataset.</p>
              </Panel>
            ) : (
              [...byKind.entries()].map(([kind, items]) => {
                const fix = FIX[kind as DatasetProblem["kind"]];
                return (
                  <Panel
                    key={kind}
                    id={`fix-${kind}`}
                    title={`${fix?.title ?? kind} (${data.problems_by_kind[kind] ?? items.length})`}
                    description={fix?.how}
                  >
                    <ul className="flex flex-col divide-y divide-line">
                      {items.map((p, i) => (
                        <li key={`${p.event_id}-${p.evidence_id}-${i}`} className="py-2.5">
                          {p.event_id ? (
                            <Link
                              href={`/events/${p.event_id}${p.kind === "needs_conflicts" ? "?tab=evidence" : ""}`}
                              className="font-semibold text-brand hover:underline"
                            >
                              {p.event_title ?? "Event"}
                            </Link>
                          ) : (
                            <span>{p.message}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </Panel>
                );
              })
            )}
          </div>

          <div className="flex flex-col gap-6">
            <Panel
              title="Export"
              description={`Schema v${data.schema_version}, annotation guideline ${data.guideline_version}.`}
            >
              <dl className="mb-4 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-sm">
                {FILES.map((f) => (
                  <div key={f.name} className="contents">
                    <dt className="text-muted">{f.label}</dt>
                    <dd className="text-right font-semibold">{c[f.name] ?? 0}</dd>
                  </div>
                ))}
              </dl>
              {admin ? (
                <div className="flex flex-col gap-2">
                  <a
                    href="/dataset/download"
                    className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 font-semibold text-white hover:bg-brand-strong"
                  >
                    <Download size={17} aria-hidden="true" />
                    Download dataset (zip)
                  </a>
                  <a
                    href="/dataset/download?all=1"
                    className="text-center text-sm font-semibold text-brand hover:underline"
                  >
                    Include unlinked reports and signals
                  </a>
                </div>
              ) : (
                <p className="text-sm text-muted">An admin can download the dataset.</p>
              )}
            </Panel>
            <Panel
              id="suggestions"
              title="Event suggestions"
              description="How reports and signals are matched to existing events on the report, signal and review pages."
            >
              <p className="mb-3 text-sm">
                {model ? (
                  <>
                    Ranked by the <strong>suggestion model</strong>, trained{" "}
                    {formatDhaka(model.created_at)} on {model.items} linked reports and signals
                    across {model.events} events.
                  </>
                ) : (
                  <>
                    Ranked by the <strong>5 km / 48 hour rule</strong>, same type first. Train a
                    model to rank by wording, timing, place and type together.
                  </>
                )}
              </p>
              {model && model.metrics.model_top1 !== undefined && (
                <dl className="mb-3 grid grid-cols-[1fr_auto_auto] gap-x-3 gap-y-1.5 text-sm">
                  <dt className="text-muted">On held-out events</dt>
                  <dd className="text-right font-semibold">Model</dd>
                  <dd className="text-right font-semibold">Rule</dd>
                  <dt className="text-muted">First suggestion right</dt>
                  <dd className="text-right">{pct(model.metrics.model_top1)}</dd>
                  <dd className="text-right">{pct(model.metrics.rule_top1)}</dd>
                  <dt className="text-muted">Right one in the first three</dt>
                  <dd className="text-right">{pct(model.metrics.model_top3)}</dd>
                  <dd className="text-right">{pct(model.metrics.rule_top3)}</dd>
                </dl>
              )}
              {model && model.metrics.model_top1 !== undefined && (
                <p className="mb-3 text-xs text-muted">
                  Measured on {model.metrics.held_out_items} items from{" "}
                  {model.metrics.held_out_events} events the model did not learn from.
                </p>
              )}
              {model && model.metrics.model_top1 === undefined && (
                <p className="mb-3 text-sm text-muted">
                  Too few held-out events to measure it yet. Retrain when there are more links.
                </p>
              )}
              <p className="mb-3 text-sm text-muted">
                {suggestions.labelled_items} linked reports and signals across{" "}
                {suggestions.labelled_events} events
                {canTrain
                  ? "."
                  : `; training needs at least ${suggestions.min_items} across ${suggestions.min_events}.`}
                {suggestions.from_suggestions.total > 0 &&
                  ` ${suggestions.from_suggestions.total} links were made from suggestions, ${suggestions.from_suggestions.first} of them from the first one.`}
              </p>
              {admin ? (
                <SuggestionModelControls active={model !== null} canTrain={canTrain} />
              ) : (
                <p className="text-sm text-muted">An admin can train the model.</p>
              )}
            </Panel>
            <Panel
              id="assessment-suggestions"
              title="Assessment suggestions"
              description="How the suggested assessment on each event's page is worked out."
            >
              <p className="mb-3 text-sm">
                {assessModel ? (
                  <>
                    From the <strong>assessment model</strong>, trained{" "}
                    {formatDhaka(assessModel.created_at)} on {assessModel.events} events with ground
                    truth ({assessModel.happened} happened): each source weighed by its own record.
                  </>
                ) : (
                  <>
                    From <strong>starting assumptions</strong>: field workers right{" "}
                    {pct(assessing.starting_rates.field)} of the time, public records{" "}
                    {pct(assessing.starting_rates.public_record)}, news{" "}
                    {pct(assessing.starting_rates.news)}, others{" "}
                    {pct(assessing.starting_rates.other)}. Train a model to learn each source&apos;s
                    own record.
                  </>
                )}
              </p>
              {assessModel && assessModel.metrics.model_brier !== undefined && (
                <>
                  <dl className="mb-2 grid grid-cols-[1fr_auto] gap-x-3 gap-y-1.5 text-sm">
                    <dt className="text-muted">Brier score on held-out events (lower is better)</dt>
                    <dd />
                    <dt className="pl-3 text-muted">Model</dt>
                    <dd className="text-right font-semibold">
                      {assessModel.metrics.model_brier.toFixed(3)}
                    </dd>
                    <dt className="pl-3 text-muted">Starting assumptions</dt>
                    <dd className="text-right">{assessModel.metrics.start_brier?.toFixed(3)}</dd>
                    <dt className="pl-3 text-muted">Majority vote</dt>
                    <dd className="text-right">{assessModel.metrics.majority_brier?.toFixed(3)}</dd>
                  </dl>
                  <p className="mb-3 text-xs text-muted">
                    Measured on {assessModel.metrics.held_out_events} events the model did not learn
                    from.
                  </p>
                </>
              )}
              {assessModel && assessModel.metrics.model_brier === undefined && (
                <p className="mb-3 text-sm text-muted">
                  Too few held-out events to measure it yet. Retrain when more events have ground
                  truth.
                </p>
              )}
              <p className="mb-3 text-sm text-muted">
                {assessing.resolved_events} events with ground truth and linked evidence (
                {assessing.resolved_happened} happened)
                {canTrainAssessment
                  ? "."
                  : `; training needs at least ${assessing.min_events}, with ${assessing.min_each} that happened and ${assessing.min_each} that did not.`}
                {assessing.from_suggestions.total > 0 &&
                  ` ${assessing.from_suggestions.total} assessments were set with a suggestion in view; ${assessing.from_suggestions.followed} followed it.`}
              </p>
              {admin ? (
                <AssessmentModelControls
                  active={assessModel !== null}
                  canTrain={canTrainAssessment}
                />
              ) : (
                <p className="text-sm text-muted">An admin can train the model.</p>
              )}
            </Panel>
            <Panel title="Before publishing">
              <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
                <li>
                  People appear only as numbers (ANN-001, …) and field workers as “Field worker”.
                  Phone numbers and emails are removed automatically.
                </li>
                <li>
                  Names of private individuals in field reports are not: read them and replace names
                  with [PERSON].
                </li>
                <li>Keep id_map.json private; it links the dataset back to CARCUX.</li>
                <li>
                  Check the files with the validator:{" "}
                  <code className="rounded bg-panel-2 px-1">
                    python -m carcux_data.validate &lt;folder&gt;
                  </code>
                </li>
              </ul>
            </Panel>
          </div>
        </div>
      </PageBody>
    </>
  );
}
