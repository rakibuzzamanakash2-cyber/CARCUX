"use client";

import { Heart, MessageCircle, Share2 } from "lucide-react";
import Link from "next/link";
import { useState, useTransition } from "react";

import { setLike } from "@/app/actions/public";

const btn =
  "inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm font-semibold transition-colors hover:bg-panel-2 disabled:opacity-60";

/** Like, comment count and share under a post. */
export function PostActions({
  postId,
  likes,
  liked,
  comments,
  signedIn,
  title,
}: {
  postId: string;
  likes: number;
  liked: boolean;
  comments: number;
  signedIn: boolean;
  title: string;
}) {
  const [pending, startTransition] = useTransition();
  const [state, setState] = useState({ liked, likes });
  const [shared, setShared] = useState<string>();

  function toggle() {
    const next = !state.liked;
    setState({ liked: next, likes: state.likes + (next ? 1 : -1) });
    startTransition(async () => {
      const r = await setLike(postId, next);
      if (!r?.ok) setState({ liked, likes });
    });
  }

  async function share() {
    const url = `${window.location.origin}/public/posts/${postId}`;
    try {
      if (navigator.share) {
        await navigator.share({ title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setShared("Link copied");
    } catch {
      setShared(url);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1 border-t border-line pt-2 text-muted">
      {signedIn ? (
        <button
          type="button"
          onClick={toggle}
          disabled={pending}
          aria-pressed={state.liked}
          className={`${btn} ${state.liked ? "text-critical" : ""}`}
        >
          <Heart size={17} fill={state.liked ? "currentColor" : "none"} aria-hidden="true" />
          {state.likes} {state.likes === 1 ? "like" : "likes"}
        </button>
      ) : (
        <Link href={`/public/signin?next=/public/posts/${postId}`} className={btn}>
          <Heart size={17} aria-hidden="true" />
          {state.likes} {state.likes === 1 ? "like" : "likes"}
        </Link>
      )}
      <Link href={`/public/posts/${postId}#comments`} className={btn}>
        <MessageCircle size={17} aria-hidden="true" />
        {comments} {comments === 1 ? "comment" : "comments"}
      </Link>
      <button type="button" onClick={share} className={btn}>
        <Share2 size={17} aria-hidden="true" />
        Share
      </button>
      <button
        type="button"
        onClick={() =>
          window.open(
            `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(
              `${window.location.origin}/public/posts/${postId}`,
            )}`,
            "_blank",
            "noopener,noreferrer",
          )
        }
        className={`${btn} text-xs`}
      >
        Facebook
      </button>
      {shared && (
        <span role="status" className="text-sm text-ink">
          {shared}
        </span>
      )}
    </div>
  );
}
