import { KeyRound, UserRound } from "lucide-react";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { verifySession } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import { roleLabel } from "@/lib/types";

import { PasswordForm } from "./password-form";

export const metadata = { title: "Your account" };

export default async function AccountPage() {
  const user = await verifySession();
  return (
    <>
      <PageBand
        scene="padma"
        icon={UserRound}
        title="Your account"
        description="Who you are signed in as, and your password."
      />
      <PageBody>
        <div className="grid gap-6 lg:grid-cols-[22rem_1fr] lg:items-start">
          <Panel id="profile" title="Profile" icon={UserRound}>
            <dl className="grid grid-cols-[6rem_1fr] gap-x-3 gap-y-2.5 text-sm">
              <dt className="text-muted">Name</dt>
              <dd className="font-semibold">{user.full_name}</dd>
              <dt className="text-muted">Sign-in</dt>
              <dd>{user.email}</dd>
              <dt className="text-muted">Role</dt>
              <dd>{roleLabel(user.role)}</dd>
              <dt className="text-muted">Since</dt>
              <dd>{formatDhaka(user.created_at)}</dd>
            </dl>
            <p className="mt-4 text-sm text-muted">Only an admin can change your name or role.</p>
          </Panel>
          <Panel
            id="password"
            title="Change password"
            icon={KeyRound}
            description="At least 12 characters. Changing it signs you out on every other device."
          >
            <PasswordForm />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
