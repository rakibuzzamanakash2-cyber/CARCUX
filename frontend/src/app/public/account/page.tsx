import { redirect } from "next/navigation";

import { publicMe } from "@/lib/public";

import { DeleteAccountForm } from "./delete-form";

export const metadata = { title: "Your account" };

export default async function AccountPage() {
  const me = await publicMe();
  if (!me) redirect("/public/signin?next=/public/account");
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-bold">Your account</h1>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 rounded-xl border border-line bg-panel p-5">
        <dt className="text-muted">Name</dt>
        <dd className="font-semibold">{me.display_name}</dd>
        <dt className="text-muted">Email</dt>
        <dd>{me.email} (never shown to others)</dd>
      </dl>
      <section className="rounded-xl border border-critical/40 bg-panel p-5">
        <h2 className="font-semibold">Delete your account</h2>
        <p className="mb-3 text-sm text-muted">
          Deletes your account with all your likes, comments and reports. This cannot be undone.
        </p>
        <DeleteAccountForm />
      </section>
    </div>
  );
}
