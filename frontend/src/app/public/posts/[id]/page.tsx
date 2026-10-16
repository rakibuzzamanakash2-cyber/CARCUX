import Link from "next/link";
import { notFound } from "next/navigation";

import { Comments } from "@/components/public/comments";
import { PostCard } from "@/components/public/post-card";
import { ApiError } from "@/lib/api";
import { isUuid } from "@/lib/format";
import { publicApi, publicMe } from "@/lib/public";
import type { PublicPostDetail } from "@/lib/types";

async function load(id: string): Promise<PublicPostDetail> {
  if (!isUuid(id)) notFound();
  try {
    return await publicApi<PublicPostDetail>(`/posts/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const post = await load((await params).id);
  return { title: `${post.title} · ${post.page.name}`, description: post.body.slice(0, 200) };
}

export default async function PublicPostPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [post, me] = await Promise.all([load(id), publicMe()]);
  return (
    <div className="flex flex-col gap-6">
      <Link href="/public" className="text-sm font-semibold text-brand hover:underline">
        ← All official posts
      </Link>
      <PostCard post={post} signedIn={!!me} full />
      <Comments postId={post.id} comments={post.comment_list} signedIn={!!me} />
    </div>
  );
}
