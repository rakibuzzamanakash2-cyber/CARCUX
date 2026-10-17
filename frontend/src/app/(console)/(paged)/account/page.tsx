import { KeyRound, ShieldCheck, UserRound } from "lucide-react";

import { PageBand, PageBody, Panel } from "@/components/page-header";
import { api } from "@/lib/api";
import { verifySession } from "@/lib/dal";
import { formatDhaka } from "@/lib/format";
import { roleLabel, type TwoFactorStatus } from "@/lib/types";

import { PasswordForm } from "./password-form";
import { TwoFactorPanel } from "./two-factor";

export const metadata = { title: "Your account" };

export default async function AccountPage() {
  const user = await verifySession();
  const twoFactor = await api<TwoFactorStatus>("/auth/two-factor");
  return (
    <>
      <PageBand
        scene="padma"
        icon={UserRound}
        title="Your account"
        description="Who you are signed in as, your password and two-factor sign-in."
      />
      <PageBody>
        {user.two_factor_setup_needed && (
          <p
            role="alert"
            className="rounded-xl border border-critical/50 bg-critical-soft px-4 py-3 text-sm text-ink"
          >
            Your role must use two-factor sign-in. Set it up below to continue to the rest of
            CARCUX.
          </p>
        )}
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
          <Panel
            id="two-factor"
            title="Two-factor sign-in"
            icon={ShieldCheck}
            description="A code from your phone after your password, so a stolen password alone cannot open your account."
          >
            <TwoFactorPanel status={twoFactor} />
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
