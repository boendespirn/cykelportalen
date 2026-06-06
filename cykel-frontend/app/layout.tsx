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
  openGraph: {
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
  },
  alternates: {
    types: {
      "application/rss+xml": "https://klassementet.dk/api/rss",
    },
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="da" className={`${geistSans.variable} ${geistMono.variable} ${bebasNeue.variable} h-full`}>
      <body className="min-h-full flex flex-col bg-slate-950 text-slate-100 antialiased">
        <nav className="border-b border-slate-800/60 bg-slate-950/95 backdrop-blur-sm sticky top-0 z-20">
          <div className="mx-auto max-w-5xl px-6 h-14 flex items-center justify-between">
            <Link
              href="/"
              className="font-display text-xl tracking-widest text-emerald-400 hover:text-emerald-300 transition-colors"
            >
              Klassementet
            </Link>
            <NavLinks />
          </div>
        </nav>

        <main className="flex-1">{children}</main>

        <footer className="border-t border-slate-800/60 py-8 text-center text-xs text-slate-600">
          <div className="flex items-center justify-center gap-5 mb-3">
            <Link href="/om" className="hover:text-slate-400 transition-colors">Om os</Link>
            <a
              href="https://www.facebook.com/profile.php?id=61576574048561"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-400 transition-colors"
              aria-label="Facebook"
            >
              Facebook
            </a>
            <a
              href="https://www.instagram.com/klassementet"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-slate-400 transition-colors"
              aria-label="Instagram"
            >
              Instagram
            </a>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/api/rss"
              className="hover:text-slate-400 transition-colors"
              aria-label="RSS feed"
            >
              RSS
            </a>
          </div>
          <p>Klassementet · Data fra UCI, ProCyclingStats og VeloWire</p>
        </footer>
      </body>
    </html>
  );
}
