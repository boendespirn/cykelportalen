import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Kontakt",
  description: "Kontakt Klassementet om advertorials, annoncering eller nyhedstip.",
  alternates: { canonical: "/kontakt" },
  openGraph: {
    url: "/kontakt",
    title: "Kontakt | Klassementet",
    description: "Kontakt Klassementet om advertorials, annoncering eller nyhedstip.",
    siteName: "Klassementet",
    locale: "da_DK",
    type: "website",
    images: [{ url: "/social-cover.png", width: 1200, height: 630 }],
  },
};

export default function KontaktLayout({ children }: { children: React.ReactNode }) {
  return children;
}
