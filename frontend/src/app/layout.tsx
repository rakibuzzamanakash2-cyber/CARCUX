import type { Metadata } from "next";

// Self-hosted from npm (SIL OFL): builds work offline and staff browsers never call
// a third-party font service. Source Sans 3 for the interface, Hind Siliguri for
// Bangla text in reports.
import "@fontsource-variable/source-sans-3/wght.css";
import "@fontsource/hind-siliguri/400.css";
import "@fontsource/hind-siliguri/600.css";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "CARCUX", template: "%s | CARCUX" },
  description: "Situational intelligence for disasters and disruptions in Bangladesh",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
