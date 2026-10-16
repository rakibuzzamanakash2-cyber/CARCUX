import Image from "next/image";
import Link from "next/link";

import { signOut } from "@/app/actions/public";
import { publicMe } from "@/lib/public";

export const metadata = {
  title: { default: "Official posts", template: "%s | CARCUX" },
  description:
    "Statements from verified government offices on disasters and disruptions in Bangladesh.",
};

export default async function PublicLayout({ children }: { children: React.ReactNode }) {
  const me = await publicMe();
  return (
    <div className="flex min-h-dvh flex-col bg-ground">
      <header className="sticky top-0 z-50 border-b border-[#1f7a46]/60 bg-gradient-to-r from-night via-[#0d2a1d] to-night text-white">
        <div className="mx-auto flex max-w-5xl items-center gap-4 px-4 py-2.5">
          <Link
            href="/public"
            className="flex shrink-0 items-center"
            aria-label="CARCUX official posts"
          >
            <Image
              src="/carcux-logo-on-dark.png"
              alt="CARCUX"
              width={900}
              height={211}
              priority
              className="h-8 w-auto"
            />
          </Link>
          <nav aria-label="Public" className="hidden text-sm font-semibold sm:block">
            <Link href="/public" className="text-night-ink hover:text-white">
              Official posts
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-3 text-sm">
            {me ? (
              <>
                <Link
                  href="/public/account"
                  className="font-semibold text-night-ink hover:text-white"
                >
                  {me.display_name}
                </Link>
                <form action={signOut}>
                  <button type="submit" className="text-night-muted hover:text-white">
                    Sign out
                  </button>
                </form>
              </>
            ) : (
              <>
                <Link href="/public/signin" className="text-night-ink hover:text-white">
                  Sign in
                </Link>
                <Link
                  href="/public/signup"
                  className="rounded-md bg-white px-3 py-1.5 font-semibold text-night hover:bg-white/90"
                >
                  Join
                </Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-3xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t border-line bg-panel py-5 text-sm text-muted">
        <div className="mx-auto max-w-3xl px-4">
          <p>
            Official posts come only from government offices verified by CARCUX. Comments are
            people&apos;s own views, not verified.
          </p>
          <p className="mt-1">
            <Link href="/public/rules" className="font-semibold text-brand hover:underline">
              Rules and privacy
            </Link>
          </p>
        </div>
      </footer>
    </div>
  );
}
