/** Ordinary pages: a green band (PageBand) then the working area (PageBody). */
export default function PagedLayout({ children }: { children: React.ReactNode }) {
  return <main className="w-full">{children}</main>;
}
