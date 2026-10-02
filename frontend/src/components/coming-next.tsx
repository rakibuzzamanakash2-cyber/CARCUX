/** Honest placeholder for sections whose backend does not exist yet. */
export function ComingNext({
  title,
  purpose,
  shows,
  needs,
}: {
  title: string;
  purpose: string;
  shows: string[];
  needs: string;
}) {
  return (
    <article className="max-w-2xl">
      <h1 className="display mb-3 text-4xl">{title}</h1>
      <p className="mb-8 text-lg leading-relaxed text-steel">{purpose}</p>

      <h2 className="mb-3 text-sm text-steel">What this page will show</h2>
      <ul className="mb-8 flex flex-col gap-2 border-l border-line pl-4">
        {shows.map((s) => (
          <li key={s} className="leading-relaxed">
            {s}
          </li>
        ))}
      </ul>

      <p className="border-l-2 border-amber pl-3 text-sm text-steel">
        <span className="text-bone">Not built yet.</span> {needs}
      </p>
    </article>
  );
}
