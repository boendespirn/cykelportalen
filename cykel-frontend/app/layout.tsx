import type { Metadata } from "next";
import { Geist, Geist_Mono, Bebas_Neue } from "next/font/google";
import Link from "next/link";
import NavLinks from "./NavLinks";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const bebasNeue = Bebas_Neue({ weight: "400", variable: "--font-bebas", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Klassementet",
  description: "Dansk portal for professionel cykling",
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
          Klassementet · Data fra UCI, ProCyclingStats og VeloWire
        </footer>
      </body>
    </html>
  );
}
