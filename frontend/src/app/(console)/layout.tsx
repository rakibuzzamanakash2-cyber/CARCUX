import { logout } from "@/app/actions/auth";
import { Sidebar } from "@/components/sidebar";
import { verifySession } from "@/lib/dal";
import { roleLabel } from "@/lib/types";

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const user = await verifySession();

  return (
    <div className="grid min-h-screen md:grid-cols-[13rem_1fr]">
      <aside className="border-b border-line bg-panel md:sticky md:top-0 md:h-screen md:border-b-0 md:border-r">
        <Sidebar role={user.role} />
      </aside>

      <div className="flex min-w-0 flex-col">
        <header className="flex items-center justify-end gap-5 border-b border-line px-6 py-3 md:px-10">
          <p className="text-sm">
            <span className="text-bone">{user.full_name}</span>
            <span className="ml-2 text-steel">{roleLabel(user.role)}</span>
          </p>
          <form action={logout}>
            <button
              type="submit"
              className="rounded-sm border border-line px-3 py-1.5 text-sm text-steel transition-colors hover:border-steel hover:text-bone"
            >
              Sign out
            </button>
          </form>
        </header>
        <main className="w-full max-w-6xl flex-1 px-6 py-10 md:px-10">{children}</main>
      </div>
    </div>
  );
}
