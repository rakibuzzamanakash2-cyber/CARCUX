import { ComingNext } from "@/components/coming-next";

export const metadata = { title: "Events" };

export default function EventsPage() {
  return (
    <ComingNext
      title="Events"
      purpose="Every situation CARCUX is tracking, with the evidence behind each assessment."
      shows={[
        "Assessment for each event: verified, partially verified, conflicting, unverified or refuted, with how certain it is.",
        "Which reports support it, which contradict it, and which are copies of something else.",
        "A timeline of how the picture changed as new evidence arrived.",
      ]}
      needs="Needs the events and evidence API, built on the CARCUX-BD schema."
    />
  );
}
