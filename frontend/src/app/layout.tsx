import type { Metadata } from "next";
import localFont from "next/font/local";

import "./globals.css";

// One family, two widths: condensed for headings, normal for reading.
// Self-hosted (SIL OFL, see fonts/ARCHIVO-OFL.txt): builds work offline and
// staff browsers never call a third-party font service.
const archivo = localFont({
  src: "./fonts/archivo-latin-wdth-normal.woff2",
  variable: "--font-archivo",
  weight: "100 900",
  display: "swap",
  declarations: [{ prop: "font-stretch", value: "62% 125%" }],
});

export const metadata: Metadata = {
  title: { default: "CARCUX", template: "%s · CARCUX" },
  description: "AI situational intelligence platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${archivo.variable} h-full antialiased`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
