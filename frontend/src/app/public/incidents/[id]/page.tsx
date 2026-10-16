import { notFound } from "next/navigation";

import { Discussion } from "@/components/public/comments";
import { PostCard } from "@/components/public/post-card";
import { ApiError } from "@/lib/api";
import { eventTypeLabel } from "@/lib/event-types";
import { formatDhaka, isUuid } from "@/lib/format";
import { publicApi, publicMe } from "@/lib/public";
import type { PublicIncident } from "@/lib/types";

export default async function PublicIncidentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  if (!isUuid(id)) notFound();
  let incident: PublicIncident;
  try {
    incident = await publicApi<PublicIncident>(`/incidents/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const me = await publicMe();
  const e = incident.event;
  return (
    <div className="flex flex-col gap-4">
      <section>
        <p className="text-sm text-muted">
          {eventTypeLabel(e.event_type)}
          {e.place_name && `, ${e.place_name}`} · {formatDhaka(e.started_at)}
        </p>
        <h1 className="text-2xl font-bold">{e.title}</h1>
      </section>
      <section aria-labelledby="official-h" className="flex flex-col gap-3">
        <h2 id="official-h" className="text-lg font-semibold">
          Official posts
        </h2>
        {incident.posts.map((p) => (
          <PostCard key={p.id} post={p} signedIn={!!me} />
        ))}
      </section>
      <div className="mt-4 rounded-xl border border-dashed border-line bg-panel p-4">
        <Discussion id={e.id} kind="opinion" items={incident.opinions} signedIn={!!me} />
      </div>
    </div>
  );
}
