"use client";

import { Flag, Trash2 } from "lucide-react";
import Link from "next/link";
import { useActionState, useState, useTransition } from "react";

import {
  addComment,
  addOpinion,
  deleteComment,
  deleteOpinion,
  reportComment,
  reportOpinion,
} from "@/app/actions/public";
import { FormMessage } from "@/components/form";
import { formatDhaka } from "@/lib/format";
import { REPORT_REASONS, type ActionState, type PublicComment } from "@/lib/types";

type Kind = "comment" | "opinion";

const ACTIONS = {
  comment: { add: addComment, report: reportComment, remove: deleteComment },
  opinion: { add: addOpinion, report: reportOpinion, remove: deleteOpinion },
};

function Comment({ c, signedIn, kind }: { c: PublicComment; signedIn: boolean; kind: Kind }) {
  const { report, remove } = ACTIONS[kind];
  const [pending, startTransition] = useTransition();
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState(REPORT_REASONS[0].value);
  const [result, setResult] = useState<ActionState>();
  return (
    <li
      id={`${kind}-${c.id}`}
      className="scroll-mt-20 rounded-lg bg-panel-2/60 px-3 py-2"
      data-testid={kind}
    >
      <p className="text-sm">
        <span className="font-semibold">{c.author}</span>
        <span className="text-muted"> · {formatDhaka(c.created_at)}</span>
      </p>
      <p className="whitespace-pre-line">{c.body}</p>
      <div className="mt-1 flex flex-wrap items-center gap-3 text-sm">
        {c.mine ? (
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              window.confirm(`Delete your ${kind}?`) &&
              startTransition(async () => setResult(await remove(c.id)))
            }
            className="inline-flex items-center gap-1 text-muted hover:text-ink"
          >
            <Trash2 size={14} aria-hidden="true" /> Delete
          </button>
        ) : (
          signedIn &&
          !reporting && (
            <button
              type="button"
              onClick={() => setReporting(true)}
              className="inline-flex items-center gap-1 text-muted hover:text-ink"
            >
              <Flag size={14} aria-hidden="true" /> Report
            </button>
          )
        )}
        {reporting && (
          <span className="flex flex-wrap items-center gap-2">
            <label className="sr-only" htmlFor={`reason-${c.id}`}>
              Why are you reporting it?
            </label>
            <select
              id={`reason-${c.id}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="h-8 rounded-md border border-line bg-panel px-2"
            >
              {REPORT_REASONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={pending}
              onClick={() =>
                startTransition(async () => {
                  setResult(await report(c.id, reason));
                  setReporting(false);
                })
              }
              className="font-semibold text-brand hover:underline"
            >
              Send report
            </button>
            <button type="button" onClick={() => setReporting(false)} className="text-muted">
              Cancel
            </button>
          </span>
        )}
        {result && (
          <span
            role={result.ok ? "status" : "alert"}
            className={result.ok ? "text-ok" : "text-critical"}
          >
            {result.message}
          </span>
        )}
      </div>
    </li>
  );
}

const TEXT = {
  comment: {
    heading: "Comments",
    note: "People's own views, not checked by CARCUX. Reported comments may be hidden.",
    placeholder: "Write a comment",
    button: "Comment",
    empty: "No comments yet.",
    invite: "to like and comment.",
  },
  opinion: {
    heading: "What people say",
    note: "People's own opinions and what they saw, not verified. CARCUX's analysts may look at them as evidence. Reported opinions may be hidden.",
    placeholder: "What did you see, or what do you think? Say where and when.",
    button: "Post opinion",
    empty: "No opinions yet. Be the first to say what you saw.",
    invite: "to share your opinion.",
  },
};

/** A discussion under a post (comments) or on an incident (opinions). */
export function Discussion({
  id,
  kind,
  items,
  signedIn,
}: {
  id: string;
  kind: Kind;
  items: PublicComment[];
  signedIn: boolean;
}) {
  const t = TEXT[kind];
  const back = kind === "comment" ? `/public/posts/${id}` : `/public/incidents/${id}`;
  const [body, setBody] = useState("");
  const [state, action, pending] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await ACTIONS[kind].add(id, prev, formData);
    if (result?.ok) setBody("");
    return result;
  }, undefined);
  const sectionId = kind === "comment" ? "comments" : "opinions";
  return (
    <section id={sectionId} aria-labelledby={`${sectionId}-h`} className="flex flex-col gap-3">
      <h2 id={`${sectionId}-h`} className="text-lg font-semibold">
        {t.heading} <span className="text-muted">({items.length})</span>
      </h2>
      <p className="text-sm text-muted">{t.note}</p>
      {signedIn ? (
        <form action={action} className="flex flex-col gap-2">
          <label htmlFor={`${sectionId}-body`} className="sr-only">
            {kind === "comment" ? "Your comment" : "Your opinion"}
          </label>
          <textarea
            id={`${sectionId}-body`}
            name="body"
            required
            minLength={2}
            maxLength={kind === "comment" ? 1000 : 1500}
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={t.placeholder}
            className="rounded-md border border-line bg-panel px-3 py-2"
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={pending}
              className="h-10 rounded-md bg-water px-4 font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
            >
              {pending ? "Posting…" : t.button}
            </button>
            <FormMessage state={state} />
          </div>
        </form>
      ) : (
        <p className="text-sm">
          <Link
            href={`/public/signin?next=${back}`}
            className="font-semibold text-brand hover:underline"
          >
            Sign in
          </Link>{" "}
          or{" "}
          <Link href="/public/signup" className="font-semibold text-brand hover:underline">
            join
          </Link>{" "}
          {t.invite}
        </p>
      )}
      {items.length === 0 ? (
        <p className="text-sm text-muted">{t.empty}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {items.map((c) => (
            <Comment key={c.id} c={c} signedIn={signedIn} kind={kind} />
          ))}
        </ul>
      )}
    </section>
  );
}

export function Comments({
  postId,
  comments,
  signedIn,
}: {
  postId: string;
  comments: PublicComment[];
  signedIn: boolean;
}) {
  return <Discussion id={postId} kind="comment" items={comments} signedIn={signedIn} />;
}
