import { Link2 } from "lucide-react";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { dhakaNowLocalInput, isUuid } from "@/lib/format";
import { REPORT_REVIEWERS, type CarcuxEvent, type District } from "@/lib/types";

import { LinkForm } from "./link-form";

export const metadata = { title: "Add a link" };

export default async function AddLinkPage({
  searchParams,
}: {
  searchParams: Promise<{ event?: string }>;
}) {
  await requireRole(...REPORT_REVIEWERS);
  const { event: eventId } = await searchParams;
  const districts = await api<District[]>("/places/districts");
  let event: CarcuxEvent | null = null;
  if (eventId && isUuid(eventId)) {
    try {
      event = await api<CarcuxEvent>(`/events/${eventId}`);
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 404)) throw error;
    }
  }

  return (
    <>
      <PageBand
        scene="padma"
        icon={Link2}
        back={
          event
            ? { href: `/events/${event.id}?tab=evidence`, label: event.title }
            : { href: "/signals", label: "All signals" }
        }
        title="Add a link"
        description="A Facebook post, a YouTube video, an X post, a news article: paste the link and what it says. CARCUX does not open the link; it reads the platform and the post from the address, and you paste the words."
      />
      <PageBody>
        <div className="flex max-w-3xl flex-col gap-6">
          <Panel>
            <LinkForm
              districts={districts.map((d) => ({ name: d.name, division: d.division }))}
              now={dhakaNowLocalInput()}
              event={event ? { id: event.id, title: event.title } : null}
            />
          </Panel>
          <Panel title="Good to know">
            <ul className="flex list-disc flex-col gap-2 pl-5 text-sm">
              <li>
                Each page, channel or account becomes its own source, so CARCUX learns how often it
                has been right.
              </li>
              <li>The same post pasted twice is one item, whatever tracking the link carries.</li>
              <li>
                Posts from social media go into the CARCUX-BD dataset as links and labels only,
                never their text, and accounts are not named.
              </li>
              <li>
                Paste only what was posted publicly. Leave out names and phone numbers of people who
                are not public figures.
              </li>
            </ul>
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
