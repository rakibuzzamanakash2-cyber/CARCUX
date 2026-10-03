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
    <main className="grid min-h-screen lg:grid-cols-[1fr_32rem]">
      {/* Bangladesh, drawn from the same map data the console uses. */}
      <section
        aria-hidden="true"
        className="relative hidden overflow-hidden bg-forest lg:flex lg:flex-col lg:justify-end lg:p-12"
      >
        <Image
          src="/geo/bangladesh-outline.svg"
          alt=""
          width={600}
          height={836}
          unoptimized
          priority
          className="pointer-events-none absolute top-1/2 left-1/2 h-[110%] w-auto -translate-x-1/2 -translate-y-1/2 select-none"
        />
        <div className="relative max-w-md text-white">
          <p className="mb-2 text-3xl leading-tight font-semibold">
            One picture of what is happening, built from what people on the ground report.
          </p>
          <p className="text-forest-ink">
            Floods, fires, road blockages and outages across Bangladesh, checked and tracked.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center bg-panel px-6 py-12">
        <div className="w-full max-w-sm">
          <Image
            src="/carcux-logo.png"
            alt="CARCUX"
            width={900}
            height={211}
            priority
            className="mb-10 h-auto w-60"
          />
          <h1 className="display mb-1 text-2xl">Sign in</h1>
          <p className="mb-6 text-sm text-muted">For authorised staff and field workers.</p>
          {notice && (
            <p
              role="status"
              className="mb-5 rounded-md border border-alert/40 bg-alert-soft px-3 py-2 text-sm"
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
