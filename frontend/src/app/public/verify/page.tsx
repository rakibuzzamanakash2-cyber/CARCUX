import { ConfirmForm } from "./confirm-form";

export const metadata = { title: "Confirm your account" };

/** The emailed link lands here. Confirming takes a click, so link scanners in email
 * programs cannot use up the link. */
export default async function VerifyPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token } = await searchParams;
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-bold">Confirm your account</h1>
      {token ? (
        <ConfirmForm token={token} />
      ) : (
        <p className="text-muted">Open the link from the email we sent you.</p>
      )}
    </div>
  );
}
