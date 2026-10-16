import { PostCard } from "@/components/public/post-card";
import { publicApi, publicMe } from "@/lib/public";
import type { PublicPost } from "@/lib/types";

export const metadata = { title: "Official posts" };

export default async function PublicFeed({
  searchParams,
}: {
  searchParams: Promise<{ welcome?: string; deleted?: string }>;
}) {
  const [{ welcome, deleted }, me, posts] = await Promise.all([
    searchParams,
    publicMe(),
    publicApi<PublicPost[]>("/posts?limit=30"),
  ]);
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-bold">Official posts</h1>
        <p className="text-muted">
          Statements from verified government offices about disasters and disruptions in Bangladesh,
          newest first.
        </p>
      </div>
      {welcome && (
        <p role="status" className="rounded-md border border-ok/50 bg-ok/10 px-3 py-2 text-sm">
          Your account is confirmed. You can now like and comment.
        </p>
      )}
      {deleted && (
        <p role="status" className="rounded-md border border-line bg-panel px-3 py-2 text-sm">
          Your account and everything you posted were deleted.
        </p>
      )}
      {posts.length === 0 ? (
        <p className="text-muted">No official posts yet.</p>
      ) : (
        posts.map((p) => <PostCard key={p.id} post={p} signedIn={!!me} />)
      )}
    </div>
  );
}
