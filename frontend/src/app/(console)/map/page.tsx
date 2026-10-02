import { ComingNext } from "@/components/coming-next";

export const metadata = { title: "Situation map" };

export default function MapPage() {
  return (
    <ComingNext
      title="Situation map"
      purpose="Where things are happening right now, at a glance."
      shows={[
        "Each tracked event at its location, sized by how many people or areas it affects.",
        "Status and priority on every marker, so the most urgent situations stand out.",
        "Field reports as they arrive, with their GPS position.",
      ]}
      needs="Needs events and field reports in the backend first."
    />
  );
}
