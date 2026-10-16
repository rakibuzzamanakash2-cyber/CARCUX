import { BadgeCheck } from "lucide-react";
import Link from "next/link";

import { FindingBadge } from "@/components/statement-bits";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka } from "@/lib/format";
import type { PublicPost } from "@/lib/types";

import { PostActions } from "./post-actions";

/** An official post: the verified page speaking, never a person. */
export function PostCard({
  post,
  signedIn,
  full = false,
}: {
  post: PublicPost;
  signedIn: boolean;
  full?: boolean;
}) {
  return (
    <article className="rounded-xl border border-line bg-panel p-4 shadow-sm" data-testid="post">
      <header className="mb-2 flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-brand-soft font-bold text-brand">
          {post.page.name.slice(0, 1)}
        </span>
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-1 font-semibold">
            <Link href={`/public/pages/${post.page.slug}`} className="hover:underline">
              {post.page.name}
            </Link>
            <BadgeCheck size={16} className="text-brand" aria-label="Verified official page" />
          </p>
          <p className="text-sm text-muted">
            {formatDhaka(post.published_at)} ·{" "}
            <Link href={`/public/incidents/${post.event.id}`} className="hover:underline">
              {eventTypeLabel(post.event.event_type)}
              {post.event.place_name && `, ${post.event.place_name}`}
            </Link>
          </p>
        </div>
        <FindingBadge finding={post.finding} />
      </header>
      {post.superseded_by_id && (
        <p className="mb-2 rounded-md bg-critical-soft px-2.5 py-1.5 text-sm">
          The office corrected this post.{" "}
          <Link href={`/public/posts/${post.superseded_by_id}`} className="font-semibold underline">
            Read the correction
          </Link>
        </p>
      )}
      {post.supersedes_id && (
        <p className="mb-1 text-sm font-semibold text-alert">
          Correction of{" "}
          <Link href={`/public/posts/${post.supersedes_id}`} className="underline">
            an earlier post
          </Link>
        </p>
      )}
      <h2 className="text-lg leading-snug font-semibold">
        {full ? (
          post.title
        ) : (
          <Link href={`/public/posts/${post.id}`} className="hover:underline">
            {post.title}
          </Link>
        )}
      </h2>
      <p
        className={`mt-1 mb-3 whitespace-pre-line text-ink/90 ${full ? "text-[17px] leading-relaxed" : "line-clamp-4"}`}
      >
        {post.body}
      </p>
      <PostActions
        postId={post.id}
        likes={post.likes}
        liked={post.liked}
        comments={post.comments}
        signedIn={signedIn}
        title={post.title}
        incidentId={post.event.id}
      />
    </article>
  );
}
