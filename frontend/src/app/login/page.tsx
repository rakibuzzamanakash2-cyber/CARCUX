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
    <main className="relative isolate grid min-h-screen bg-[#0c3a29] lg:grid-cols-[1fr_30rem]">
      {/* The Sundarbans at dusk: mangroves, a nouka on the river, a tiger on the bank. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/art/sundarbans.svg"
        alt=""
        aria-hidden="true"
        className="absolute inset-x-0 bottom-0 -z-10 h-[62%] w-full object-cover object-[70%_bottom]"
      />
      <div
        aria-hidden="true"
        className="absolute inset-0 -z-10 bg-gradient-to-b from-night/40 via-transparent to-night/80 lg:bg-gradient-to-r lg:from-night/20 lg:via-night/10 lg:to-night/90"
      />

      <section className="hidden flex-col justify-between p-10 text-white lg:flex">
        <div>
          <Image
            src="/carcux-logo-on-dark.png"
            alt="CARCUX"
            width={900}
            height={211}
            priority
            className="h-14 w-auto drop-shadow-lg"
          />
          <p className="mt-2 text-xs font-semibold tracking-[0.2em] text-night-ink/90">
            SAFER COMMUNITIES · SMARTER RESPONSE
          </p>
        </div>
        <div className="max-w-lg drop-shadow-lg">
          <p className="text-3xl leading-tight font-semibold">
            One picture of what is happening, built from what people on the ground report.
          </p>
          <p className="mt-2 text-night-ink/90">
            Floods, fires, road blockages and outages across Bangladesh, checked and tracked.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center px-5 py-12">
        <div className="w-full max-w-sm rounded-2xl border border-white/15 bg-night/80 p-7 text-white shadow-2xl shadow-black/50 backdrop-blur-md">
          <Image
            src="/carcux-logo-on-dark.png"
            alt="CARCUX"
            width={900}
            height={211}
            priority
            className="mb-8 h-auto w-48 lg:hidden"
          />
          <h1 className="display mb-1 text-2xl">Sign in</h1>
          <p className="mb-6 text-sm text-night-muted">For authorised staff and field workers.</p>
          {notice && (
            <p
              role="status"
              className="mb-5 rounded-md border border-alert-bright/50 bg-alert-bright/15 px-3 py-2 text-sm"
            >
              {notice}
            </p>
          )}
          <LoginForm next={next} />
        </div>
      </section>
    </main>
  );
}
