import { PenLine } from "lucide-react";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import { dhakaNowLocalInput } from "@/lib/format";
import { REPORT_REVIEWERS, type District, type Source } from "@/lib/types";

import { BulletinForm } from "./bulletin-form";

export const metadata = { title: "Enter a bulletin" };

export default async function NewBulletinPage() {
  await requireRole(...REPORT_REVIEWERS);
  const [sources, districts] = await Promise.all([
    api<Source[]>("/sources"),
    api<District[]>("/places/districts"),
  ]);
  const manual = sources.filter((s) => s.adapter === "manual" && s.enabled);

  return (
    <>
      <PageBand
        scene="padma"
        icon={PenLine}
        back={{ href: "/signals", label: "All signals" }}
        title="Enter a bulletin"
        description="For publishers without a feed CARCUX can read, such as BMD weather bulletins and FFWC flood forecasts. Copy the key lines and keep the link to the original."
      />
      <PageBody>
        <div className="flex max-w-3xl flex-col gap-6">
          <Panel>
            <BulletinForm
              sources={manual.map((s) => ({ id: s.id, name: s.name }))}
              districts={districts.map((d) => ({
                name: d.name,
                division: d.division,
              }))}
              now={dhakaNowLocalInput()}
            />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
