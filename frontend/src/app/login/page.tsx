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
    <main className="relative grid min-h-screen place-items-center overflow-hidden px-4 py-12">
      {/* The delta, faintly, behind the form: CARCUX watches Bangladesh. */}
      <Image
        src="/geo/bangladesh-outline.svg"
        alt=""
        width={600}
        height={836}
        unoptimized
        priority
        aria-hidden="true"
        className="pointer-events-none absolute top-1/2 left-1/2 h-[120vh] w-auto -translate-x-[15%] -translate-y-1/2 opacity-60 select-none"
      />
      <div className="relative w-full max-w-sm rounded-xl border border-line bg-panel/95 p-6 shadow-2xl shadow-black/40 backdrop-blur sm:p-8">
        <Image
          src="/carcux-logo-light.png"
          alt="CARCUX"
          width={900}
          height={474}
          priority
          className="mb-6 h-auto w-40"
        />
        <h1 className="display mb-1 text-3xl">Sign in</h1>
        <p className="mb-6 text-sm text-muted">
          Disasters and disruptions across Bangladesh, from field reports to one picture.
        </p>
        {notice && (
          <p
            role="status"
            className="mb-5 rounded-md border border-alert/50 bg-alert-soft px-3 py-2 text-sm"
          >
            {notice}
          </p>
        )}
        <LoginForm next={next} />
      </div>
    </main>
  );
}
