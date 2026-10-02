import Link from "next/link";

export default function NotFound() {
  return (
    <main className="grid min-h-[60vh] place-items-center px-4">
      <div className="max-w-sm text-center">
        <p className="display mb-2 text-6xl text-muted">404</p>
        <h1 className="display mb-2 text-2xl">This page could not be found.</h1>
        <p className="mb-6 text-muted">
          It may have been removed, or you may not have access to it.
        </p>
        <Link href="/" className="text-water hover:underline">
          Back to the map
        </Link>
      </div>
    </main>
  );
}
