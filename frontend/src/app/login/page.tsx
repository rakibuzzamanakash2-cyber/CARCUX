import Image from "next/image";

import { LoginForm } from "./login-form";

export const metadata = { title: "Sign in" };

const REASONS: Record<string, string> = {
  expired: "Your session ended. Sign in again to continue.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; reason?: string }>;
}) {
  const { next, reason } = await searchParams;
  const notice = reason ? REASONS[reason] : undefined;

  return (
    <main className="grid min-h-screen place-items-center px-6 py-12">
      <div className="grid w-full max-w-4xl items-center gap-10 md:grid-cols-[1fr_auto_1fr] md:gap-14">
        <section className="flex flex-col items-start gap-6">
          <Image
            src="/carcux-logo-light.png"
            alt="CARCUX"
            width={900}
            height={474}
            priority
            className="h-auto w-64 md:w-80"
          />
          <p className="max-w-sm text-base leading-relaxed text-steel">
            Field reports and public information, brought together into one evidence-backed
            picture of what is happening, so staff can decide quickly.
          </p>
        </section>

        <div className="meridian hidden h-80 md:block" aria-hidden="true" />

        <section className="w-full max-w-sm justify-self-center md:justify-self-start">
          <h1 className="display mb-2 text-4xl">Sign in</h1>
          <p className="mb-8 text-sm text-steel">For authorised staff and field workers.</p>
          {notice && (
            <p role="status" className="mb-6 border-l-2 border-amber pl-3 text-sm text-bone">
              {notice}
            </p>
          )}
          <LoginForm next={next} />
        </section>
      </div>
    </main>
  );
}
