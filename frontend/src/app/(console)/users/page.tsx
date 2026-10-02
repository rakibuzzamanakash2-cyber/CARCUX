import { api } from "@/lib/api";
import { requireRole } from "@/lib/dal";
import type { User } from "@/lib/types";

import { CreateUserForm } from "./create-user-form";
import { UserRow } from "./user-row";

export const metadata = { title: "Users" };

export default async function UsersPage() {
  const me = await requireRole("admin");
  const users = await api<User[]>("/users");
  const active = users.filter((u) => u.is_active).length;

  return (
    <div className="flex flex-col gap-10">
      <section>
        <h1 className="display mb-3 text-4xl">Users</h1>
        <p className="max-w-2xl text-steel">
          {users.length} {users.length === 1 ? "account" : "accounts"}, {active} active. Changing
          someone&apos;s role or deactivating them signs them out immediately.
        </p>
      </section>

      <section aria-label="Accounts" className="overflow-x-auto">
        <table className="w-full min-w-[44rem] text-left text-sm">
          <thead className="border-b border-line text-steel">
            <tr>
              <th scope="col" className="py-2 pr-4 font-normal">Name</th>
              <th scope="col" className="py-2 pr-4 font-normal">Email</th>
              <th scope="col" className="py-2 pr-4 font-normal">Role</th>
              <th scope="col" className="py-2 pr-4 font-normal">Last sign-in</th>
              <th scope="col" className="py-2 font-normal">Access</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {users.map((u) => (
              <UserRow key={u.id} user={u} isSelf={u.id === me.id} />
            ))}
          </tbody>
        </table>
      </section>

      <section aria-labelledby="add" className="border-t border-line pt-6">
        <h2 id="add" className="display mb-1 text-2xl">Add an account</h2>
        <p className="mb-6 text-sm text-steel">
          The email is only used as a sign-in name; CARCUX never sends mail to it.
        </p>
        <CreateUserForm />
      </section>
    </div>
  );
}
