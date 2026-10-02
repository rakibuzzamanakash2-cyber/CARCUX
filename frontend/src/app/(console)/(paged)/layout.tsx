/** Ordinary pages: a readable column inside the console shell. The map page is full-bleed. */
export default function PagedLayout({ children }: { children: React.ReactNode }) {
  return <main className="mx-auto w-full max-w-6xl px-4 py-6 md:px-8 md:py-8">{children}</main>;
}
