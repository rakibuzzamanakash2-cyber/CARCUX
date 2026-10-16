"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { banAccount, hideComment, keepComment, unbanAccount } from "@/app/actions/moderation";
import { formatDhaka } from "@/lib/format";
import { REPORT_REASONS, type ActionState, type ModerationComment } from "@/lib/types";

const reasonLabel = (r: string) => REPORT_REASONS.find((x) => x.value === r)?.label ?? r;
const link = "font-semibold text-brand hover:underline disabled:opacity-60";

export function ModerationItem({ c, admin }: { c: ModerationComment; admin: boolean }) {
  const [pending, startTransition] = useTransition();
  const [result, setResult] = useState<ActionState>();
  const done = !!result?.ok;
  const run = (fn: () => Promise<ActionState>) =>
    startTransition(async () => setResult(await fn()));
  return (
    <li className="rounded-lg border border-line bg-panel p-4" data-testid="moderation-item">
      <p className="text-sm text-muted">
        On{" "}
        <Link
          href={`/public/posts/${c.statement_id}`}
          className="font-semibold text-ink hover:underline"
        >
          {c.statement_title}
        </Link>{" "}
        ({c.page_name}) · {formatDhaka(c.created_at)}
      </p>
      <p className="mt-1">
        <span className="font-semibold">{c.author}</span>
        {c.account_status === "banned" && <span className="ml-2 text-critical">banned</span>}
      </p>
      <p className="mt-1 whitespace-pre-line">{c.body}</p>
      <p className="mt-2 text-sm">
        {c.reports > 0 && (
          <span className="text-critical">
            {c.reports} {c.reports === 1 ? "report" : "reports"}:{" "}
            {c.report_reasons.map(reasonLabel).join(", ")}
          </span>
        )}
        {c.hidden_at && (
          <span className="ml-2 text-muted">
            Hidden {formatDhaka(c.hidden_at)}
            {c.hidden_reason && `: ${c.hidden_reason}`}
          </span>
        )}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
        {done ? null : !c.hidden_at || c.hidden_reason?.startsWith("Hidden after reports") ? (
          <>
            {!c.hidden_at && (
              <button
                type="button"
                className={link}
                disabled={pending}
                onClick={() => {
                  const reason = window.prompt(
                    "Why hide it? (shown in the audit log)",
                    "Breaks the rules",
                  );
                  if (reason) run(() => hideComment(c.id, reason));
                }}
              >
                Hide
              </button>
            )}
            <button
              type="button"
              className={link}
              disabled={pending}
              onClick={() => run(() => keepComment(c.id))}
            >
              Keep it up
            </button>
          </>
        ) : (
          <button
            type="button"
            className={link}
            disabled={pending}
            onClick={() => run(() => keepComment(c.id))}
          >
            Restore
          </button>
        )}
        {admin &&
          !done &&
          (c.account_status === "banned" ? (
            <button
              type="button"
              className={link}
              disabled={pending}
              onClick={() => run(() => unbanAccount(c.account_id))}
            >
              Lift ban
            </button>
          ) : (
            <button
              type="button"
              className="font-semibold text-critical hover:underline disabled:opacity-60"
              disabled={pending}
              onClick={() => {
                const reason = window.prompt(
                  `Ban ${c.author}? Give the reason:`,
                  "Repeatedly breaks the rules",
                );
                if (reason) run(() => banAccount(c.account_id, reason));
              }}
            >
              Ban account
            </button>
          ))}
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
