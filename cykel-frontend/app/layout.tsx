import type { Metadata } from "next";
import { Geist, Geist_Mono, Bebas_Neue } from "next/font/google";
import Link from "next/link";
import NavLinks from "./NavLinks";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const bebasNeue = Bebas_Neue({ weight: "400", variable: "--font-bebas", subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "Klassementet — Dansk cykelportal",
    template: "%s | Klassementet",
  },
  description: "Klassementet er Danmarks bedste cykelportal med etapeinfo, favoritter, højdeprofiler og klassementer fra UCI WorldTour.",
  metadataBase: new URL("https://klassementet.dk"),
  verification: {
    google: "KS9dcw2BBbQ_zhT2_YPgVjXgZiWXeOv5E8_5OxIYbXs",
  },
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
    shortcut: "/favicon.svg",
  },
  openGraph: {
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    images: ["/social-cover.png"],
  },
  alternates: {
    types: { "application/rss+xml": "https://klassementet.dk/api/rss" },
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="da" className={`${geistSans.variable} ${geistMono.variable} ${bebasNeue.variable} h-full`}>
      <body className="min-h-full flex flex-col antialiased" style={{ background: "var(--background)", color: "var(--foreground)" }}>

        {/* ── Navigation ─────────────────────────────────────────────────── */}
        <nav
          className="sticky top-0 z-20 backdrop-blur-md"
          style={{
            borderBottom: "1px solid var(--border)",
            background: "rgba(6, 9, 26, 0.95)",
          }}
        >
          <div className="mx-auto max-w-5xl px-6 h-16 flex items-center justify-between">
            <Link href="/" className="flex items-center gap-3 group">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo-icon.svg"
                alt=""
                width={26}
                height={26}
                className="opacity-60 group-hover:opacity-90 transition-opacity duration-200"
              />
              <span className="font-display text-xl tracking-widest">
                <span style={{ color: "var(--accent)" }}>K</span>
                <span className="text-white/90 group-hover:text-white transition-colors duration-200">lassementet</span>
              </span>
            </Link>
            <NavLinks />
          </div>
        </nav>

        <main className="flex-1">{children}</main>

        {/* ── Footer ─────────────────────────────────────────────────────── */}
        <footer
          className="mt-16 py-10"
          style={{ borderTop: "1px solid var(--border)" }}
        >
          <div className="mx-auto max-w-5xl px-6">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-5">
              <span className="font-display text-sm tracking-[0.2em]" style={{ color: "var(--text-3)" }}>
                KLASSEMENTET
              </span>

              <nav className="flex items-center gap-7 text-xs" style={{ color: "var(--text-3)" }}>
                <Link href="/om" className="hover:text-white transition-colors duration-150">Om os</Link>
                <a href="https://www.facebook.com/profile.php?id=61576574048561" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors duration-150">Facebook</a>
                <a href="https://www.instagram.com/klassementet" target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors duration-150">Instagram</a>
                <a href="/api/rss" className="hover:text-white transition-colors duration-150">RSS</a>
              </nav>

              <p className="text-[11px]" style={{ color: "var(--text-3)" }}>
                Data: UCI · ProCyclingStats · VeloWire
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
