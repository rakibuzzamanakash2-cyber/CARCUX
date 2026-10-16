import { BadgeCheck, ExternalLink } from "lucide-react";
import { notFound } from "next/navigation";

import { PostCard } from "@/components/public/post-card";
import { ApiError } from "@/lib/api";
import { formatDhaka } from "@/lib/format";
import { publicApi, publicMe } from "@/lib/public";
import { pageKindLabel, type PublicPageView } from "@/lib/types";

export default async function PublicOfficialPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  let view: PublicPageView;
  try {
    view = await publicApi<PublicPageView>(`/pages/${encodeURIComponent(slug)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const me = await publicMe();
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-xl border border-line bg-panel p-5 shadow-sm">
        <p className="text-sm text-muted">{pageKindLabel(view.page.kind)}</p>
        <h1 className="flex flex-wrap items-center gap-2 text-2xl font-bold">
          {view.page.name}
          <BadgeCheck className="text-brand" aria-label="Verified official page" />
        </h1>
        {view.page.name_bn && <p className="text-lg">{view.page.name_bn}</p>}
        {view.description && <p className="mt-2 whitespace-pre-line">{view.description}</p>}
        <p className="mt-2 text-sm text-muted">
          Verified by CARCUX{view.verified_at && ` on ${formatDhaka(view.verified_at)}`}
          {view.website && (
            <>
              {" · "}
              <a
                href={view.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 font-semibold text-brand hover:underline"
              >
                {view.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
                <ExternalLink size={13} aria-hidden="true" />
              </a>
            </>
          )}
        </p>
      </section>
      {view.posts.length === 0 ? (
        <p className="text-muted">No posts yet.</p>
      ) : (
        view.posts.map((p) => <PostCard key={p.id} post={p} signedIn={!!me} />)
      )}
    </div>
  );
}
