export const metadata = { title: "Rules and privacy" };

export default function RulesPage() {
  return (
    <article className="flex flex-col gap-4 rounded-xl border border-line bg-panel p-6 leading-relaxed">
      <h1 className="text-2xl font-bold">Rules and privacy</h1>
      <section>
        <h2 className="font-semibold">Official posts</h2>
        <p>
          Only government offices verified by CARCUX can post here, after the office confirmed its
          page through its own email address or an official letter. A post is never edited: a
          correction is a new post, and the earlier one is marked as corrected.
        </p>
      </section>
      <section>
        <h2 className="font-semibold">Comments</h2>
        <ul className="list-disc pl-5">
          <li>
            No false information, abuse or hate, spam, or other people&apos;s personal information.
          </li>
          <li>
            Anyone signed in can report a comment. A comment reported by several people is hidden
            until a moderator looks at it.
          </li>
          <li>
            Moderators (CARCUX admins, and the office for comments on its own posts) can hide
            comments. Admins can ban accounts that break the rules.
          </li>
          <li>You can comment a few times every ten minutes.</li>
        </ul>
      </section>
      <section>
        <h2 className="font-semibold">What we keep</h2>
        <p>
          Your email address (to confirm your account; never shown), the name you chose, your
          password in a form that cannot be read back, your likes, comments and reports. You can
          delete your account at any time from Your account; everything you posted goes with it.
        </p>
      </section>
    </article>
  );
}
