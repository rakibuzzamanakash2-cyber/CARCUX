import { ComingNext } from "@/components/coming-next";

export const metadata = { title: "Field reports" };

export default function FieldReportsPage() {
  return (
    <ComingNext
      title="Field reports"
      purpose="Reports from authorised field workers: what they saw, where, and when."
      shows={[
        "New reports with text, location, time and photos.",
        "Integrity checks on each report, such as GPS that jumps impossibly or a reused photo.",
        "For field workers: a form to submit a report, which also works without a connection and sends later.",
      ]}
      needs="Needs the field report API and the integrity module."
    />
  );
}
