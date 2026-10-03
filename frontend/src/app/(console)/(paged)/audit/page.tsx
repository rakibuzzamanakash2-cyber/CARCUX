import { ScrollText } from "lucide-react";

import { ComingNext } from "@/components/coming-next";
import { requireRole } from "@/lib/dal";

export const metadata = { title: "Audit log" };

export default async function AuditPage() {
  await requireRole("admin");
  return (
    <ComingNext
      icon={ScrollText}
      title="Audit log"
      purpose="A permanent record of who did what and when. Entries can never be edited or deleted."
      shows={[
        "Sign-ins, including failed attempts and why they failed.",
        "Account changes, with the value before and after.",
        "Filters by person, action and date.",
      ]}
      needs="The log is already being written by the backend. It needs a read-only API endpoint for admins before it can be shown here."
    />
  );
}
