import Link from "next/link";

import { SignInForm } from "./signin-form";

export const metadata = { title: "Sign in" };

export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-bold">Sign in</h1>
      <SignInForm next={next ?? "/public"} />
      <p className="text-sm">
        New here?{" "}
        <Link href="/public/signup" className="font-semibold text-brand hover:underline">
          Join
        </Link>
      </p>
    </div>
  );
}
