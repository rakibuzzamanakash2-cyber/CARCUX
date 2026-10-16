"use client";

import { Flag, Trash2 } from "lucide-react";
import Link from "next/link";
import { useActionState, useState, useTransition } from "react";

import { addComment, deleteComment, reportComment } from "@/app/actions/public";
import { FormMessage } from "@/components/form";
import { formatDhaka } from "@/lib/format";
import { REPORT_REASONS, type ActionState, type PublicComment } from "@/lib/types";

function Comment({ c, signedIn }: { c: PublicComment; signedIn: boolean }) {
  const [pending, startTransition] = useTransition();
  const [reporting, setReporting] = useState(false);
  const [reason, setReason] = useState(REPORT_REASONS[0].value);
  const [result, setResult] = useState<ActionState>();
  return (
    <li className="rounded-lg bg-panel-2/60 px-3 py-2" data-testid="comment">
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
              window.confirm("Delete your comment?") &&
              startTransition(async () => setResult(await deleteComment(c.id)))
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
                  setResult(await reportComment(c.id, reason));
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

export function Comments({
  postId,
  comments,
  signedIn,
}: {
  postId: string;
  comments: PublicComment[];
  signedIn: boolean;
}) {
  const [body, setBody] = useState("");
  const [state, action, pending] = useActionState(async (prev: ActionState, formData: FormData) => {
    const result = await addComment(postId, prev, formData);
    if (result?.ok) setBody("");
    return result;
  }, undefined);
  return (
    <section id="comments" aria-labelledby="comments-h" className="flex flex-col gap-3">
      <h2 id="comments-h" className="text-lg font-semibold">
        Comments <span className="text-muted">({comments.length})</span>
      </h2>
      <p className="text-sm text-muted">
        People&apos;s own views, not checked by CARCUX. Reported comments may be hidden.
      </p>
      {signedIn ? (
        <form action={action} className="flex flex-col gap-2">
          <label htmlFor="comment-body" className="sr-only">
            Your comment
          </label>
          <textarea
            id="comment-body"
            name="body"
            required
            minLength={2}
            maxLength={1000}
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write a comment"
            className="rounded-md border border-line bg-panel px-3 py-2"
          />
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={pending}
              className="h-10 rounded-md bg-water px-4 font-semibold text-white hover:bg-brand-strong disabled:opacity-60"
            >
              {pending ? "Posting…" : "Comment"}
            </button>
            <FormMessage state={state} />
          </div>
        </form>
      ) : (
        <p className="text-sm">
          <Link
            href={`/public/signin?next=/public/posts/${postId}`}
            className="font-semibold text-brand hover:underline"
          >
            Sign in
          </Link>{" "}
          or{" "}
          <Link href="/public/signup" className="font-semibold text-brand hover:underline">
            join
          </Link>{" "}
          to like and comment.
        </p>
      )}
      {comments.length === 0 ? (
        <p className="text-sm text-muted">No comments yet.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {comments.map((c) => (
            <Comment key={c.id} c={c} signedIn={signedIn} />
          ))}
        </ul>
      )}
    </section>
  );
}
