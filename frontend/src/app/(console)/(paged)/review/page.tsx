import { Inbox } from "lucide-react";

import { ComingNext } from "@/components/coming-next";
import { requireRole } from "@/lib/dal";

export const metadata = { title: "Review queue" };

export default async function ReviewPage() {
  await requireRole("admin", "analyst");
  return (
    <ComingNext
      icon={Inbox}
      title="Review queue"
      purpose="Assessments waiting for a person to confirm them. The system suggests; people decide."
      shows={[
        "Events ordered by priority, with the evidence for and against each one.",
        "Actions to verify an assessment, mark it as conflicting, or ask for more evidence.",
        "Every decision recorded in the audit log.",
      ]}
      needs="Needs events and assessments from the fusion engine."
    />
  );
}
