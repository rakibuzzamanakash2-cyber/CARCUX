import { PageBand, PageBody, Panel, StatTile, StatTiles } from "@/components/page-header";
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
    <>
      <PageBand
        title="Users"
        description={`${users.length} ${users.length === 1 ? "account" : "accounts"}, ${active} active. Changing someone's role or deactivating them signs them out immediately.`}
      />
      <PageBody>
        <StatTiles>
          <StatTile value={users.length} label="Accounts" tone="forest" />
          <StatTile
            value={active}
            label="Active"
            note={`${users.length - active} deactivated`}
            tone="green"
          />
          <StatTile
            value={
              users.filter((u) => u.is_active && (u.role === "admin" || u.role === "analyst"))
                .length
            }
            label="Admins and analysts"
            tone="red"
          />
          <StatTile
            value={users.filter((u) => u.is_active && u.role === "field_worker").length}
            label="Field workers"
            tone="amber"
          />
        </StatTiles>

        <section
          aria-label="Accounts"
          className="overflow-x-auto rounded-lg border border-line bg-panel px-4 shadow-sm"
        >
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="border-b border-line text-steel">
              <tr>
                <th scope="col" className="py-3 pr-4 font-normal">
                  Name
                </th>
                <th scope="col" className="py-3 pr-4 font-normal">
                  Email
                </th>
                <th scope="col" className="py-3 pr-4 font-normal">
                  Role
                </th>
                <th scope="col" className="py-3 pr-4 font-normal">
                  Last sign-in
                </th>
                <th scope="col" className="py-3 font-normal">
                  Access
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {users.map((u) => (
                <UserRow key={u.id} user={u} isSelf={u.id === me.id} />
              ))}
            </tbody>
          </table>
        </section>

        <Panel
          id="add"
          title="Add an account"
          description="The email is only a sign-in name; CARCUX never sends mail to it."
        >
          <CreateUserForm />
        </Panel>
      </PageBody>
    </>
  );
}
