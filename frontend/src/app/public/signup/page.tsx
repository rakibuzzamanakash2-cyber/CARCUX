import Link from "next/link";
import { redirect } from "next/navigation";

import { publicMe } from "@/lib/public";

import { SignUpForm } from "./signup-form";

export const metadata = { title: "Join" };

export default async function SignUpPage() {
  if (await publicMe()) redirect("/public");
  return (
    <div className="mx-auto flex max-w-md flex-col gap-4">
      <h1 className="text-2xl font-bold">Join to like and comment</h1>
      <p className="text-muted">
        Reading is open to everyone. To like and comment on official posts, sign up with your email
        address. We only use it to confirm your account; it is never shown.
      </p>
      <SignUpForm />
      <p className="text-sm">
        Already joined?{" "}
        <Link href="/public/signin" className="font-semibold text-brand hover:underline">
          Sign in
        </Link>
      </p>
    </div>
  );
}
